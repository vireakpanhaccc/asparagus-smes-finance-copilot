"""My data: everything the Copilot reads to build the forecast, and where it came from.

Owner only. Rows carry a `source`: bank (synced, or a payment the Copilot made after
approval), file (CSV upload) or manual (typed by the owner). Bank rows are LOCKED on the
server: a PATCH or DELETE returns 403 and the attempt is written to the audit log. The UI
hides the buttons, but this is the check that counts.

Free text (names, notes, memos) is untrusted. It is stored as-is, returned as plain
strings, flagged here when it looks like instructions, and wrapped again whenever the
agent reads it. Contact details are stored in full but only ever returned masked.
"""

import csv
import io
from datetime import date, datetime, time, timedelta, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field, StringConstraints, field_validator
from sqlalchemy import func, or_
from sqlmodel import Session, select

from app.analytics import forecast
from app.api.deps import require_owner
from app.config import settings
from app.connectors.csv_adapter import CsvAdapter
from app.db import get_session
from app.models import Bill, ConsentGrant, DataUpload, Invoice, Source, Transaction
from app.rate_limit import limiter
from app.security import audit
from app.security.masking import mask_pii
from app.security.untrusted import looks_like_instructions

router = APIRouter(prefix="/data", tags=["my data"], dependencies=[Depends(require_owner)])
ACC = settings.demo_account_id

MAX_AMOUNT_USD = 1_000_000
MAX_CSV_BYTES = 1_000_000
MAX_CSV_ROWS = 5_000
PAGE = 50
CSV_COLUMNS = {"date", "amount", "counterparty"}  # category and memo are optional
TEMPLATE_CSV = (
    "date,amount,counterparty,category,memo\n"
    "2026-10-15,320.00,Cash sales,Sales,Weekend market stall\n"
    "2026-10-16,-95.50,Central Market,Ingredients,\n"
)

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Note = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]
Contact = Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)]
Amount = Annotated[float, Field(ge=0.01, le=MAX_AMOUNT_USD, description="In dollars")]
SourceFilter = Literal["bank", "file", "manual"]
Direction = Literal["in", "out"]


# ---- helpers ----------------------------------------------------------------------------


def _usd(cents: int) -> str:
    return f"${abs(cents) / 100:,.2f}"


def _log(session: Session, action: str, detail: str, result: str = "ok") -> None:
    audit.append(session, actor="owner", action=action, tier="owner_input", result=result,
                 detail=detail)


def _flag_instructions(session: Session, source: str, *texts: str) -> None:
    if any(looks_like_instructions(t) for t in texts if t):
        audit.append(session, actor=source, action="untrusted_text_detected", tier="read_only",
                     result="ignored", detail="Instruction-like text in an entry. Stored as "
                     "data; it is never followed.")


def _within_a_year(d: date) -> date:
    if not date.today() - timedelta(days=365) <= d <= date.today() + timedelta(days=365):
        raise ValueError("must be within a year of today")
    return d


def _not_future(d: date) -> date:
    if d > date.today():
        raise ValueError("a transaction cannot be in the future")
    return _within_a_year(d)


def _upcoming(d: date) -> date:
    if d < date.today():
        raise ValueError("a bill must be due today or later")
    return _within_a_year(d)


def _at_noon(d: date) -> datetime:
    return datetime.combine(d, time(12, 0))


def _signed(direction: str, amount_usd: float) -> int:
    return round(amount_usd * 100) * (1 if direction == "in" else -1)


def _own(session: Session, model, row_id: int):
    row = session.get(model, row_id)
    if row is None or row.account_id != ACC:
        raise HTTPException(404, "No such entry.")
    return row


def _guard(session: Session, row, kind: str, label: str) -> None:
    """The lock. Bank rows can never be changed, whatever the UI shows."""
    if row.source == Source.BANK:
        _log(session, "bank_entry_edit",
             f"Tried to change {kind} #{row.id} ({label}). Bank entries are locked.",
             result="blocked")
        raise HTTPException(403, "Bank entries are locked")


# ---- schemas ----------------------------------------------------------------------------


class TransactionIn(BaseModel):
    booked_on: date
    direction: Direction
    amount_usd: Amount
    counterparty: Name
    category: Name = "Uncategorized"
    memo: Note = ""

    _date = field_validator("booked_on")(_not_future)


class TransactionPatch(BaseModel):
    booked_on: date | None = None
    direction: Direction | None = None
    amount_usd: Amount | None = None
    counterparty: Name | None = None
    category: Name | None = None
    memo: Note | None = None

    @field_validator("booked_on")
    @classmethod
    def _date(cls, d: date | None) -> date | None:
        return None if d is None else _not_future(d)


class BillIn(BaseModel):
    payee: Name
    amount_usd: Amount
    due_on: date
    category: Name = "Other"
    note: Note = ""

    _due = field_validator("due_on")(_upcoming)


class BillPatch(BaseModel):
    payee: Name | None = None
    amount_usd: Amount | None = None
    due_on: date | None = None
    category: Name | None = None
    note: Note | None = None

    @field_validator("due_on")
    @classmethod
    def _due(cls, d: date | None) -> date | None:
        return None if d is None else _upcoming(d)


class InvoiceIn(BaseModel):
    customer: Name
    amount_usd: Amount
    due_on: date
    customer_contact: Contact = ""
    note: Note = ""

    _due = field_validator("due_on")(_within_a_year)


class InvoicePatch(BaseModel):
    customer: Name | None = None
    amount_usd: Amount | None = None
    due_on: date | None = None
    customer_contact: Contact | None = None
    note: Note | None = None

    @field_validator("due_on")
    @classmethod
    def _due(cls, d: date | None) -> date | None:
        return None if d is None else _within_a_year(d)


class CorrectionIn(BaseModel):
    direction: Direction
    amount_usd: Amount
    note: Note = ""


# ---- row shapes -------------------------------------------------------------------------


def _tx_row(t: Transaction) -> dict:
    return {
        "id": t.id, "booked_at": t.booked_at.date().isoformat(),
        "amount_cents": t.amount_cents, "counterparty": t.counterparty,
        "category": t.category, "memo": t.memo, "source": t.source,
        "source_ref": t.source_ref, "created_by": t.created_by, "corrects_id": t.corrects_id,
        "locked": t.source == Source.BANK,
    }


def _bill_row(b: Bill, shortfall_weeks: list[date], today: date) -> dict:
    return {
        "id": b.id, "payee": b.payee, "amount_cents": b.amount_cents,
        "due_on": b.due_on.isoformat(), "category": b.category, "note": b.note,
        "paid": b.paid, "source": b.source, "source_ref": b.source_ref,
        "created_by": b.created_by, "locked": b.source == Source.BANK,
        "days_until_due": (b.due_on - today).days,
        "in_shortfall_week": any(w <= b.due_on <= w + timedelta(days=6) for w in shortfall_weeks),
    }


def _invoice_row(i: Invoice, today: date) -> dict:
    return {
        "id": i.id, "customer": i.customer, "customer_contact": mask_pii(i.customer_contact),
        "amount_cents": i.amount_cents, "due_on": i.due_on.isoformat(), "paid": i.paid,
        "note": i.note, "note_flagged": looks_like_instructions(i.note), "source": i.source,
        "source_ref": i.source_ref, "created_by": i.created_by,
        "locked": i.source == Source.BANK,
        "days_overdue": 0 if i.paid else max(0, (today - i.due_on).days),
    }


# ---- sources ----------------------------------------------------------------------------


def _count(session: Session, model, *where) -> int:
    return session.exec(select(func.count()).select_from(model)
                        .where(model.account_id == ACC, *where)).one()


def _active_grant(session: Session) -> ConsentGrant | None:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return session.exec(
        select(ConsentGrant).where(ConsentGrant.account_id == ACC)
        .where(ConsentGrant.revoked_at == None)  # noqa: E711
        .where(ConsentGrant.expires_at > now)
        .order_by(ConsentGrant.id.desc())
    ).first()


@router.get("/sources")
def sources(session: Session = Depends(get_session)) -> dict:
    grant = _active_grant(session)
    bank_rows = _count(session, Transaction, Transaction.source == Source.BANK)
    file_rows = _count(session, Transaction, Transaction.source == Source.FILE)
    manual = {
        "transactions": _count(session, Transaction, Transaction.source == Source.MANUAL),
        "bills": _count(session, Bill, Bill.source == Source.MANUAL),
        "invoices": _count(session, Invoice, Invoice.source == Source.MANUAL),
    }
    first, last = session.exec(
        select(func.min(Transaction.booked_at), func.max(Transaction.booked_at))
        .where(Transaction.account_id == ACC)).one()
    latest = session.exec(select(DataUpload).where(DataUpload.account_id == ACC)
                          .order_by(DataUpload.id.desc())).first()
    uploads = _count(session, DataUpload)
    manual_total = sum(manual.values())
    return {
        "bank": {
            "linked": grant is not None,
            "grant_id": grant.id if grant else None,
            "provider": grant.provider if grant else None,
            "scope": grant.scope if grant else None,
            "expires_at": grant.expires_at if grant else None,
            "last_sync_at": (grant.last_sync_at or grant.granted_at) if grant else None,
            "transactions": bank_rows,
        },
        "files": {
            "count": uploads,
            "transactions": file_rows,
            "latest": None if latest is None else {
                "filename": latest.filename, "uploaded_at": latest.uploaded_at,
                "rows": latest.rows},
        },
        "manual": {**manual, "total": manual_total},
        "totals": {  # for the tab titles: every row of each kind, whoever added it
            "transactions": _count(session, Transaction),
            "bills": _count(session, Bill),
            "invoices": _count(session, Invoice),
        },
        # First-run rule: nothing linked, uploaded or typed yet -> the UI sends the owner to /setup
        "range": {"first": first.date().isoformat() if first else None,
                  "last": last.date().isoformat() if last else None},
        "has_data": bool(grant or bank_rows or file_rows or manual_total),
    }


# ---- transactions -----------------------------------------------------------------------


def _tx_query(q: str | None):
    stmt = select(Transaction).where(Transaction.account_id == ACC)
    if q and q.strip():
        needle = q.strip().lower()
        stmt = stmt.where(or_(*(func.lower(c).contains(needle, autoescape=True)
                                for c in (Transaction.counterparty, Transaction.category,
                                          Transaction.memo))))
    return stmt


def _source_counts(session: Session, base) -> dict:
    sub = base.subquery()
    by = dict(session.exec(select(sub.c.source, func.count()).group_by(sub.c.source)).all())
    return {"all": sum(by.values()), **{s.value: by.get(s.value, 0) for s in Source}}


@router.get("/transactions")
def list_transactions(
    source: SourceFilter | None = None,
    q: str | None = Query(None, max_length=100),
    cursor: str | None = Query(None, max_length=40),
    session: Session = Depends(get_session),
) -> dict:
    base = _tx_query(q)
    counts = _source_counts(session, base)  # chips follow the search, not the source filter
    if source:
        base = base.where(Transaction.source == source)
    total = session.exec(select(func.count()).select_from(base.subquery())).one()
    stmt = base.order_by(Transaction.booked_at.desc(), Transaction.id.desc())
    if cursor:
        try:
            at, row_id = cursor.rsplit("_", 1)
            at_dt, row_id_n = datetime.fromisoformat(at), int(row_id)
        except ValueError as err:
            raise HTTPException(400, "Bad cursor.") from err
        stmt = stmt.where(or_(Transaction.booked_at < at_dt,
                              (Transaction.booked_at == at_dt) & (Transaction.id < row_id_n)))
    rows = session.exec(stmt.limit(PAGE + 1)).all()
    more = len(rows) > PAGE
    rows = rows[:PAGE]
    return {
        "rows": [_tx_row(t) for t in rows], "total": total, "counts": counts,
        "next_cursor": f"{rows[-1].booked_at.isoformat()}_{rows[-1].id}" if more else None,
    }


def _csv_safe(value: str) -> str:
    """Stop spreadsheet apps from running a cell as a formula (CSV injection)."""
    return "'" + value if value[:1] in ("=", "+", "-", "@", "\t", "\r") else value


@router.get("/transactions.csv", response_class=PlainTextResponse)
def export_transactions(
    source: SourceFilter | None = None,
    q: str | None = Query(None, max_length=100),
    session: Session = Depends(get_session),
) -> PlainTextResponse:
    stmt = _tx_query(q)
    if source:
        stmt = stmt.where(Transaction.source == source)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["date", "amount", "counterparty", "category", "memo", "source"])
    for t in session.exec(stmt.order_by(Transaction.booked_at.desc(), Transaction.id.desc())):
        writer.writerow([t.booked_at.date().isoformat(), f"{t.amount_cents / 100:.2f}",
                         _csv_safe(t.counterparty), _csv_safe(t.category), _csv_safe(t.memo),
                         t.source])
    return PlainTextResponse(
        buf.getvalue(), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=transactions.csv"})


@router.get("/template.csv", response_class=PlainTextResponse)
def template() -> PlainTextResponse:
    return PlainTextResponse(
        TEMPLATE_CSV, media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=transactions-template.csv"})


@router.post("/transactions")
@limiter.limit("60/minute")
def add_transaction(request: Request, body: TransactionIn,
                    session: Session = Depends(get_session)) -> dict:
    cents = _signed(body.direction, body.amount_usd)
    tx = Transaction(account_id=ACC, booked_at=_at_noon(body.booked_on), amount_cents=cents,
                     counterparty=body.counterparty, category=body.category, memo=body.memo,
                     source=Source.MANUAL, created_by="owner")
    session.add(tx)
    session.commit()
    session.refresh(tx)
    _flag_instructions(session, "manual_entry", body.counterparty, body.memo)
    summary = f"{'+' if cents > 0 else '-'}{_usd(cents)} {body.counterparty} on {body.booked_on}"
    _log(session, "manual_entry_added", f"Transaction: {summary}")
    return {"status": "added", "id": tx.id, "summary": summary}


@router.patch("/transactions/{row_id}")
@limiter.limit("60/minute")
def edit_transaction(request: Request, row_id: int, body: TransactionPatch,
                     session: Session = Depends(get_session)) -> dict:
    tx = _own(session, Transaction, row_id)
    _guard(session, tx, "transaction", tx.counterparty)
    changes = body.model_dump(exclude_unset=True)
    if "booked_on" in changes:
        tx.booked_at = _at_noon(changes["booked_on"])
    if "amount_usd" in changes or "direction" in changes:
        direction = changes.get("direction") or ("in" if tx.amount_cents > 0 else "out")
        amount = changes.get("amount_usd", abs(tx.amount_cents) / 100)
        tx.amount_cents = _signed(direction, amount)
    for field in ("counterparty", "category", "memo"):
        if field in changes:
            setattr(tx, field, changes[field])
    session.add(tx)
    session.commit()
    _flag_instructions(session, "manual_entry", tx.counterparty, tx.memo)
    fields = ", ".join(sorted(changes)) or "nothing"
    _log(session, "manual_entry_changed",
         f"Transaction #{tx.id} ({tx.counterparty}): changed {fields}")
    return {"status": "changed", "row": _tx_row(tx)}


@router.delete("/transactions/{row_id}")
@limiter.limit("60/minute")
def delete_transaction(request: Request, row_id: int,
                       session: Session = Depends(get_session)) -> dict:
    tx = _own(session, Transaction, row_id)
    _guard(session, tx, "transaction", tx.counterparty)
    sign = "+" if tx.amount_cents > 0 else "-"
    summary = f"{sign}{_usd(tx.amount_cents)} {tx.counterparty} on {tx.booked_at:%Y-%m-%d}"
    session.delete(tx)
    session.commit()
    _log(session, "manual_entry_deleted", f"Transaction: {summary}")
    return {"status": "deleted", "summary": summary}


@router.post("/transactions/{row_id}/correction")
@limiter.limit("60/minute")
def add_correction(request: Request, row_id: int, body: CorrectionIn,
                   session: Session = Depends(get_session)) -> dict:
    """A bank row can't be changed, so a mistake is fixed by adding an offsetting entry."""
    bank = _own(session, Transaction, row_id)
    if bank.source != Source.BANK:
        raise HTTPException(400, "Only bank entries need a correction; edit this one directly.")
    cents = _signed(body.direction, body.amount_usd)
    fix = Transaction(
        account_id=ACC, booked_at=_at_noon(date.today()), amount_cents=cents,
        counterparty=f"Correction: {bank.counterparty}"[:120], category=bank.category,
        memo=(body.note or f"Corrects bank entry #{bank.id}")[:500],
        source=Source.MANUAL, created_by="owner", corrects_id=bank.id)
    session.add(fix)
    session.commit()
    session.refresh(fix)
    _flag_instructions(session, "manual_entry", fix.memo)
    _log(session, "correction_added",
         f"{'+' if cents > 0 else '-'}{_usd(cents)} corrects bank entry #{bank.id} "
         f"({bank.counterparty})")
    return {"status": "added", "id": fix.id, "row": _tx_row(fix)}


# ---- bills ------------------------------------------------------------------------------


def _text_filter(stmt, q: str | None, *cols):
    if q and q.strip():
        needle = q.strip().lower()
        stmt = stmt.where(or_(*(func.lower(c).contains(needle, autoescape=True) for c in cols)))
    return stmt


@router.get("/bills")
def list_bills(
    source: SourceFilter | None = None,
    q: str | None = Query(None, max_length=100),
    session: Session = Depends(get_session),
) -> dict:
    base = _text_filter(select(Bill).where(Bill.account_id == ACC), q,
                        Bill.payee, Bill.category, Bill.note)
    counts = _source_counts(session, base)
    if source:
        base = base.where(Bill.source == source)
    rows = session.exec(base.order_by(Bill.due_on, Bill.id)).all()
    weeks = [date.fromisoformat(w) for w in
             forecast.forecast_weekly(session, ACC, weeks=12).get("shortfall_weeks", [])]
    today = date.today()
    return {"rows": [_bill_row(b, weeks, today) for b in rows], "total": len(rows),
            "counts": counts}


@router.post("/bills")
@limiter.limit("60/minute")
def add_bill(request: Request, body: BillIn, session: Session = Depends(get_session)) -> dict:
    bill = Bill(account_id=ACC, payee=body.payee, amount_cents=round(body.amount_usd * 100),
                due_on=body.due_on, category=body.category, note=body.note,
                source=Source.MANUAL, created_by="owner")
    session.add(bill)
    session.commit()
    session.refresh(bill)
    _flag_instructions(session, "manual_entry", body.payee, body.note)
    summary = f"{body.payee} {_usd(bill.amount_cents)} due {body.due_on}"
    _log(session, "manual_entry_added", f"Bill: {summary}")
    return {"status": "added", "id": bill.id, "summary": summary}


@router.patch("/bills/{row_id}")
@limiter.limit("60/minute")
def edit_bill(request: Request, row_id: int, body: BillPatch,
              session: Session = Depends(get_session)) -> dict:
    bill = _own(session, Bill, row_id)
    _guard(session, bill, "bill", bill.payee)
    changes = body.model_dump(exclude_unset=True)
    if "amount_usd" in changes:
        bill.amount_cents = round(changes.pop("amount_usd") * 100)
    for field, value in changes.items():
        setattr(bill, field, value)
    session.add(bill)
    session.commit()
    _flag_instructions(session, "manual_entry", bill.payee, bill.note)
    _log(session, "manual_entry_changed", f"Bill #{bill.id} ({bill.payee}) was edited")
    return {"status": "changed", "id": bill.id}


@router.delete("/bills/{row_id}")
@limiter.limit("60/minute")
def delete_bill(request: Request, row_id: int, session: Session = Depends(get_session)) -> dict:
    bill = _own(session, Bill, row_id)
    _guard(session, bill, "bill", bill.payee)
    summary = f"{bill.payee} {_usd(bill.amount_cents)} due {bill.due_on}"
    session.delete(bill)
    session.commit()
    _log(session, "manual_entry_deleted", f"Bill: {summary}")
    return {"status": "deleted", "summary": summary}


# ---- invoices ---------------------------------------------------------------------------


@router.get("/invoices")
def list_invoices(
    source: SourceFilter | None = None,
    q: str | None = Query(None, max_length=100),
    session: Session = Depends(get_session),
) -> dict:
    # Contacts are PII: never searched, only returned masked.
    base = _text_filter(select(Invoice).where(Invoice.account_id == ACC), q,
                        Invoice.customer, Invoice.note)
    counts = _source_counts(session, base)
    if source:
        base = base.where(Invoice.source == source)
    rows = session.exec(base.order_by(Invoice.due_on, Invoice.id)).all()
    today = date.today()
    return {"rows": [_invoice_row(i, today) for i in rows], "total": len(rows),
            "counts": counts}


@router.post("/invoices")
@limiter.limit("60/minute")
def add_invoice(request: Request, body: InvoiceIn,
                session: Session = Depends(get_session)) -> dict:
    inv = Invoice(account_id=ACC, customer=body.customer, customer_contact=body.customer_contact,
                  amount_cents=round(body.amount_usd * 100),
                  issued_on=min(date.today(), body.due_on), due_on=body.due_on,
                  note=body.note, source=Source.MANUAL, created_by="owner")
    session.add(inv)
    session.commit()
    session.refresh(inv)
    _flag_instructions(session, "manual_entry", body.customer, body.note)
    summary = f"{body.customer} owes {_usd(inv.amount_cents)}, due {body.due_on}"
    _log(session, "manual_entry_added", f"Invoice: {summary}")
    return {"status": "added", "id": inv.id, "summary": summary}


@router.patch("/invoices/{row_id}")
@limiter.limit("60/minute")
def edit_invoice(request: Request, row_id: int, body: InvoicePatch,
                 session: Session = Depends(get_session)) -> dict:
    inv = _own(session, Invoice, row_id)
    _guard(session, inv, "invoice", inv.customer)
    changes = body.model_dump(exclude_unset=True)
    if "amount_usd" in changes:
        inv.amount_cents = round(changes.pop("amount_usd") * 100)
    for field, value in changes.items():
        setattr(inv, field, value)
    session.add(inv)
    session.commit()
    _flag_instructions(session, "manual_entry", inv.customer, inv.note)
    _log(session, "manual_entry_changed", f"Invoice #{inv.id} ({inv.customer}) was edited")
    return {"status": "changed", "id": inv.id}


@router.delete("/invoices/{row_id}")
@limiter.limit("60/minute")
def delete_invoice(request: Request, row_id: int, session: Session = Depends(get_session)) -> dict:
    inv = _own(session, Invoice, row_id)
    _guard(session, inv, "invoice", inv.customer)
    summary = f"{inv.customer} owes {_usd(inv.amount_cents)}, due {inv.due_on}"
    session.delete(inv)
    session.commit()
    _log(session, "manual_entry_deleted", f"Invoice: {summary}")
    return {"status": "deleted", "summary": summary}


# ---- CSV upload -------------------------------------------------------------------------


@router.post("/upload")
@limiter.limit("20/minute")
def upload_csv(request: Request, file: UploadFile = File(...),
               session: Session = Depends(get_session)) -> dict:
    """Import transactions from a CSV. All rows or none: one bad line rejects the file."""
    raw = file.file.read(MAX_CSV_BYTES + 1)
    if len(raw) > MAX_CSV_BYTES:
        raise HTTPException(413, "File too large: the limit is 1 MB.")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as err:
        raise HTTPException(400, "The file is not UTF-8 text.") from err

    missing = CSV_COLUMNS - set(csv.DictReader(io.StringIO(text)).fieldnames or [])
    if missing:
        raise HTTPException(400, f"Missing columns: {', '.join(sorted(missing))}.")
    try:
        rows = CsvAdapter().parse(ACC, text)
    except ValueError as err:
        raise HTTPException(400, f"Nothing imported. {err}") from err
    if not rows:
        raise HTTPException(400, "No rows found.")
    if len(rows) > MAX_CSV_ROWS:
        raise HTTPException(400, f"Too many rows: the limit is {MAX_CSV_ROWS}.")
    for line, tx in enumerate(rows, start=2):
        if not 1 <= abs(tx.amount_cents) <= MAX_AMOUNT_USD * 100:
            raise HTTPException(400, f"Nothing imported. line {line}: amount out of range")
        if tx.booked_at.date() > date.today():
            raise HTTPException(400, f"Nothing imported. line {line}: date is in the future")

    name = (file.filename or "upload.csv").replace("\\", "/").rsplit("/", 1)[-1][:120]
    upload = DataUpload(account_id=ACC, filename=name or "upload.csv", rows=len(rows))
    session.add(upload)
    session.flush()  # get the id so every row can point back at its file
    for tx in rows:
        tx.source_ref = str(upload.id)
    session.add_all(rows)
    session.commit()

    if any(looks_like_instructions(t.memo) or looks_like_instructions(t.counterparty)
           for t in rows):
        audit.append(session, actor="csv_upload", action="untrusted_text_detected",
                     tier="read_only", result="ignored",
                     detail="Rows contain instruction-like text. Stored as data; never followed.")
    _log(session, "csv_imported", f"{len(rows)} transactions from {upload.filename}")
    return {"status": "imported", "rows": len(rows), "filename": upload.filename,
            "upload_id": upload.id}

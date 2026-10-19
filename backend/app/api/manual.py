"""Manual data entry, for businesses with no bank link or for what the link misses
(cash sales, upcoming bills, invoices). Owner only, validated, and audited.

Free text (names, notes) is stored as-is and treated as untrusted data whenever the
copilot reads it; instruction-like text is also flagged here, at entry.
"""

import csv
import io
from datetime import date, datetime, time, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field, StringConstraints, field_validator
from sqlmodel import Session

from app.api.deps import require_owner
from app.config import settings
from app.connectors.csv_adapter import CsvAdapter
from app.db import get_session
from app.models import Bill, Invoice, Transaction
from app.rate_limit import limiter
from app.security import audit
from app.security.untrusted import looks_like_instructions

router = APIRouter(prefix="/manual", tags=["manual entry"], dependencies=[Depends(require_owner)])

MAX_AMOUNT_USD = 1_000_000
MAX_CSV_BYTES = 1_000_000
MAX_CSV_ROWS = 5_000
CSV_COLUMNS = {"date", "amount", "counterparty"}  # category and memo are optional

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Note = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]
Amount = Annotated[float, Field(ge=0.01, le=MAX_AMOUNT_USD, description="In dollars")]


def _usd(cents: int) -> str:
    return f"${abs(cents) / 100:,.2f}"


def _within_a_year(d: date) -> date:
    if not date.today() - timedelta(days=365) <= d <= date.today() + timedelta(days=365):
        raise ValueError("must be within a year of today")
    return d


def _flag_instructions(session: Session, source: str, *texts: str) -> None:
    if any(looks_like_instructions(t) for t in texts if t):
        audit.append(session, actor=source, action="untrusted_text_detected", tier="read_only",
                     result="ignored", detail="Instruction-like text in a manual entry. Stored as "
                     "data; it is never followed.")


def _added(session: Session, action: str, detail: str) -> None:
    audit.append(session, actor="owner", action=action, tier="owner_input", result="ok",
                 detail=detail)


class TransactionIn(BaseModel):
    booked_on: date
    direction: Literal["in", "out"]
    amount_usd: Amount
    counterparty: Name
    category: Name = "Uncategorized"
    memo: Note = ""

    @field_validator("booked_on")
    @classmethod
    def _past_or_today(cls, d: date) -> date:
        if d > date.today():
            raise ValueError("a transaction cannot be in the future")
        return _within_a_year(d)


@router.post("/transactions")
@limiter.limit("60/minute")
def add_transaction(request: Request, body: TransactionIn,
                    session: Session = Depends(get_session)) -> dict:
    cents = round(body.amount_usd * 100) * (1 if body.direction == "in" else -1)
    tx = Transaction(account_id=settings.demo_account_id,
                     booked_at=datetime.combine(body.booked_on, time(12, 0)),
                     amount_cents=cents, counterparty=body.counterparty,
                     category=body.category, memo=body.memo, source="manual")
    session.add(tx)
    session.commit()
    session.refresh(tx)
    _flag_instructions(session, "manual_entry", body.counterparty, body.memo)
    summary = f"{'+' if cents > 0 else '-'}{_usd(cents)} {body.counterparty} on {body.booked_on}"
    _added(session, "manual_transaction_added", summary)
    return {"status": "added", "id": tx.id, "summary": summary}


class BillIn(BaseModel):
    payee: Name
    amount_usd: Amount
    due_on: date

    @field_validator("due_on")
    @classmethod
    def _upcoming(cls, d: date) -> date:
        if d < date.today():
            raise ValueError("a bill must be due today or later")
        return _within_a_year(d)


@router.post("/bills")
@limiter.limit("60/minute")
def add_bill(request: Request, body: BillIn, session: Session = Depends(get_session)) -> dict:
    bill = Bill(account_id=settings.demo_account_id, payee=body.payee,
                amount_cents=round(body.amount_usd * 100), due_on=body.due_on)
    session.add(bill)
    session.commit()
    session.refresh(bill)
    _flag_instructions(session, "manual_entry", body.payee)
    summary = f"{body.payee} {_usd(bill.amount_cents)} due {body.due_on}"
    _added(session, "manual_bill_added", summary)
    return {"status": "added", "id": bill.id, "summary": summary}


class InvoiceIn(BaseModel):
    customer: Name
    amount_usd: Amount
    due_on: date
    customer_contact: Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)] = ""
    note: Note = ""

    _due = field_validator("due_on")(_within_a_year)


@router.post("/invoices")
@limiter.limit("60/minute")
def add_invoice(request: Request, body: InvoiceIn,
                session: Session = Depends(get_session)) -> dict:
    inv = Invoice(account_id=settings.demo_account_id, customer=body.customer,
                  customer_contact=body.customer_contact,
                  amount_cents=round(body.amount_usd * 100),
                  issued_on=min(date.today(), body.due_on), due_on=body.due_on, note=body.note)
    session.add(inv)
    session.commit()
    session.refresh(inv)
    _flag_instructions(session, "manual_entry", body.customer, body.note)
    summary = f"{body.customer} owes {_usd(inv.amount_cents)}, due {body.due_on}"
    _added(session, "manual_invoice_added", summary)
    return {"status": "added", "id": inv.id, "summary": summary}


@router.post("/csv")
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

    header = set(csv.DictReader(io.StringIO(text)).fieldnames or [])
    missing = CSV_COLUMNS - header
    if missing:
        raise HTTPException(400, f"Missing columns: {', '.join(sorted(missing))}.")
    try:
        rows = CsvAdapter().parse(settings.demo_account_id, text)
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

    session.add_all(rows)
    session.commit()
    flagged = [t for t in rows if looks_like_instructions(t.memo) or
               looks_like_instructions(t.counterparty)]
    if flagged:
        audit.append(session, actor="csv_upload", action="untrusted_text_detected",
                     tier="read_only", result="ignored",
                     detail=f"{len(flagged)} rows contain instruction-like text. Stored as "
                     "data; never followed.")
    _added(session, "csv_transactions_imported", f"{len(rows)} transactions from a CSV file")
    return {"status": "imported", "rows": len(rows)}

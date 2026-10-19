"""My data: owner-only view, bank rows locked on the server, edit/correct/delete the rest."""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text
from sqlmodel import create_engine, select
from sqlmodel.pool import StaticPool

from app.config import settings
from app.db import get_session
from app.main import app
from app.models import AuditEntry, Bill, ConsentGrant, Invoice, Transaction
from app.policy.engine import PolicyEngine
from app.security import audit

OWNER = {"X-Owner-Token": settings.owner_demo_token}
TODAY = date.today()
CSV = (
    "date,amount,counterparty,category,memo\n"
    f"{TODAY - timedelta(days=2)},-40,Central Market,Ingredients,\n"
)


@pytest.fixture
def client(seeded):
    app.dependency_overrides[get_session] = lambda: seeded
    yield TestClient(app)
    app.dependency_overrides.clear()


def _actions(session, result=None):
    q = select(AuditEntry)
    if result:
        q = q.where(AuditEntry.result == result)
    return [e.action for e in session.exec(q).all()]


def _add_tx(client, counterparty="Cash sales", memo="", amount=120, direction="in"):
    r = client.post("/api/data/transactions", headers=OWNER, json={
        "booked_on": str(TODAY), "direction": direction, "amount_usd": amount,
        "counterparty": counterparty, "memo": memo})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _bank_row(session):
    return session.exec(select(Transaction).where(Transaction.source == "bank")).first()


def _add_bill(client, payee="Insurance"):
    r = client.post("/api/data/bills", headers=OWNER, json={
        "payee": payee, "amount_usd": 90, "due_on": str(TODAY + timedelta(days=10)),
        "category": "Insurance"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


@pytest.mark.parametrize("method,path", [
    ("get", "/api/data/sources"), ("get", "/api/data/transactions"),
    ("get", "/api/data/transactions.csv"), ("get", "/api/data/bills"),
    ("get", "/api/data/invoices"), ("get", "/api/data/template.csv"),
    ("patch", "/api/data/transactions/1"), ("delete", "/api/data/transactions/1"),
    ("patch", "/api/data/bills/1"), ("delete", "/api/data/bills/1"),
    ("patch", "/api/data/invoices/1"), ("delete", "/api/data/invoices/1"),
    ("post", "/api/data/transactions/1/correction"), ("post", "/api/data/upload"),
])
def test_every_data_route_needs_the_owner_token(client, method, path):
    assert getattr(client, method)(path).status_code == 401
    assert getattr(client, method)(path, headers={"X-Owner-Token": "no"}).status_code == 401


# ---- the lock ----------------------------------------------------------------------------


def test_bank_row_cannot_be_edited(client, seeded):
    bank = _bank_row(seeded)
    before = (bank.amount_cents, bank.counterparty)
    r = client.patch(f"/api/data/transactions/{bank.id}", headers=OWNER, json={"amount_usd": 1})
    assert r.status_code == 403 and r.json()["detail"] == "Bank entries are locked"
    seeded.refresh(bank)
    assert (bank.amount_cents, bank.counterparty) == before
    blocked = seeded.exec(select(AuditEntry).where(AuditEntry.action == "bank_entry_edit")).all()
    assert blocked and blocked[-1].result == "blocked"
    assert audit.verify_chain(seeded) == (True, None)


def test_bank_row_cannot_be_deleted(client, seeded):
    bank = _bank_row(seeded)
    r = client.delete(f"/api/data/transactions/{bank.id}", headers=OWNER)
    assert r.status_code == 403
    assert seeded.get(Transaction, bank.id) is not None
    assert "bank_entry_edit" in _actions(seeded, "blocked")


def test_bank_row_is_marked_locked_in_the_list(client):
    rows = client.get("/api/data/transactions?source=bank", headers=OWNER).json()["rows"]
    assert rows and all(r["locked"] for r in rows)


def test_a_payment_the_copilot_made_is_locked_too(client, seeded):
    bill = seeded.exec(select(Bill).where(Bill.payee == "Kitchen equipment repair")).one()
    eng = PolicyEngine(seeded, secret="s" * 32, ttl_seconds=600)
    outcome = eng.call("pay_bill", {"bill_id": bill.id})
    eng.execute(outcome.pending_action_id, eng.approve(outcome.pending_action_id,
                                                       outcome.payload_hash))
    payment = seeded.exec(select(Transaction).where(Transaction.source_ref.like("payment:%"))).one()
    assert client.delete(f"/api/data/transactions/{payment.id}", headers=OWNER).status_code == 403


# ---- edit / delete / correct the rest ----------------------------------------------------


def test_manual_row_can_be_edited_and_deleted(client, seeded):
    tx_id = _add_tx(client)
    r = client.patch(f"/api/data/transactions/{tx_id}", headers=OWNER,
                     json={"amount_usd": 75, "direction": "out", "category": "Supplies"})
    assert r.status_code == 200
    tx = seeded.get(Transaction, tx_id)
    assert tx.amount_cents == -7_500 and tx.category == "Supplies"
    assert client.delete(f"/api/data/transactions/{tx_id}", headers=OWNER).status_code == 200
    assert seeded.get(Transaction, tx_id) is None
    actions = _actions(seeded)
    assert "manual_entry_changed" in actions and "manual_entry_deleted" in actions
    assert audit.verify_chain(seeded) == (True, None)


def test_editing_only_the_amount_keeps_the_direction(client, seeded):
    tx_id = _add_tx(client, direction="out", amount=10)
    client.patch(f"/api/data/transactions/{tx_id}", headers=OWNER, json={"amount_usd": 30})
    assert seeded.get(Transaction, tx_id).amount_cents == -3_000


def test_edits_are_validated(client):
    tx_id = _add_tx(client)
    r = client.patch(f"/api/data/transactions/{tx_id}", headers=OWNER, json={"amount_usd": 0})
    assert r.status_code == 422


def test_file_rows_are_editable(client, seeded):
    client.post("/api/data/upload", headers=OWNER, files={"file": ("d.csv", CSV.encode())})
    row = client.get("/api/data/transactions?source=file", headers=OWNER).json()["rows"][0]
    assert not row["locked"]
    assert client.delete(f"/api/data/transactions/{row['id']}", headers=OWNER).status_code == 200


def test_correction_creates_linked_manual_row(client, seeded):
    bank = _bank_row(seeded)
    r = client.post(f"/api/data/transactions/{bank.id}/correction", headers=OWNER, json={
        "direction": "in" if bank.amount_cents < 0 else "out",
        "amount_usd": abs(bank.amount_cents) / 100, "note": "Entered twice"})
    assert r.status_code == 200
    fix = seeded.get(Transaction, r.json()["id"])
    assert fix.source == "manual" and fix.corrects_id == bank.id
    assert fix.amount_cents == -bank.amount_cents
    assert "correction_added" in _actions(seeded)
    seeded.refresh(bank)  # the bank row itself is untouched
    assert bank.source == "bank"


def test_only_bank_rows_get_corrections(client):
    tx_id = _add_tx(client)
    r = client.post(f"/api/data/transactions/{tx_id}/correction", headers=OWNER,
                    json={"direction": "out", "amount_usd": 5})
    assert r.status_code == 400


def test_bills_and_invoices_can_be_edited_and_deleted(client, seeded):
    bill_id = _add_bill(client)
    assert client.patch(f"/api/data/bills/{bill_id}", headers=OWNER,
                        json={"amount_usd": 120, "note": "Renewal"}).status_code == 200
    assert seeded.get(Bill, bill_id).amount_cents == 12_000
    assert client.delete(f"/api/data/bills/{bill_id}", headers=OWNER).status_code == 200
    inv = seeded.exec(select(Invoice)).first()
    assert client.patch(f"/api/data/invoices/{inv.id}", headers=OWNER,
                        json={"customer": "Customer Z"}).status_code == 200
    assert client.delete(f"/api/data/invoices/{inv.id}", headers=OWNER).status_code == 200


def test_unknown_entry_is_404(client):
    assert client.delete("/api/data/transactions/999999", headers=OWNER).status_code == 404
    assert client.patch("/api/data/bills/999999", headers=OWNER, json={}).status_code == 404


def test_editing_or_deleting_a_bill_blocks_its_pending_payment(client, seeded):
    eng = PolicyEngine(seeded, secret="s" * 32, ttl_seconds=600)
    for change in ("edit", "delete"):
        bill_id = _add_bill(client, payee=f"Payee {change}")
        outcome = eng.call("pay_bill", {"bill_id": bill_id})
        token = eng.approve(outcome.pending_action_id, outcome.payload_hash)
        if change == "edit":
            client.patch(f"/api/data/bills/{bill_id}", headers=OWNER, json={"amount_usd": 500})
        else:
            client.delete(f"/api/data/bills/{bill_id}", headers=OWNER)
        assert eng.execute(outcome.pending_action_id, token).status == "blocked"


# ---- uploads -----------------------------------------------------------------------------


def test_csv_upload_all_or_nothing(client, seeded):
    bad = CSV + "not-a-date,10,Shop,Sales,\n"
    r = client.post("/api/data/upload", headers=OWNER, files={"file": ("bad.csv", bad.encode())})
    assert r.status_code == 400 and "line 3" in r.json()["detail"]
    assert seeded.exec(select(Transaction).where(Transaction.source == "file")).all() == []
    assert client.get("/api/data/sources", headers=OWNER).json()["files"]["count"] == 0


def test_upload_records_the_file_and_points_rows_at_it(client, seeded):
    r = client.post("/api/data/upload", headers=OWNER,
                    files={"file": ("../../etc/stmt.csv", CSV.encode())})
    assert r.status_code == 200 and r.json()["filename"] == "stmt.csv"
    row = seeded.exec(select(Transaction).where(Transaction.source == "file")).one()
    assert row.source_ref == str(r.json()["upload_id"]) and row.created_by == "owner"
    files = client.get("/api/data/sources", headers=OWNER).json()["files"]
    assert files["count"] == 1 and files["latest"]["filename"] == "stmt.csv"
    assert "csv_imported" in _actions(seeded)


def test_template_has_header_and_examples(client):
    text_ = client.get("/api/data/template.csv", headers=OWNER).text
    lines = text_.strip().splitlines()
    assert lines[0] == "date,amount,counterparty,category,memo" and len(lines) == 3


# ---- reading -----------------------------------------------------------------------------


def test_invoice_contact_is_masked_in_api(client):
    rows = client.get("/api/data/invoices", headers=OWNER).json()["rows"]
    contacts = [r["customer_contact"] for r in rows]
    assert "***-***-678" in contacts and "c***@example.com" in contacts
    assert not any("345 678" in c or "customer.b@" in c for c in contacts)


def test_injected_invoice_note_is_flagged(client):
    rows = client.get("/api/data/invoices", headers=OWNER).json()["rows"]
    flagged = {r["customer"]: r["note_flagged"] for r in rows}
    assert flagged["Customer B"] is True and flagged["Customer A"] is False


def test_invoices_report_days_overdue_and_paid(client):
    listed = client.get("/api/data/invoices", headers=OWNER).json()["rows"]
    rows = {r["customer"]: r for r in listed}
    assert rows["Customer A"]["days_overdue"] > 0
    assert rows["Customer C"]["paid"] and rows["Customer C"]["days_overdue"] == 0


def test_bills_report_days_until_due_and_shortfall_week(client):
    rows = client.get("/api/data/bills", headers=OWNER).json()["rows"]
    assert len(rows) == 2 and all("days_until_due" in r for r in rows)
    assert all(isinstance(r["in_shortfall_week"], bool) for r in rows)


def test_transactions_are_paged_with_a_cursor_and_counts(client):
    first = client.get("/api/data/transactions", headers=OWNER).json()
    assert len(first["rows"]) == 50 and first["next_cursor"]
    assert first["counts"]["all"] == first["total"]
    second = client.get(f"/api/data/transactions?cursor={first['next_cursor']}",
                        headers=OWNER).json()
    assert {r["id"] for r in first["rows"]}.isdisjoint(r["id"] for r in second["rows"])
    assert second["rows"][0]["booked_at"] <= first["rows"][-1]["booked_at"]
    assert client.get("/api/data/transactions?cursor=junk", headers=OWNER).status_code == 400


def test_search_follows_the_filter_and_counts_follow_the_search(client):
    _add_tx(client, counterparty="Zebra Studio")
    hit = client.get("/api/data/transactions?q=zebra", headers=OWNER).json()
    assert hit["total"] == 1 and hit["counts"] == {"all": 1, "bank": 0, "file": 0, "manual": 1}
    only_bank = client.get("/api/data/transactions?q=zebra&source=bank", headers=OWNER).json()
    assert only_bank["total"] == 0 and only_bank["counts"]["manual"] == 1


def test_bad_source_filter_is_rejected(client):
    assert client.get("/api/data/transactions?source=mock_webank", headers=OWNER).status_code == 422


def test_csv_export_neutralises_formulas(client):
    _add_tx(client, counterparty='=HYPERLINK("http://evil")')
    body = client.get("/api/data/transactions.csv?q=hyperlink", headers=OWNER).text
    assert "'=HYPERLINK" in body and ",=HYPERLINK" not in body


# ---- sources / first run -----------------------------------------------------------------


def test_sources_reports_bank_files_and_manual(client, seeded):
    _add_tx(client)
    _add_bill(client)
    s = client.get("/api/data/sources", headers=OWNER).json()
    assert s["has_data"] and s["bank"]["transactions"] > 0
    assert s["manual"]["transactions"] == 1 and s["manual"]["bills"] == 3
    assert s["bank"]["linked"] is False  # the plain test seed has no bank link
    assert s["totals"]["bills"] == 3 and s["totals"]["transactions"] > 400
    assert s["range"]["first"] < s["range"]["last"]


def test_an_active_bank_link_shows_up_and_revoking_hides_it(client, seeded):
    g = client.post("/api/connect", headers=OWNER, json={"provider": "WeBank (mock)"}).json()
    bank = client.get("/api/data/sources", headers=OWNER).json()["bank"]
    assert bank["linked"] and bank["provider"] == "WeBank (mock)" and bank["last_sync_at"]
    client.delete(f"/api/connect/{g['id']}", headers=OWNER)
    assert client.get("/api/data/sources", headers=OWNER).json()["bank"]["linked"] is False
    assert seeded.exec(select(ConsentGrant)).one().revoked_at


def test_an_empty_business_has_no_data(client, seeded):
    for model in (Transaction, Bill, Invoice, ConsentGrant):
        for row in seeded.exec(select(model)).all():
            seeded.delete(row)
    seeded.commit()
    assert client.get("/api/data/sources", headers=OWNER).json()["has_data"] is False


# ---- migration ---------------------------------------------------------------------------


def test_older_databases_are_migrated(monkeypatch):
    import app.db as db

    old = create_engine("sqlite://", connect_args={"check_same_thread": False},
                        poolclass=StaticPool)
    with old.begin() as conn:
        conn.execute(text('CREATE TABLE "transaction" (id INTEGER PRIMARY KEY, account_id TEXT, '
                          "booked_at DATETIME, amount_cents INTEGER, currency TEXT, "
                          "counterparty TEXT, category TEXT, memo TEXT, source TEXT)"))
        conn.execute(text("CREATE TABLE bill (id INTEGER PRIMARY KEY, account_id TEXT, "
                          "payee TEXT, amount_cents INTEGER, due_on DATE, paid BOOLEAN, "
                          "source TEXT DEFAULT 'seed')"))
        conn.execute(text("CREATE TABLE invoice (id INTEGER PRIMARY KEY, account_id TEXT, "
                          "customer TEXT, customer_contact TEXT, amount_cents INTEGER, "
                          "issued_on DATE, due_on DATE, paid BOOLEAN, note TEXT)"))
        conn.execute(text("CREATE TABLE consentgrant (id INTEGER PRIMARY KEY, provider TEXT, "
                          "account_id TEXT, scope TEXT, granted_at TEXT, expires_at TEXT, "
                          "revoked_at TEXT)"))
        for i, src in enumerate(["mock_webank", "csv", "manual", "sandbox_payment"], start=1):
            conn.execute(text('INSERT INTO "transaction" (id, source) VALUES (:i, :s)'),
                         {"i": i, "s": src})
        conn.execute(text("INSERT INTO bill (id, source) VALUES (1, 'seed')"))
        conn.execute(text("INSERT INTO invoice (id) VALUES (1)"))
    monkeypatch.setattr(db, "engine", old)
    db._migrate()
    db._migrate()  # safe to run twice

    names = lambda t: {c["name"] for c in inspect(old).get_columns(t)}  # noqa: E731
    assert {"source_ref", "created_by", "corrects_id"} <= names("transaction")
    assert {"source", "source_ref", "created_by", "category", "note"} <= names("bill")
    assert {"source", "source_ref", "created_by"} <= names("invoice")
    assert "last_sync_at" in names("consentgrant")
    with old.connect() as conn:
        rows = conn.execute(text('SELECT source, created_by FROM "transaction" ORDER BY id')).all()
        assert rows == [("bank", "system"), ("file", "owner"), ("manual", "owner"),
                        ("bank", "system")]
        assert conn.execute(text("SELECT source FROM bill")).scalar() == "manual"
        assert conn.execute(text("SELECT source FROM invoice")).scalar() == "manual"


# ---- demo seed ---------------------------------------------------------------------------


def test_demo_seed_adds_user_data_without_changing_the_story(session):
    """Bank 403 + file 25 + typed 3, but the same closing balance, KPIs and shortfall."""
    from app.analytics import analysis, forecast
    from scripts.seed_data import seed

    acc = settings.demo_account_id
    def snapshot():
        return (forecast.forecast_weekly(session, acc, weeks=12),
                analysis.business_summary(session, acc))

    seed(session, today=TODAY, sample_user_data=False)
    plain = snapshot()

    seed(session, today=TODAY, sample_user_data=True)
    by_source = {s: len(session.exec(select(Transaction).where(Transaction.source == s)).all())
                 for s in ("bank", "file", "manual")}
    assert by_source == {"bank": 403, "file": 25, "manual": 3}
    assert session.exec(select(ConsentGrant)).one().provider == "WeBank (mock)"

    demo = snapshot()
    assert demo[0]["current_balance_cents"] == plain[0]["current_balance_cents"] == 420_000
    assert demo[0]["shortfall_weeks"] == plain[0]["shortfall_weeks"] != []
    assert demo[1]["last_30_days"] == plain[1]["last_30_days"]
    assert demo[1]["supplier_cost_change_8w_pct"] == plain[1]["supplier_cost_change_8w_pct"]

"""Messages that leave the business: who gets them is built by the server, and they may
not carry links, contact details or account numbers (data leaks, payment scams)."""

import pytest
from sqlmodel import select

from app.analytics.rescue import REMINDER_MESSAGE
from app.models import Invoice, PendingAction, SandboxOutbox
from app.policy.engine import PolicyEngine
from app.security.outbound import outbound_problems

SECRET = "test-secret"
UNSAFE = [
    "Please pay at http://pay.example.com today.",
    "Pay now at www.fast-pay.top",
    "Visit pay-now.xyz to settle.",
    "Transfer to account 0123456789 please.",
    "Use card 4111 1111 1111 1111.",
    "Call me on +855 12 345 678.",
    "Email the receipt to someone@example.com.",
]


def _engine(session, clock):
    return PolicyEngine(session, secret=SECRET, ttl_seconds=600, clock=clock)


def _unpaid(session):
    return session.exec(select(Invoice).where(Invoice.paid == False)).all()  # noqa: E712


def _held(session):
    return session.exec(select(PendingAction)).all()


def test_reminder_card_shows_who_gets_it(seeded, clock):
    invoices = _unpaid(seeded)
    held = _engine(seeded, clock).call(
        "send_payment_reminders", {"invoice_ids": [i.id for i in invoices], "message": "Hi"})
    assert held.status == "needs_approval"
    recipients = held.payload["recipients"]
    assert [r["customer"] for r in recipients] == [i.customer for i in invoices]
    for r, inv in zip(recipients, invoices, strict=True):
        assert inv.customer_contact not in str(r)  # contact shown masked only


@pytest.mark.parametrize("bad_id", ["unknown", "paid"])
def test_unknown_or_paid_invoice_is_refused(seeded, clock, bad_id):
    paid = seeded.exec(select(Invoice).where(Invoice.paid == True)).first()  # noqa: E712
    inv_id = 9999 if bad_id == "unknown" else paid.id
    held = _engine(seeded, clock).call(
        "send_payment_reminders", {"invoice_ids": [inv_id], "message": "Hi"})
    assert held.status == "blocked" and _held(seeded) == []


@pytest.mark.parametrize("message", UNSAFE)
def test_unsafe_reminder_is_refused_before_any_card(seeded, clock, message):
    held = _engine(seeded, clock).call(
        "send_payment_reminders",
        {"invoice_ids": [_unpaid(seeded)[0].id], "message": message})
    assert held.status == "blocked" and "Message refused" in held.reason
    assert _held(seeded) == []


@pytest.mark.parametrize("message", UNSAFE)
def test_unsafe_supplier_message_is_refused(seeded, clock, message):
    plan = _engine(seeded, clock).call("build_rescue_plan", {}).result
    supplier = next(a["args"]["supplier"] for a in plan["next_actions"]
                    if a["tool"] == "send_supplier_message")
    held = _engine(seeded, clock).call(
        "send_supplier_message", {"supplier": supplier, "message": message})
    assert held.status == "blocked" and _held(seeded) == []


@pytest.mark.parametrize("message", [
    REMINDER_MESSAGE,
    "Invoice #12 for $1,250.00 was due on 2026-10-05. Thank you!",
])
def test_normal_messages_are_allowed(message):
    assert outbound_problems(message) == []


def test_contact_changed_after_approval_blocks_the_send(seeded, clock):
    eng = _engine(seeded, clock)
    inv = _unpaid(seeded)[0]
    held = eng.call("send_payment_reminders", {"invoice_ids": [inv.id], "message": "Hi"})
    token = eng.approve(held.pending_action_id, held.payload_hash)
    inv.customer_contact = "+855 99 999 999"  # edited on My data after approval
    seeded.add(inv)
    seeded.commit()
    result = eng.execute(held.pending_action_id, token)
    assert result.status == "blocked" and "changed after approval" in result.reason
    assert seeded.exec(select(SandboxOutbox)).all() == []

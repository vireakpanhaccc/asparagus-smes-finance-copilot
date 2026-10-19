"""Loan applications: the terms the owner approves come from the product catalogue, with
the total cost shown, and the model cannot apply for a product or amount that does not fit."""

import pytest
from sqlmodel import select

from app.analytics.financing import _amortized
from app.models import PendingAction, SandboxOutbox
from app.policy.engine import PolicyEngine

SECRET = "test-secret"


def _engine(session, clock):
    return PolicyEngine(session, secret=SECRET, ttl_seconds=600, clock=clock)


def _apply(eng, product_id, amount_usd, term_months):
    return eng.call("submit_loan_application", {
        "product_id": product_id, "amount_usd": amount_usd, "term_months": term_months})


def test_card_shows_lender_payment_and_total_cost(seeded, clock):
    held = _apply(_engine(seeded, clock), "lender-a-line", 1500, 3)
    assert held.status == "needs_approval"
    payment, cost = _amortized(150_000, 0.18, 3)
    assert held.payload["lender_product"] == "[Lender A] Credit line"
    assert held.payload["monthly_payment"] == f"${payment / 100:,.2f}"
    assert held.payload["total_cost"] == f"${cost / 100:,.2f}"


@pytest.mark.parametrize("product_id, amount_usd, term_months, reason", [
    ("lender-x-fake", 1000, 3, "No such financing product"),
    ("supplier-terms", 1000, 1, "not a loan"),
    ("lender-a-line", 5000, 3, "at most"),        # over the $2,000 limit
    ("lender-c-term", 1000, 6, "fixed term"),     # the term loan is 12 months
    ("lender-b-advance", 5000, 1, "at most"),     # more than 80% of overdue invoices
])
def test_application_that_does_not_fit_is_refused(seeded, clock, product_id, amount_usd,
                                                  term_months, reason):
    held = _apply(_engine(seeded, clock), product_id, amount_usd, term_months)
    assert held.status == "blocked" and reason in held.reason
    assert seeded.exec(select(PendingAction)).all() == []


def test_approved_application_is_submitted_once_in_sandbox(seeded, clock):
    eng = _engine(seeded, clock)
    held = _apply(eng, "lender-a-line", 1500, 3)
    token = eng.approve(held.pending_action_id, held.payload_hash)
    assert eng.execute(held.pending_action_id, token).status == "ok"
    rows = seeded.exec(select(SandboxOutbox).where(SandboxOutbox.kind == "loan_application")).all()
    assert len(rows) == 1 and rows[0].recipient_masked == "[Lender A] Credit line"
    assert eng.execute(held.pending_action_id, token).status == "blocked"


def test_draft_shows_the_same_total_cost(seeded, clock):
    eng = _engine(seeded, clock)
    draft = eng.call("draft_loan_application", {
        "product_id": "lender-a-line", "amount_usd": 1500, "term_months": 3})
    held = _apply(eng, "lender-a-line", 1500, 3)
    assert draft.result["draft"]["total_cost"] == held.payload["total_cost"]

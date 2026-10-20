"""Analytics on the deterministic seed data."""

from datetime import date

from app.analytics import analysis, financing, forecast, invoices
from app.config import settings
from tests.conftest import TODAY

ACC = settings.demo_account_id


def test_overdue_invoices_match_scenario(seeded):
    overdue = invoices.find_overdue(seeded, ACC, today=TODAY)
    assert sorted(i.amount_cents for i in overdue) == [26_000, 38_000]
    assert {(TODAY - i.due_on).days for i in overdue} == {9, 14}


def test_forecast_shape_and_recurring_bills(seeded):
    fc = forecast.forecast_weekly(seeded, ACC, weeks=12, today=TODAY)
    assert fc["current_balance_cents"] == 420_000
    assert len(fc["weeks"]) == 12
    detected = {r["counterparty"] for r in fc["recurring_detected"]}
    assert {"Landlord", "Staff payroll", "Bean & Dairy Co"} <= detected
    assert date.fromisoformat(fc["weeks"][0]["week_start"]) > TODAY
    for w in fc["weeks"]:
        assert w["bills_total_cents"] == sum(b["amount_cents"] for b in w["scheduled_bills"])
        span = date.fromisoformat(w["week_end"]) - date.fromisoformat(w["week_start"])
        assert span.days == 6


def test_forecast_flags_december_shortfall(seeded):
    """The demo story: rent, wages, supplies and two known bills cluster in early December."""
    fc = forecast.forecast_weekly(seeded, ACC, weeks=12, today=TODAY)
    assert "2026-12-07" in fc["shortfall_weeks"]
    assert all(w["lowest_balance_cents"] > 0 for w in fc["weeks"][:6])


def test_supplier_cost_rise_detected(seeded):
    summary = analysis.business_summary(seeded, ACC, today=TODAY)
    assert 8 <= summary["supplier_cost_change_8w_pct"] <= 20
    assert summary["last_30_days"]["money_in_cents"] > 0


def test_financing_ranking_is_explainable(seeded):
    ranked = financing.rank_options(seeded, ACC, gap_cents=20_000, months_needed=2, today=TODAY)
    labels = {o["product_id"]: o["label"] for o in ranked["options"]}
    assert labels["supplier-terms"] == "Try first"
    assert ranked["options"][0]["kind"] == "supplier_terms"
    for o in ranked["options"]:
        assert o["why_it_fits"] or o["watch_out"]  # every option explains itself
    assert "mock" in ranked["disclaimer"].lower()


def test_loan_payments_repay_principal_not_just_interest(seeded):
    ranked = financing.rank_options(seeded, ACC, gap_cents=72_074, months_needed=2, today=TODAY)
    by_id = {o["product_id"]: o for o in ranked["options"]}
    for pid in ("lender-a-line", "lender-c-term"):
        o = by_id[pid]
        months = 2 if pid == "lender-a-line" else 12
        assert o["monthly_payment_cents"] * months >= o["amount_cents"]
        assert o["total_cost_cents"] == o["monthly_payment_cents"] * months - o["amount_cents"]


def test_summary_compares_with_the_previous_30_days(seeded):
    s = analysis.business_summary(seeded, ACC, today=TODAY)
    now, before = s["last_30_days"], s["previous_30_days"]
    for period in (now, before):
        assert period["money_in_cents"] > 0 and period["money_out_cents"] > 0
        assert period["net_cents"] == period["money_in_cents"] - period["money_out_cents"]
    assert now != before  # two different windows of the same history

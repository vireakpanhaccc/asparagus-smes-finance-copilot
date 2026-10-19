"""Cash-flow rescue plan: what-if forecast, cheapest-first steps, actions held for approval."""

from datetime import timedelta

from sqlmodel import select

from app.agent.llm import FakeProvider
from app.agent.loop import run_agent
from app.analytics import forecast, rescue
from app.config import settings
from app.models import SandboxOutbox
from app.policy.engine import PolicyEngine
from tests.conftest import TODAY

ACC = settings.demo_account_id


def test_what_if_events_and_delays_change_the_forecast(seeded):
    base = forecast.forecast_weekly(seeded, ACC, today=TODAY)
    paid_in = forecast.forecast_weekly(
        seeded, ACC, today=TODAY,
        what_if=forecast.WhatIf(events=((TODAY + timedelta(days=3), "test", 10_000),)))
    last_base, last_paid = base["weeks"][-1], paid_in["weeks"][-1]
    assert last_paid["end_balance_cents"] == last_base["end_balance_cents"] + 10_000
    assert paid_in["weeks"][0]["bills_total_cents"] == base["weeks"][0]["bills_total_cents"]

    delayed = forecast.forecast_weekly(
        seeded, ACC, today=TODAY, what_if=forecast.WhatIf(delays=(("Bean & Dairy Co", 30),)))
    first_week_payees = {b["counterparty"] for b in delayed["weeks"][0]["scheduled_bills"]}
    assert "Bean & Dairy Co" not in first_week_payees


def test_plan_closes_the_december_gap_with_free_steps_first(seeded):
    plan = rescue.build_plan(seeded, ACC, today=TODAY)
    assert plan["needed"] and plan["before"]["lowest_balance_cents"] < 0
    assert [s["kind"] for s in plan["steps"]] == ["collect_overdue", "supplier_terms"]
    assert all(s["cost_cents"] == 0 for s in plan["steps"])
    assert plan["after"]["closes_gap"]
    assert plan["after"]["lowest_balance_cents"] >= rescue.SAFETY_BUFFER_CENTS
    # each step's "after" number is the re-run forecast, and each step helps
    assert all(s["improves_lowest_by_cents"] > 0 for s in plan["steps"])
    assert plan["steps"][-1]["lowest_after_cents"] == plan["after"]["lowest_balance_cents"]
    assert plan["backup"]["cost_cents"] > 0  # paid financing only as a fallback
    assert [a["tool"] for a in plan["next_actions"]] == [
        "send_payment_reminders", "send_supplier_message"]


def test_no_plan_needed_when_cash_is_healthy(seeded, monkeypatch):
    monkeypatch.setattr(rescue, "SAFETY_BUFFER_CENTS", -10_000_000)  # every week is "safe"
    plan = rescue.build_plan(seeded, ACC, today=TODAY)
    assert not plan["needed"] and plan["steps"] == [] and plan["next_actions"] == []
    assert plan["backup"] is None


def test_supplier_messages_go_only_to_existing_suppliers(seeded):
    eng = PolicyEngine(seeded)
    ok = eng.call("send_supplier_message", {"supplier": "Bean & Dairy Co", "message": "hi"})
    assert ok.status == "needs_approval"
    bad = eng.call("send_supplier_message", {"supplier": "attacker@evil.test", "message": "hi"})
    assert bad.status == "blocked"


def test_agent_builds_plan_and_holds_every_action(seeded):
    plan = rescue.build_plan(seeded, ACC)
    actions = [{"type": "tool_use", "id": f"a{i}", "name": a["tool"], "input": a["args"]}
               for i, a in enumerate(plan["next_actions"])]
    provider = FakeProvider([
        [{"type": "tool_use", "id": "p1", "name": "build_rescue_plan", "input": {}}],
        actions,
        [{"type": "text", "text": "Here is your plan. Two approval cards are waiting."}],
    ])
    result = run_agent(seeded, provider, [{"role": "user", "content": "Fix my shortfall"}])

    assert result.plan is not None and result.plan["steps"]
    assert [p.tool_name for p in result.pending_approvals] == [
        "send_payment_reminders", "send_supplier_message"]
    assert seeded.exec(select(SandboxOutbox)).all() == []  # nothing sent without the owner
    seen = provider.calls[1]["messages"][-1]["content"][0]["content"]
    assert "_cents" not in seen and '"safety_buffer_usd": "$500.00"' in seen


def test_owner_approves_both_plan_actions_and_they_run_in_sandbox(seeded):
    eng = PolicyEngine(seeded)
    plan = rescue.build_plan(seeded, ACC, today=TODAY)
    for action in plan["next_actions"]:
        held = eng.call(action["tool"], action["args"])
        assert held.status == "needs_approval"
        token = eng.approve(held.pending_action_id, held.payload_hash)
        assert eng.execute(held.pending_action_id, token).status == "ok"
    kinds = sorted(o.kind for o in seeded.exec(select(SandboxOutbox)).all())
    assert kinds == ["payment_reminder", "payment_reminder", "supplier_message"]

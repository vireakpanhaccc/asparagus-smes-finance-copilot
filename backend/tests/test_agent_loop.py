"""Agent-loop scenarios with a scripted fake LLM (deterministic, no API key)."""

import json

from sqlmodel import select

from app.agent.llm import FakeProvider
from app.agent.loop import NOTE_NOTHING_HELD, NOTE_STILL_HELD, run_agent
from app.analytics import forecast
from app.config import settings
from app.models import AuditEntry, SandboxOutbox
from app.policy.engine import in_dollars


def _tool(id_, name, input_):
    return {"type": "tool_use", "id": id_, "name": name, "input": input_}


def test_agent_cannot_send_without_owner(seeded):
    provider = FakeProvider([
        [_tool("t1", "find_overdue_invoices", {})],
        [_tool("t2", "send_payment_reminders",
               {"invoice_ids": [1, 2], "message": "Friendly reminder"})],
        [{"type": "text", "text": "An approval card is waiting for you."}],
    ])
    result = run_agent(seeded, provider, [{"role": "user", "content": "Chase late payers"}])

    assert len(result.pending_approvals) == 1
    assert [t["status"] for t in result.tool_trace] == ["ok", "needs_approval"]
    assert seeded.exec(select(SandboxOutbox)).all() == []


def test_model_never_sees_approval_tokens(seeded):
    provider = FakeProvider([
        [_tool("t1", "send_payment_reminders", {"invoice_ids": [1], "message": "hi"})],
        [{"type": "text", "text": "Waiting for approval."}],
    ])
    run_agent(seeded, provider, [{"role": "user", "content": "send it"}])
    tool_result = provider.calls[1]["messages"][-1]["content"][0]["content"]
    assert "needs_approval" in tool_result
    assert "token" not in tool_result.lower()


def test_unknown_tool_from_model_is_blocked(seeded):
    provider = FakeProvider([
        [_tool("t1", "wire_transfer", {"to": "x", "amount": 500000})],
        [{"type": "text", "text": "I can't do that."}],
    ])
    result = run_agent(seeded, provider, [{"role": "user", "content": "wire money"}])
    assert result.tool_trace[0]["status"] == "blocked"


def test_loop_stops_after_max_steps(seeded):
    provider = FakeProvider([[_tool(f"t{i}", "find_overdue_invoices", {})] for i in range(20)])
    result = run_agent(seeded, provider, [{"role": "user", "content": "loop"}], max_steps=3)
    assert "too many steps" in result.text
    assert len(result.tool_trace) == 3


def test_model_sees_dollars_not_cents(seeded):
    provider = FakeProvider([
        [_tool("t1", "forecast_cash_flow", {"weeks": 12})],
        [{"type": "text", "text": "Done."}],
    ])
    run_agent(seeded, provider, [{"role": "user", "content": "forecast"}])
    seen = provider.calls[1]["messages"][-1]["content"][0]["content"]
    assert "_cents" not in seen
    assert '"current_balance_usd": "$4,200.00"' in seen
    assert '"lowest_balance_usd": "-$' in seen


def test_false_approval_claim_is_corrected(seeded):
    provider = FakeProvider([
        [{"type": "text", "text": "An approval card is waiting for you."}],
    ])
    result = run_agent(seeded, provider, [{"role": "user", "content": "chase late payers"}])
    assert result.text.endswith(NOTE_NOTHING_HELD)
    flagged = seeded.exec(
        select(AuditEntry).where(AuditEntry.action == "reply_claim_corrected")
    ).all()
    assert len(flagged) == 1 and flagged[0].result == "blocked"


def test_claiming_sent_while_held_is_corrected(seeded):
    provider = FakeProvider([
        [_tool("t1", "send_payment_reminders", {"invoice_ids": [1], "message": "hi"})],
        [{"type": "text", "text": "I have sent the reminders."}],
    ])
    result = run_agent(seeded, provider, [{"role": "user", "content": "send them"}])
    assert result.text.endswith(NOTE_STILL_HELD)


def test_honest_reply_is_left_alone(seeded):
    honest = "An approval card is waiting for you. Nothing has been sent yet."
    provider = FakeProvider([
        [_tool("t1", "send_payment_reminders", {"invoice_ids": [1], "message": "hi"})],
        [{"type": "text", "text": honest}],
    ])
    result = run_agent(seeded, provider, [{"role": "user", "content": "send them"}])
    assert result.text == honest


def test_financing_tool_takes_dollars(seeded):
    provider = FakeProvider([
        [_tool("t1", "rank_financing", {"gap_usd": 215.0, "months_needed": 2})],
        [_tool("t2", "rank_financing", {"gap_cents": 21500})],  # old cents input is refused
        [{"type": "text", "text": "Done."}],
    ])
    result = run_agent(seeded, provider, [{"role": "user", "content": "financing"}])
    assert [t["status"] for t in result.tool_trace] == ["ok", "blocked"]
    seen = provider.calls[1]["messages"][-1]["content"][0]["content"]
    assert '"gap_usd": "$215.00"' in seen


def test_forecast_tool_always_covers_12_weeks(seeded):
    provider = FakeProvider([
        [_tool("t1", "forecast_cash_flow", {"weeks": 4})],  # a horizon from the model is ignored
        [{"type": "text", "text": "Done."}],
    ])
    run_agent(seeded, provider, [{"role": "user", "content": "bills in the week of Nov 30?"}])
    seen = json.loads(provider.calls[1]["messages"][-1]["content"][0]["content"])
    weeks = seen["result"]["weeks"]
    assert len(weeks) == 12
    # the tool forecasts from the real date, so compare with the same forecast in cents
    expected = forecast.forecast_weekly(seeded, settings.demo_account_id, weeks=12)["weeks"]
    for got, want in zip(weeks, expected, strict=True):
        assert got["bills_total_usd"] == in_dollars(want)["bills_total_usd"]
    assert any(w["bills_total_usd"] == "-$5,800.00" for w in weeks)  # the December cluster


def test_reply_never_shows_wrapper_tags(seeded):
    provider = FakeProvider([[{"type": "text", "text":
        'You owe <untrusted_data source="payee">Bean &amp; Dairy Co</untrusted_data> $90.'}]])
    result = run_agent(seeded, provider, [{"role": "user", "content": "Who do I owe?"}])
    assert result.text == "You owe Bean & Dairy Co $90."

"""Security tests for the approval gate. Cite these in the security self-assessment."""

import json

import pytest
from sqlmodel import Session, select

from app.models import Invoice, PendingAction, SandboxOutbox
from app.policy.approvals import ApprovalError, issue_token
from app.policy.engine import PolicyEngine

SECRET = "test-secret"


def _engine(session, clock):
    return PolicyEngine(session, secret=SECRET, ttl_seconds=600, clock=clock)


def _invoice_ids(session):
    unpaid = select(Invoice).where(Invoice.paid == False)  # noqa: E712
    return [i.id for i in session.exec(unpaid).all()]


def _propose(engine, session):
    return engine.call(
        "send_payment_reminders",
        {"invoice_ids": _invoice_ids(session), "message": "Friendly reminder"},
    )


def _outbox(session):
    return session.exec(select(SandboxOutbox)).all()


def test_needs_approval_tool_is_held_not_run(seeded, clock):
    outcome = _propose(_engine(seeded, clock), seeded)
    assert outcome.status == "needs_approval"
    assert _outbox(seeded) == []


def test_execute_without_approval_is_blocked(seeded, clock):
    eng = _engine(seeded, clock)
    outcome = _propose(eng, seeded)
    result = eng.execute(outcome.pending_action_id, token=None)
    assert result.status == "blocked"
    assert _outbox(seeded) == []


def test_happy_path_runs_once_in_sandbox(seeded, clock):
    eng = _engine(seeded, clock)
    outcome = _propose(eng, seeded)
    token = eng.approve(outcome.pending_action_id, outcome.payload_hash)
    result = eng.execute(outcome.pending_action_id, token)
    assert result.status == "ok"
    assert result.result["really_sent"] == 0
    assert len(_outbox(seeded)) == 2


def test_forged_token_is_blocked(seeded, clock):
    eng = _engine(seeded, clock)
    outcome = _propose(eng, seeded)
    eng.approve(outcome.pending_action_id, outcome.payload_hash)
    forged = issue_token(action_id=outcome.pending_action_id, p_hash=outcome.payload_hash,
                         secret="attacker-secret", ttl_seconds=600, now=clock())
    assert eng.execute(outcome.pending_action_id, forged).status == "blocked"
    assert _outbox(seeded) == []


def test_payload_changed_after_approval_is_blocked(seeded, clock):
    eng = _engine(seeded, clock)
    outcome = _propose(eng, seeded)
    token = eng.approve(outcome.pending_action_id, outcome.payload_hash)

    # Tamper with the stored action after the owner approved it
    pending = seeded.get(PendingAction, outcome.pending_action_id)
    payload = json.loads(pending.payload_json)
    payload["message"] = "Pay to my other account instead"
    pending.payload_json = json.dumps(payload)
    seeded.add(pending)
    seeded.commit()

    result = eng.execute(outcome.pending_action_id, token)
    assert result.status == "blocked"
    assert "payload changed" in result.reason
    assert _outbox(seeded) == []


def test_owner_must_approve_what_they_saw(seeded, clock):
    eng = _engine(seeded, clock)
    outcome = _propose(eng, seeded)
    with pytest.raises(ApprovalError, match="changed"):
        eng.approve(outcome.pending_action_id, "0" * 64)


def test_token_cannot_be_reused(seeded, clock):
    eng = _engine(seeded, clock)
    outcome = _propose(eng, seeded)
    token = eng.approve(outcome.pending_action_id, outcome.payload_hash)
    assert eng.execute(outcome.pending_action_id, token).status == "ok"
    assert eng.execute(outcome.pending_action_id, token).status == "blocked"
    assert len(_outbox(seeded)) == 2


def test_expired_approval_is_blocked(seeded, clock):
    eng = _engine(seeded, clock)
    outcome = _propose(eng, seeded)
    token = eng.approve(outcome.pending_action_id, outcome.payload_hash)
    clock.t += 601
    result = eng.execute(outcome.pending_action_id, token)
    assert result.status == "blocked"
    assert "expired" in result.reason


def test_declined_action_cannot_run(seeded, clock):
    eng = _engine(seeded, clock)
    outcome = _propose(eng, seeded)
    eng.decline(outcome.pending_action_id)
    assert eng.execute(outcome.pending_action_id, "x.1.y").status == "blocked"


def test_unknown_tool_and_bad_input_are_blocked(seeded, clock):
    eng = _engine(seeded, clock)
    assert eng.call("transfer_all_money", {}).status == "blocked"
    assert eng.call("send_payment_reminders", {"invoice_ids": []}).status == "blocked"


def test_two_tabs_approving_at_once_run_the_action_once(seeded, clock):
    eng = _engine(seeded, clock)
    outcome = _propose(eng, seeded)
    action_id = outcome.pending_action_id
    with Session(seeded.get_bind()) as tab_b:
        # Request B has read the action (still "pending") when request A finishes.
        seen_by_b = tab_b.get(PendingAction, action_id)
        token = eng.approve(action_id, outcome.payload_hash)
        assert eng.execute(action_id, token).status == "ok"
        assert seen_by_b.status == "pending"  # stale, as in a real race
        with pytest.raises(ApprovalError):
            _engine(tab_b, clock).approve(action_id, outcome.payload_hash)
    assert len(_outbox(seeded)) == 2  # sent once, not twice


def test_one_token_used_twice_at_once_runs_once(seeded, clock):
    eng = _engine(seeded, clock)
    outcome = _propose(eng, seeded)
    action_id = outcome.pending_action_id
    token = eng.approve(action_id, outcome.payload_hash)
    with Session(seeded.get_bind()) as second:
        # A second request with the same token has read the action (still "approved").
        seen_by_second = second.get(PendingAction, action_id)
        assert eng.execute(action_id, token).status == "ok"
        assert seen_by_second.status == "approved"  # stale, as in a real race
        assert _engine(second, clock).execute(action_id, token).status == "blocked"
    assert len(_outbox(seeded)) == 2

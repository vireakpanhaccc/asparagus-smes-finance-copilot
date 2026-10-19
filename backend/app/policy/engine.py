"""Policy engine: the single gate every tool call passes through.

  READ_ONLY       -> validate input, run, log "ok"
  SUGGEST         -> validate input, run, log "ok" (output is a draft only)
  NEEDS_APPROVAL  -> validate input, DO NOT run, store a PendingAction, log "held"

Approval flow for NEEDS_APPROVAL:
  approve(action_id, shown_hash)  owner confirms the exact payload they saw -> token
  execute(action_id, token)       token verified against the stored payload -> run once

The LLM never sees or handles approval tokens. Only the owner's authenticated
request to /approvals/{id}/approve can produce one.
"""

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import ValidationError
from sqlmodel import Session, update

from app.config import settings
from app.models import PendingAction
from app.models.tables import utcnow_iso
from app.policy.approvals import ApprovalError, issue_token, payload_hash, verify_token
from app.security import audit
from app.security.untrusted import INJECTION_WARNING, contains_instructions, wrap_names
from app.tools.registry import REGISTRY, Tier

Status = Literal["ok", "needs_approval", "blocked", "error", "declined"]


@dataclass
class ToolOutcome:
    status: Status
    tool_name: str
    tier: str
    result: Any = None
    reason: str = ""
    pending_action_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    payload_hash: str | None = None
    flagged: bool = False  # the result holds instruction-like text (already logged)

    def for_llm(self) -> dict[str, Any]:
        """What the model is allowed to see. No tokens, ever; names wrapped as untrusted."""
        out: dict[str, Any] = {"status": self.status}
        if self.status == "ok":
            out["result"] = wrap_names(in_dollars(self.result))
            if self.flagged:
                out["warning"] = INJECTION_WARNING
        elif self.status == "needs_approval":
            out["message"] = (
                "Held for the owner's approval. An approval card is shown to the owner. "
                "Do not claim this was done."
            )
        else:
            out["reason"] = self.reason
        return out


def _usd(cents: int | float) -> str:
    return f"{'-' if cents < 0 else ''}${abs(cents) / 100:,.2f}"


def in_dollars(value: Any) -> Any:
    """Rewrite every `x_cents` field as `x_usd` dollar text ("-$215.00").

    Small models misread cents as dollars, so the model only ever copies finished
    amounts and never converts them. The UI and API keep using cents.
    """
    if isinstance(value, list):
        return [in_dollars(v) for v in value]
    if not isinstance(value, dict):
        return value
    out: dict[str, Any] = {}
    for key, v in value.items():
        if not key.endswith("_cents"):
            out[key] = in_dollars(v)
            continue
        key = key.removesuffix("_cents") + "_usd"
        if isinstance(v, dict):  # e.g. spend_by_category_cents: {category: cents}
            out[key] = {k: _usd(c) for k, c in v.items()}
        elif isinstance(v, int | float):
            out[key] = _usd(v)
        else:
            out[key] = v
    return out


class PolicyEngine:
    def __init__(
        self,
        session: Session,
        *,
        secret: str | None = None,
        ttl_seconds: int | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.session = session
        self.secret = secret or settings.approval_secret
        if not self.secret:  # an empty HMAC key would make every token forgeable
            raise RuntimeError("APPROVAL_SECRET is not set")
        self.ttl = ttl_seconds or settings.approval_ttl_seconds
        self.clock = clock

    # ---- agent-facing -------------------------------------------------------

    def call(self, tool_name: str, args: dict[str, Any], actor: str = "copilot") -> ToolOutcome:
        spec = REGISTRY.get(tool_name)
        if spec is None:
            self._log(actor, tool_name, "unknown", "blocked", "Unknown tool")
            return ToolOutcome("blocked", tool_name, "unknown", reason="unknown tool")

        try:
            validated = spec.input_model.model_validate(args)
        except ValidationError as err:
            self._log(actor, tool_name, spec.tier.value, "blocked", "Invalid input")
            return ToolOutcome("blocked", tool_name, spec.tier.value, reason=str(err))

        if spec.tier in (Tier.READ_ONLY, Tier.SUGGEST):
            try:
                result = spec.handler(self.session, validated)
            except Exception as err:  # noqa: BLE001 - tool failures must not crash the loop
                self._log(actor, tool_name, spec.tier.value, "error", type(err).__name__)
                return ToolOutcome("error", tool_name, spec.tier.value, reason=str(err))
            self._log(actor, tool_name, spec.tier.value, "ok", _summarize(result))
            flagged = contains_instructions(result)
            if flagged:
                self._log("untrusted_data", "untrusted_text_detected", "read_only", "ignored",
                          f"Instruction-like text in {tool_name} output. Treated as data, "
                          "not followed.")
            return ToolOutcome("ok", tool_name, spec.tier.value, result=result, flagged=flagged)

        # NEEDS_APPROVAL: hold, never run here
        clean_args = validated.model_dump(mode="json")
        if spec.prepare:
            try:
                clean_args = spec.prepare(self.session, validated)
            except ValueError as err:
                self._log(actor, tool_name, spec.tier.value, "blocked", str(err))
                return ToolOutcome("blocked", tool_name, spec.tier.value, reason=str(err))
        p_hash = payload_hash(tool_name, clean_args)
        pending = PendingAction(
            tool_name=tool_name, payload_json=json.dumps(clean_args), payload_hash=p_hash
        )
        self.session.add(pending)
        self.session.commit()
        self._log(actor, tool_name, spec.tier.value, "held",
                  f"Held until the owner decides {_ref(pending.id, p_hash)}")
        return ToolOutcome(
            "needs_approval",
            tool_name,
            spec.tier.value,
            pending_action_id=pending.id,
            payload=clean_args,
            payload_hash=p_hash,
        )

    # ---- owner-facing -------------------------------------------------------

    def approve(self, action_id: str, shown_hash: str, actor: str = "owner") -> str:
        pending = self._get_pending(action_id)
        if pending.status != "pending":
            raise ApprovalError(f"action is {pending.status}, not pending")
        if shown_hash != pending.payload_hash:
            self._log(actor, "approval_rejected", "needs_approval", "blocked",
                      "Approved content does not match the stored action "
                      f"{_ref(action_id, pending.payload_hash)}")
            raise ApprovalError("the action changed since it was shown to you")
        if not self._move(action_id, "pending", "approved", approved_at=utcnow_iso()):
            raise ApprovalError("action is no longer pending")  # another request won the race
        self._log(actor, "approval_recorded", "needs_approval", "approved",
                  f"Approved {pending.tool_name} {_ref(action_id, pending.payload_hash)}")
        return issue_token(action_id=action_id, p_hash=pending.payload_hash,
                           secret=self.secret, ttl_seconds=self.ttl, now=self.clock())

    def decline(self, action_id: str, actor: str = "owner") -> None:
        pending = self._get_pending(action_id)
        if pending.status == "pending":
            pending.status = "declined"
            self.session.add(pending)
            self.session.commit()
            self._log(actor, "approval_declined", "needs_approval", "declined",
                      f"Declined {pending.tool_name} {_ref(action_id, pending.payload_hash)}")

    def execute(self, action_id: str, token: str | None) -> ToolOutcome:
        pending = self.session.get(PendingAction, action_id)
        if pending is None:
            self._log("system", "execute", "needs_approval", "blocked", "No such action")
            return ToolOutcome("blocked", "unknown", "needs_approval", reason="no such action")
        spec = REGISTRY[pending.tool_name]
        args = json.loads(pending.payload_json)
        ref = _ref(action_id, pending.payload_hash)

        def blocked(reason: str) -> ToolOutcome:
            self._log("system", spec.name, spec.tier.value, "blocked", f"{reason} {ref}")
            return ToolOutcome("blocked", spec.name, spec.tier.value, reason=reason)

        if pending.status != "approved":
            return blocked(f"No valid approval on record (status: {pending.status})")
        if not token:
            return blocked("No approval token")
        try:
            # Recompute from what is stored NOW, so any tampering is caught.
            verify_token(token, action_id=action_id, p_hash=payload_hash(pending.tool_name, args),
                         secret=self.secret, now=self.clock())
        except ApprovalError as err:
            return blocked(str(err))

        # A prepared payload also holds server-filled details; validate only the inputs.
        fields = spec.input_model.model_fields
        validated = spec.input_model.model_validate({k: v for k, v in args.items() if k in fields})
        if spec.prepare:
            # The record behind the approval (e.g. the bill) must be exactly as approved.
            try:
                current = spec.prepare(self.session, validated)
            except ValueError as err:
                return blocked(str(err))
            if current != args:
                return blocked("the record changed after approval; ask the owner again")

        # Mark executed BEFORE running so a token can never be used twice.
        if not self._move(action_id, "approved", "executed", executed_at=utcnow_iso()):
            return blocked("Already executed")  # another request with this token won the race

        try:
            result = spec.handler(self.session, validated, action_id=action_id)
        except Exception as err:  # noqa: BLE001
            # It did not happen: undo anything half-written, record it as failed (not
            # executed) and say why, e.g. "Real sending is not implemented" with sandbox off.
            self.session.rollback()
            self._move(action_id, "executed", "failed")
            self._log("system", spec.name, spec.tier.value, "error", f"Failed: {err} {ref}")
            return ToolOutcome("error", spec.name, spec.tier.value, reason=str(err))
        self._log("system", spec.name, spec.tier.value, "done", f"{_summarize(result)} {ref}")
        return ToolOutcome("ok", spec.name, spec.tier.value, result=result)

    # ---- helpers ------------------------------------------------------------

    def _move(self, action_id: str, from_status: str, to_status: str, **fields: str) -> bool:
        """Change status in ONE conditional UPDATE, so two requests can never both win.

        Reading the status and then writing it would let two simultaneous requests both
        see "pending" (or "approved") and both proceed. Returns False if another request
        changed the status first.
        """
        result = self.session.exec(
            update(PendingAction)
            .where(PendingAction.id == action_id, PendingAction.status == from_status)
            .values(status=to_status, **fields)
        )
        self.session.commit()
        return result.rowcount == 1

    def _get_pending(self, action_id: str) -> PendingAction:
        pending = self.session.get(PendingAction, action_id)
        if pending is None:
            raise ApprovalError("no such action")
        return pending

    def _log(self, actor: str, action: str, tier: str, result: str, detail: str) -> None:
        audit.append(self.session, actor=actor, action=action, tier=tier, result=result,
                     detail=detail)


def _ref(action_id: str, p_hash: str) -> str:
    """Short action and payload reference for the audit log, so held -> approved -> done
    of one action can be followed. Grouped in fours: the log masks 8+ digit runs as
    account numbers, and an all-digit ID must not be masked."""
    def grouped(s: str) -> str:
        return "-".join(s[i:i + 4] for i in range(0, len(s), 4))
    return f"[action {grouped(action_id[:8])} · payload {grouped(p_hash[:12])}]"


def _summarize(result: Any) -> str:
    if isinstance(result, dict):
        keys = [k for k in ("count", "messages_logged", "submitted", "sent", "paid")
                if k in result]
        return ", ".join(f"{k}={result[k]}" for k in keys)[:200]
    return ""

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
from sqlmodel import Session

from app.config import settings
from app.models import PendingAction
from app.models.tables import utcnow_iso
from app.policy.approvals import ApprovalError, issue_token, payload_hash, verify_token
from app.security import audit
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

    def for_llm(self) -> dict[str, Any]:
        """What the model is allowed to see. No tokens, ever."""
        out: dict[str, Any] = {"status": self.status}
        if self.status == "ok":
            out["result"] = in_dollars(self.result)
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
            return ToolOutcome("ok", tool_name, spec.tier.value, result=result)

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
        self._log(actor, tool_name, spec.tier.value, "held", "Held until the owner decides")
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
                      "Approved content does not match the stored action")
            raise ApprovalError("the action changed since it was shown to you")
        pending.status = "approved"
        pending.approved_at = utcnow_iso()
        self.session.add(pending)
        self.session.commit()
        self._log(actor, "approval_recorded", "needs_approval", "approved",
                  f"Approved {pending.tool_name}")
        return issue_token(action_id=action_id, p_hash=pending.payload_hash,
                           secret=self.secret, ttl_seconds=self.ttl, now=self.clock())

    def decline(self, action_id: str, actor: str = "owner") -> None:
        pending = self._get_pending(action_id)
        if pending.status == "pending":
            pending.status = "declined"
            self.session.add(pending)
            self.session.commit()
            self._log(actor, "approval_declined", "needs_approval", "declined",
                      f"Declined {pending.tool_name}")

    def execute(self, action_id: str, token: str | None) -> ToolOutcome:
        pending = self.session.get(PendingAction, action_id)
        if pending is None:
            self._log("system", "execute", "needs_approval", "blocked", "No such action")
            return ToolOutcome("blocked", "unknown", "needs_approval", reason="no such action")
        spec = REGISTRY[pending.tool_name]
        args = json.loads(pending.payload_json)

        def blocked(reason: str) -> ToolOutcome:
            self._log("system", pending.tool_name, spec.tier.value, "blocked", reason)
            return ToolOutcome("blocked", pending.tool_name, spec.tier.value, reason=reason)

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
        pending.status = "executed"
        pending.executed_at = utcnow_iso()
        self.session.add(pending)
        self.session.commit()

        try:
            result = spec.handler(self.session, validated, action_id=action_id)
        except Exception as err:  # noqa: BLE001
            self._log("system", pending.tool_name, spec.tier.value, "error", type(err).__name__)
            return ToolOutcome("error", pending.tool_name, spec.tier.value, reason=str(err))
        self._log("system", pending.tool_name, spec.tier.value, "done", _summarize(result))
        return ToolOutcome("ok", pending.tool_name, spec.tier.value, result=result)

    # ---- helpers ------------------------------------------------------------

    def _get_pending(self, action_id: str) -> PendingAction:
        pending = self.session.get(PendingAction, action_id)
        if pending is None:
            raise ApprovalError("no such action")
        return pending

    def _log(self, actor: str, action: str, tier: str, result: str, detail: str) -> None:
        audit.append(self.session, actor=actor, action=action, tier=tier, result=result,
                     detail=detail)


def _summarize(result: Any) -> str:
    if isinstance(result, dict):
        keys = [k for k in ("count", "messages_logged", "submitted", "sent", "paid")
                if k in result]
        return ", ".join(f"{k}={result[k]}" for k in keys)[:200]
    return ""

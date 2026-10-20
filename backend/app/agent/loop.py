"""The agent loop. Every tool call goes through PolicyEngine.call()."""

import json
import re
from dataclasses import dataclass, field
from typing import Any

from sqlmodel import Session

from app.agent.llm import LLMProvider
from app.agent.prompts import build_system_prompt
from app.config import settings
from app.policy.engine import PolicyEngine, ToolOutcome
from app.security import audit
from app.security.untrusted import unwrap_untrusted
from app.tools import REGISTRY

_CLAIMS_PENDING = re.compile(r"approval card|(waiting|awaiting|needs?) (for )?your approval", re.I)
# "has been sent", "were paid", and also contractions and plain past tense the model
# uses: "I've submitted", "it's been sent", "I submitted", "I just paid".
_CLAIMS_DONE = re.compile(
    r"(\b(has|have|had|was|were)|['’](ve|s))\s+(been\s+)?(sent|submitted|paid|transferred)\b"
    r"|\b(I|we)\s+(just\s+|already\s+)?(sent|submitted|paid|transferred)\b",
    re.I,
)
_NEGATION = re.compile(r"\b(not|no|nothing|never)\b|n't", re.I)
NOTE_NOTHING_HELD = (
    "Note: no action from this reply is waiting for your approval, and nothing was sent "
    "or submitted."
)
NOTE_STILL_HELD = "Note: nothing has been sent or submitted yet. It is waiting for your approval."


@dataclass
class AgentResult:
    text: str
    pending_approvals: list[ToolOutcome] = field(default_factory=list)
    tool_trace: list[dict[str, str]] = field(default_factory=list)  # for the side panel
    messages: list[dict[str, Any]] = field(default_factory=list)
    plan: dict[str, Any] | None = None  # set when build_rescue_plan ran, for the plan card


def run_agent(
    session: Session,
    provider: LLMProvider,
    messages: list[dict[str, Any]],
    max_steps: int | None = None,
) -> AgentResult:
    engine = PolicyEngine(session)
    tools = [spec.to_llm_schema() for spec in REGISTRY.values()]
    system = build_system_prompt()
    result = AgentResult(text="", messages=messages)

    for _ in range(max_steps or settings.agent_max_steps):
        resp = provider.complete(system=system, messages=messages, tools=tools)
        messages.append({"role": "assistant", "content": resp.content})
        tool_uses = [b for b in resp.content if b.get("type") == "tool_use"]

        if not tool_uses:
            text = "\n".join(b["text"] for b in resp.content if b.get("type") == "text")
            text = unwrap_untrusted(text)  # the owner sees names, never wrapper tags
            result.text = check_claims(session, text, held=bool(result.pending_approvals))
            return result

        tool_results = []
        for tu in tool_uses:
            outcome = engine.call(tu["name"], tu.get("input", {}))
            result.tool_trace.append(
                {"tool": tu["name"], "tier": outcome.tier, "status": outcome.status}
            )
            if outcome.status == "needs_approval":
                result.pending_approvals.append(outcome)
            if tu["name"] == "build_rescue_plan" and outcome.status == "ok":
                result.plan = outcome.result
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tu["id"],
                    "content": json.dumps(outcome.for_llm(), default=str),
                    "is_error": outcome.status in ("blocked", "error"),
                }
            )
        messages.append({"role": "user", "content": tool_results})

    result.text = "I stopped after too many steps. Please try a more specific question."
    return result


def _claims_done(text: str) -> bool:
    """'The reminders were sent' counts; 'nothing has been sent' does not."""
    return any(
        not _NEGATION.search(text[max(0, m.start() - 30) : m.start()])
        for m in _CLAIMS_DONE.finditer(text)
    )


def check_claims(session: Session, text: str, *, held: bool) -> str:
    """Server-side guard: the reply may not claim actions that did not happen.

    The prompt asks the model not to do this, but small models still do, so the
    server checks the reply against what actually happened in this turn.
    """
    if not text.strip():
        return "I could not produce an answer. Please try again."
    if held and _claims_done(text):
        note = NOTE_STILL_HELD
    elif not held and (_CLAIMS_PENDING.search(text) or _claims_done(text)):
        note = NOTE_NOTHING_HELD
    else:
        return text
    audit.append(session, actor="system", action="reply_claim_corrected", tier="n/a",
                 result="blocked", detail="Reply claimed an action that did not happen")
    return f"{text}\n\n{note}"

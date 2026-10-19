import logging
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlmodel import Session

from app.agent.llm import LLMUnavailable, get_provider
from app.agent.loop import run_agent
from app.api.deps import require_owner
from app.db import get_session
from app.rate_limit import limiter

router = APIRouter(prefix="/chat", tags=["chat"])
log = logging.getLogger(__name__)

# Demo-only conversation store. TODO(backend): persist if you need history across restarts.
_CONVERSATIONS: dict[str, list[dict]] = {}


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    conversation_id: str | None = None


@router.post("")
@limiter.limit("20/minute")
def chat(
    request: Request,
    body: ChatIn,
    session: Session = Depends(get_session),
    _owner: str = Depends(require_owner),
) -> dict:
    conv_id = body.conversation_id or uuid4().hex
    messages = _CONVERSATIONS.setdefault(conv_id, [])
    start = len(messages)
    messages.append({"role": "user", "content": body.message})

    try:
        result = run_agent(session, get_provider(), messages)
    except LLMUnavailable as err:
        del messages[start:]  # drop the half-finished turn so a retry starts clean
        log.warning("LLM unavailable: %s", err)
        raise HTTPException(
            status_code=503,
            detail="The AI service is busy right now. Please try again in a minute.",
        ) from err
    return {
        "conversation_id": conv_id,
        "reply": result.text,
        "tool_trace": result.tool_trace,
        "plan": result.plan,  # cents, like the rest of the API; the UI draws the plan card
        "approval_cards": [
            {
                "action_id": p.pending_action_id,
                "tool": p.tool_name,
                "payload": p.payload,
                "payload_hash": p.payload_hash,  # the UI sends this back on approve
            }
            for p in result.pending_approvals
        ],
    }

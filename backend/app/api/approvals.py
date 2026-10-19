import json

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session, select

from app.api.deps import require_owner
from app.db import get_session
from app.models import PendingAction
from app.policy.approvals import ApprovalError
from app.policy.engine import PolicyEngine
from app.rate_limit import limiter

router = APIRouter(prefix="/approvals", tags=["approvals"])


class ApproveIn(BaseModel):
    payload_hash: str  # the hash of the card the owner actually saw


@router.get("/pending")
def list_pending(
    session: Session = Depends(get_session), _owner: str = Depends(require_owner)
) -> list[dict]:
    rows = session.exec(select(PendingAction).where(PendingAction.status == "pending")).all()
    return [
        {"action_id": r.id, "tool": r.tool_name, "payload": json.loads(r.payload_json),
         "payload_hash": r.payload_hash, "created_at": r.created_at}
        for r in rows
    ]


@router.post("/{action_id}/approve")
@limiter.limit("10/minute")
def approve_and_run(
    request: Request,
    action_id: str,
    body: ApproveIn,
    session: Session = Depends(get_session),
    _owner: str = Depends(require_owner),
) -> dict:
    """'Approve and run' button: record approval, then execute with the issued token."""
    engine = PolicyEngine(session)
    try:
        token = engine.approve(action_id, body.payload_hash)
    except ApprovalError as err:
        raise HTTPException(status_code=409, detail=str(err)) from err
    outcome = engine.execute(action_id, token)
    if outcome.status != "ok":
        raise HTTPException(status_code=403, detail=outcome.reason)
    return {"status": "done", "result": outcome.result}


@router.post("/{action_id}/decline")
def decline(
    action_id: str, session: Session = Depends(get_session), _owner: str = Depends(require_owner)
) -> dict:
    try:
        PolicyEngine(session).decline(action_id)
    except ApprovalError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    return {"status": "declined"}

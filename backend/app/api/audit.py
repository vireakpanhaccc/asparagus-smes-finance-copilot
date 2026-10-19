from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from sqlmodel import Session, select

from app.api.deps import require_owner
from app.db import get_session
from app.models import AuditEntry
from app.security import audit

router = APIRouter(prefix="/audit", tags=["audit"], dependencies=[Depends(require_owner)])


@router.get("")
def list_entries(
    result: str | None = Query(None, description="filter: held, blocked, ignored, ..."),
    session: Session = Depends(get_session),
) -> list[dict]:
    q = select(AuditEntry).order_by(AuditEntry.id)
    if result:
        q = q.where(AuditEntry.result == result)
    return [e.model_dump() for e in session.exec(q).all()]


@router.get("/verify")
def verify(session: Session = Depends(get_session)) -> dict:
    ok, broken = audit.verify_chain(session)
    return {"chain_intact": ok, "first_broken_id": broken}


@router.get("/export.csv", response_class=PlainTextResponse)
def export(session: Session = Depends(get_session)) -> PlainTextResponse:
    return PlainTextResponse(
        audit.export_csv(session),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit_log.csv"},
    )

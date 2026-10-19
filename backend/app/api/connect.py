"""Mock bank-link consent (read-only scope) and the live-sync event stream."""

import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select
from sse_starlette.sse import EventSourceResponse

from app.api.deps import require_owner, require_owner_stream
from app.config import settings
from app.connectors.mock_webank import MockWeBankAdapter
from app.db import engine, get_session
from app.models import ConsentGrant
from app.models.tables import utcnow_iso
from app.security import audit

router = APIRouter(prefix="/connect", tags=["connect"])


class GrantIn(BaseModel):
    provider: str = "WeBank (mock)"
    days_valid: int = Field(default=90, ge=1, le=365)


@router.post("")
def grant(
    body: GrantIn, session: Session = Depends(get_session), _owner: str = Depends(require_owner)
) -> dict:
    expires = datetime.now(timezone.utc) + timedelta(days=body.days_valid)
    g = ConsentGrant(provider=body.provider, account_id=settings.demo_account_id,
                     expires_at=expires.isoformat(timespec="seconds"))
    session.add(g)
    session.commit()
    session.refresh(g)
    audit.append(session, actor="owner", action="consent_granted", tier="read_only",
                 result="ok", detail=f"{g.provider}: {g.scope} until {g.expires_at}")
    return g.model_dump()


@router.delete("/{grant_id}")
def revoke(
    grant_id: int, session: Session = Depends(get_session), _owner: str = Depends(require_owner)
) -> dict:
    g = session.get(ConsentGrant, grant_id)
    if g is None:
        raise HTTPException(404, "no such grant")
    g.revoked_at = utcnow_iso()
    session.add(g)
    session.commit()
    audit.append(session, actor="owner", action="consent_revoked", tier="read_only",
                 result="ok", detail=f"{g.provider} access revoked")
    return {"status": "revoked"}


@router.get("/live")
async def live_sync(_owner: str = Depends(require_owner_stream)):
    """SSE stream of new transactions while a consent grant is active."""
    adapter = MockWeBankAdapter()

    async def events():
        async for tx in adapter.stream_new(settings.demo_account_id):
            with Session(engine) as s:
                active = s.exec(
                    select(ConsentGrant).where(ConsentGrant.revoked_at == None)  # noqa: E711
                ).first()
                if active is None:
                    yield {"event": "stopped", "data": "no active consent"}
                    return
                s.add(tx)
                s.commit()
                s.refresh(tx)
                yield {"event": "transaction", "data": json.dumps(
                    {"id": tx.id, "amount_cents": tx.amount_cents,
                     "counterparty": tx.counterparty, "booked_at": tx.booked_at.isoformat()})}

    return EventSourceResponse(events())

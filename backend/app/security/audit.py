"""Append-only, hash-chained audit log.

Each row stores the hash of the previous row, so editing or deleting any row
breaks the chain from that point on. verify_chain() finds the first broken row.
This log, exported as CSV, is the competition's "sandbox operation log" evidence.
"""

import csv
import hashlib
import io

from sqlmodel import Session, select

from app.models import AuditEntry
from app.models.tables import utcnow_iso
from app.security.masking import mask_pii

GENESIS_HASH = "0" * 64


def compute_row_hash(
    prev_hash: str, ts: str, actor: str, action: str, tier: str, result: str, detail: str
) -> str:
    material = "\x1f".join([prev_hash, ts, actor, action, tier, result, detail])
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def append(
    session: Session, *, actor: str, action: str, tier: str, result: str, detail: str = ""
) -> AuditEntry:
    detail = mask_pii(detail)
    last = session.exec(select(AuditEntry).order_by(AuditEntry.id.desc())).first()
    prev_hash = last.row_hash if last else GENESIS_HASH
    ts = utcnow_iso()
    entry = AuditEntry(
        ts=ts,
        actor=actor,
        action=action,
        tier=tier,
        result=result,
        detail=detail,
        prev_hash=prev_hash,
        row_hash=compute_row_hash(prev_hash, ts, actor, action, tier, result, detail),
    )
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return entry


def verify_chain(session: Session) -> tuple[bool, int | None]:
    """Return (ok, first_broken_id)."""
    prev = GENESIS_HASH
    for e in session.exec(select(AuditEntry).order_by(AuditEntry.id)).all():
        expected = compute_row_hash(prev, e.ts, e.actor, e.action, e.tier, e.result, e.detail)
        if e.prev_hash != prev or e.row_hash != expected:
            return False, e.id
        prev = e.row_hash
    return True, None


def export_csv(session: Session) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["id", "ts", "actor", "action", "tier", "result", "detail", "row_hash"])
    for e in session.exec(select(AuditEntry).order_by(AuditEntry.id)).all():
        writer.writerow([e.id, e.ts, e.actor, e.action, e.tier, e.result, e.detail, e.row_hash])
    return buf.getvalue()

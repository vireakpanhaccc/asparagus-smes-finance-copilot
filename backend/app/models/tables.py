"""Database tables.

Money is always stored as integer cents to avoid float rounding.
Fields marked UNTRUSTED contain free text from customers or counterparties and
must go through app.security.untrusted before reaching the LLM.
"""

from datetime import date, datetime, timezone
from uuid import uuid4

from sqlmodel import Field, SQLModel


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Transaction(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    account_id: str = Field(index=True)
    booked_at: datetime = Field(index=True)
    amount_cents: int  # positive = money in, negative = money out
    currency: str = "USD"
    counterparty: str
    category: str
    memo: str = ""  # UNTRUSTED
    source: str = "mock_webank"


class Invoice(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    account_id: str = Field(index=True)
    customer: str
    customer_contact: str  # PII - masked before logging
    amount_cents: int
    issued_on: date
    due_on: date
    paid: bool = False
    note: str = ""  # UNTRUSTED


class Bill(SQLModel, table=True):
    """A known upcoming payment (payable) that the forecast must include."""

    id: int | None = Field(default=None, primary_key=True)
    account_id: str = Field(index=True)
    payee: str
    amount_cents: int  # positive number; it is paid out
    due_on: date
    paid: bool = False


class PendingAction(SQLModel, table=True):
    """An action the agent proposed that needs the owner's approval."""

    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    tool_name: str
    payload_json: str
    payload_hash: str
    status: str = "pending"  # pending | approved | declined | executed
    created_at: str = Field(default_factory=utcnow_iso)
    approved_at: str | None = None
    executed_at: str | None = None


class AuditEntry(SQLModel, table=True):
    """Append-only, hash-chained audit log. Never UPDATE or DELETE rows."""

    id: int | None = Field(default=None, primary_key=True)
    ts: str = Field(default_factory=utcnow_iso)
    actor: str  # copilot | owner | system | <data source>
    action: str
    tier: str
    result: str  # ok | held | approved | declined | done | blocked | ignored | error
    detail: str = ""
    prev_hash: str
    row_hash: str


class ConsentGrant(SQLModel, table=True):
    """Read-only data-sharing consent from the owner (mock bank link)."""

    id: int | None = Field(default=None, primary_key=True)
    provider: str  # e.g. "WeBank (mock)", "CSV upload"
    account_id: str
    scope: str = "transactions:read"
    granted_at: str = Field(default_factory=utcnow_iso)
    expires_at: str
    revoked_at: str | None = None


class SandboxOutbox(SQLModel, table=True):
    """Where 'send' and 'submit' actions land. Nothing ever leaves the system."""

    id: int | None = Field(default=None, primary_key=True)
    kind: str  # payment_reminder | loan_application | supplier_message
    recipient_masked: str
    body: str
    pending_action_id: str
    created_at: str = Field(default_factory=utcnow_iso)

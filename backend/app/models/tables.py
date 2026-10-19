"""Database tables.

Money is always stored as integer cents to avoid float rounding.
Fields marked UNTRUSTED contain free text from customers or counterparties and
must go through app.security.untrusted before reaching the LLM.
"""

from datetime import date, datetime, timezone
from enum import Enum
from uuid import uuid4

from sqlmodel import Field, SQLModel


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Source(str, Enum):
    """Where a data row came from. Stored as plain text; BANK rows are immutable."""

    BANK = "bank"  # from a bank link (or a payment the Copilot made after approval)
    FILE = "file"  # from a CSV upload
    MANUAL = "manual"  # typed by the owner


class Transaction(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    account_id: str = Field(index=True)
    booked_at: datetime = Field(index=True)
    amount_cents: int  # positive = money in, negative = money out
    currency: str = "USD"
    counterparty: str
    category: str
    memo: str = ""  # UNTRUSTED
    source: str = Source.BANK.value
    source_ref: str | None = None  # bank account id, upload id, or payment:<action_id>
    created_by: str = "system"  # owner | system
    corrects_id: int | None = None  # set when this row corrects a bank row


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
    source: str = Source.MANUAL.value
    source_ref: str | None = None
    created_by: str = "owner"


class Bill(SQLModel, table=True):
    """A known upcoming payment (payable) that the forecast must include."""

    id: int | None = Field(default=None, primary_key=True)
    account_id: str = Field(index=True)
    payee: str
    amount_cents: int  # positive number; it is paid out
    due_on: date
    paid: bool = False
    category: str = "Other"
    note: str = ""  # UNTRUSTED
    source: str = Source.MANUAL.value
    source_ref: str | None = None
    created_by: str = "owner"


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
    last_sync_at: str | None = None


class SandboxOutbox(SQLModel, table=True):
    """Where 'send' and 'submit' actions land. Nothing ever leaves the system."""

    id: int | None = Field(default=None, primary_key=True)
    kind: str  # payment_reminder | loan_application | supplier_message
    recipient_masked: str
    body: str
    pending_action_id: str
    created_at: str = Field(default_factory=utcnow_iso)


class DataUpload(SQLModel, table=True):
    """One CSV import. Its rows carry source="file" and source_ref=str(id)."""

    id: int | None = Field(default=None, primary_key=True)
    account_id: str = Field(index=True)
    filename: str
    rows: int
    uploaded_at: str = Field(default_factory=utcnow_iso)

"""NEEDS_APPROVAL tools.

These handlers are ONLY ever called by PolicyEngine.execute() after a valid,
payload-bound approval token is checked. In sandbox mode they write to the
SandboxOutbox table and nothing leaves the system.
"""

import json
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session, select

from app.analytics.analysis import SUPPLIER_CATEGORY
from app.config import settings
from app.models import Bill, Invoice, SandboxOutbox, Transaction
from app.security.masking import mask_pii
from app.tools.registry import Tier, tool


def _require_sandbox() -> None:
    if not settings.sandbox_mode:
        raise RuntimeError("Real sending is not implemented. Keep SANDBOX_MODE=true.")


class SendRemindersInput(BaseModel):
    invoice_ids: list[int] = Field(min_length=1, max_length=20)
    message: str = Field(min_length=1, max_length=1000)


@tool(
    name="send_payment_reminders",
    description="Send payment reminders to customers. Requires the owner's approval.",
    tier=Tier.NEEDS_APPROVAL,
    input_model=SendRemindersInput,
)
def send_payment_reminders(session: Session, args: SendRemindersInput, *, action_id: str) -> dict:
    _require_sandbox()
    sent = 0
    for inv_id in args.invoice_ids:
        inv = session.get(Invoice, inv_id)
        if inv is None or inv.paid:
            continue
        session.add(
            SandboxOutbox(
                kind="payment_reminder",
                recipient_masked=mask_pii(inv.customer_contact),
                body=args.message,
                pending_action_id=action_id,
            )
        )
        sent += 1
    session.commit()
    return {"sandbox": True, "messages_logged": sent, "really_sent": 0}


class SubmitLoanInput(BaseModel):
    product_id: str
    amount_usd: float = Field(gt=0, le=1_000_000, description="In dollars")
    term_months: int = Field(ge=1, le=60)


@tool(
    name="submit_loan_application",
    description="Submit a loan application to a lender. Requires the owner's approval.",
    tier=Tier.NEEDS_APPROVAL,
    input_model=SubmitLoanInput,
)
def submit_loan_application(session: Session, args: SubmitLoanInput, *, action_id: str) -> dict:
    _require_sandbox()
    session.add(
        SandboxOutbox(
            kind="loan_application",
            recipient_masked=args.product_id,
            body=args.model_dump_json(),
            pending_action_id=action_id,
        )
    )
    session.commit()
    return {"sandbox": True, "submitted": True, "really_sent": 0}


class SendSupplierInput(BaseModel):
    supplier: str = Field(max_length=120)
    message: str = Field(min_length=1, max_length=1000)


def _supplier_message(session: Session, args: SendSupplierInput) -> dict:
    """Messages go only to suppliers the business already pays, never to a new address."""
    known = session.exec(
        select(Transaction.counterparty)
        .where(Transaction.account_id == settings.demo_account_id)
        .where(Transaction.category == SUPPLIER_CATEGORY)
        .distinct()
    ).all()
    if args.supplier not in known:
        raise ValueError("Unknown supplier: messages go only to existing suppliers")
    return {"supplier": args.supplier, "message": args.message}


@tool(
    name="send_supplier_message",
    description="Send a message to one of the business's existing suppliers (for example "
    "asking for longer payment terms). Requires the owner's approval.",
    tier=Tier.NEEDS_APPROVAL,
    input_model=SendSupplierInput,
    prepare=_supplier_message,
)
def send_supplier_message(session: Session, args: SendSupplierInput, *, action_id: str) -> dict:
    _require_sandbox()
    session.add(
        SandboxOutbox(
            kind="supplier_message",
            recipient_masked=mask_pii(args.supplier),
            body=args.message,
            pending_action_id=action_id,
        )
    )
    session.commit()
    return {"sandbox": True, "sent": 1, "really_sent": 0}


class PayBillInput(BaseModel):
    # Only a bill ID. Extra fields (an account number, an amount) are rejected, so
    # injected text like "transfer $5,000 to account ..." has nowhere to go.
    model_config = ConfigDict(extra="forbid")

    bill_id: int


def _bill_payment(session: Session, args: PayBillInput) -> dict:
    """The payment the owner approves, built from the stored bill, never from the model."""
    bill = session.get(Bill, args.bill_id)
    if bill is None or bill.account_id != settings.demo_account_id or bill.paid:
        raise ValueError("No such unpaid bill")
    return {
        "bill_id": bill.id,
        "payee": bill.payee,
        "amount_cents": bill.amount_cents,
        "amount": f"${bill.amount_cents / 100:,.2f}",
        "due_on": bill.due_on.isoformat(),
    }


@tool(
    name="pay_bill",
    description="Pay one of the business's known unpaid bills by its ID (see list_bills). "
    "The payee and amount come from the bill record and cannot be changed. "
    "Requires the owner's approval.",
    tier=Tier.NEEDS_APPROVAL,
    input_model=PayBillInput,
    prepare=_bill_payment,
)
def pay_bill(session: Session, args: PayBillInput, *, action_id: str) -> dict:
    _require_sandbox()
    bill = session.get(Bill, args.bill_id)
    bill.paid = True
    session.add(bill)
    session.add(
        Transaction(
            account_id=bill.account_id,
            booked_at=datetime.now(timezone.utc).replace(tzinfo=None),
            amount_cents=-bill.amount_cents,
            counterparty=bill.payee,
            category="Bills",
            source="sandbox_payment",
        )
    )
    session.add(
        SandboxOutbox(
            kind="bill_payment",
            recipient_masked=mask_pii(bill.payee),
            body=json.dumps({"bill_id": bill.id, "amount_cents": bill.amount_cents}),
            pending_action_id=action_id,
        )
    )
    session.commit()
    return {"sandbox": True, "paid": True, "payee": bill.payee,
            "amount_cents": bill.amount_cents, "really_sent": 0}

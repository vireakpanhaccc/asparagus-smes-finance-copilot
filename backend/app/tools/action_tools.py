"""NEEDS_APPROVAL tools.

These handlers are ONLY ever called by PolicyEngine.execute() after a valid,
payload-bound approval token is checked. In sandbox mode they write to the
SandboxOutbox table and nothing leaves the system.
"""

import hashlib
import json
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlmodel import Session, select

from app.analytics import financing
from app.analytics.analysis import SUPPLIER_CATEGORY
from app.config import settings
from app.models import Bill, Invoice, SandboxOutbox, Transaction
from app.security.masking import mask_pii
from app.security.outbound import check_outbound
from app.security.untrusted import unwrap_untrusted
from app.tools.registry import Tier, tool


def _require_sandbox() -> None:
    if not settings.sandbox_mode:
        raise RuntimeError("Real sending is not implemented. Keep SANDBOX_MODE=true.")


class SendRemindersInput(BaseModel):
    invoice_ids: list[int] = Field(min_length=1, max_length=20)
    message: str = Field(min_length=1, max_length=1000)


def _reminders(session: Session, args: SendRemindersInput) -> dict:
    """Who gets the reminder, built from the stored invoices, never from the model.

    The owner's card shows each customer, amount and masked contact. A fingerprint of the
    full contact is part of the approved payload, so a contact edited after approval
    blocks the send (the payload is rebuilt and compared at execution).
    """
    check_outbound(args.message)
    invoice_ids = list(dict.fromkeys(args.invoice_ids))  # drop duplicates, keep order
    recipients = []
    for inv_id in invoice_ids:
        inv = session.get(Invoice, inv_id)
        if inv is None or inv.account_id != settings.demo_account_id or inv.paid:
            raise ValueError(f"No such unpaid invoice: #{inv_id}")
        recipients.append({
            "invoice_id": inv.id,
            "customer": inv.customer,
            "amount": f"${inv.amount_cents / 100:,.2f}",
            "contact": mask_pii(inv.customer_contact),
            "contact_fingerprint": hashlib.sha256(
                inv.customer_contact.encode("utf-8")).hexdigest()[:12],
        })
    return {"invoice_ids": invoice_ids, "message": args.message, "recipients": recipients}


@tool(
    name="send_payment_reminders",
    description="Send payment reminders to customers with unpaid invoices. Requires the "
    "owner's approval. The message may not contain links, contact details or account "
    "numbers.",
    tier=Tier.NEEDS_APPROVAL,
    input_model=SendRemindersInput,
    prepare=_reminders,
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
    product_id: str = Field(max_length=60)
    amount_usd: float = Field(gt=0, le=1_000_000, description="In dollars")
    term_months: int = Field(ge=1, le=60)


def _loan_terms(session: Session, args: SubmitLoanInput) -> dict:
    """The application the owner approves: lender, amount, term, monthly payment and
    total cost, all computed from the product catalogue. Unknown products and amounts or
    terms the product does not allow are refused."""
    terms = financing.quote(session, settings.demo_account_id, args.product_id,
                            round(args.amount_usd * 100), args.term_months)
    return {**args.model_dump(), **terms}


@tool(
    name="submit_loan_application",
    description="Submit a loan application for a product from rank_financing. Requires the "
    "owner's approval. The server computes the terms; the product must allow the amount "
    "and term.",
    tier=Tier.NEEDS_APPROVAL,
    input_model=SubmitLoanInput,
    prepare=_loan_terms,
)
def submit_loan_application(session: Session, args: SubmitLoanInput, *, action_id: str) -> dict:
    _require_sandbox()
    terms = _loan_terms(session, args)
    session.add(
        SandboxOutbox(
            kind="loan_application",
            recipient_masked=terms["lender_product"],
            body=json.dumps(terms),
            pending_action_id=action_id,
        )
    )
    session.commit()
    return {"sandbox": True, "submitted": True, "really_sent": 0}


class SendSupplierInput(BaseModel):
    supplier: str = Field(max_length=200)
    message: str = Field(min_length=1, max_length=1000)

    # Tool results wrap names as untrusted; the model may copy the wrapped form.
    _plain = field_validator("supplier")(unwrap_untrusted)


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
    check_outbound(args.message)
    return {"supplier": args.supplier, "message": args.message}


@tool(
    name="send_supplier_message",
    description="Send a message to one of the business's existing suppliers (for example "
    "asking for longer payment terms). Requires the owner's approval. The message may not "
    "contain links, contact details or account numbers.",
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
            source="bank",  # locked like a bank record: nobody can edit or delete it
            source_ref=f"payment:{action_id}",
            created_by="system",
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

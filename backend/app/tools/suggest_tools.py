"""SUGGEST tools: produce drafts. Nothing leaves the app."""

from pydantic import BaseModel, Field
from sqlmodel import Session

from app.models import Invoice
from app.tools.registry import Tier, tool


class DraftRemindersInput(BaseModel):
    invoice_ids: list[int] = Field(min_length=1, max_length=20)


@tool(
    name="draft_payment_reminders",
    description="Draft polite payment reminders for the given invoices. Does not send.",
    tier=Tier.SUGGEST,
    input_model=DraftRemindersInput,
)
def draft_payment_reminders(session: Session, args: DraftRemindersInput) -> dict:
    drafts = []
    for inv_id in args.invoice_ids:
        inv = session.get(Invoice, inv_id)
        if inv is None or inv.paid:
            continue
        drafts.append(
            {
                "invoice_id": inv.id,
                "customer": inv.customer,
                "message": (
                    f"Hello {inv.customer}, a friendly reminder that invoice #{inv.id} "
                    f"for ${inv.amount_cents / 100:,.2f} was due on {inv.due_on:%b %d}. "
                    "Thank you!"
                ),
            }
        )
    return {"drafts": drafts, "sent": False}


class DraftLoanInput(BaseModel):
    product_id: str
    amount_usd: float = Field(gt=0, le=1_000_000, description="In dollars")
    term_months: int = Field(ge=1, le=60)


@tool(
    name="draft_loan_application",
    description="Prepare a loan application draft for a ranked product. Does not submit.",
    tier=Tier.SUGGEST,
    input_model=DraftLoanInput,
)
def draft_loan_application(session: Session, args: DraftLoanInput) -> dict:
    # TODO(backend): fill from business_summary() - revenue, margin, time in business.
    return {"draft": args.model_dump(), "submitted": False}


class DraftSupplierInput(BaseModel):
    supplier: str
    request: str = Field(default="30-day payment terms", max_length=200)


@tool(
    name="draft_supplier_message",
    description="Draft a message asking a supplier for longer payment terms. Does not send.",
    tier=Tier.SUGGEST,
    input_model=DraftSupplierInput,
)
def draft_supplier_message(session: Session, args: DraftSupplierInput) -> dict:
    return {
        "draft": f"Hello {args.supplier}, could we move to {args.request} on our next invoice?",
        "sent": False,
    }

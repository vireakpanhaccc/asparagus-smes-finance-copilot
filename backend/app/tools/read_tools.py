"""READ_ONLY tools: look at data, never change anything."""

from datetime import date, datetime, timedelta, timezone

from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.analytics import analysis, financing, forecast, invoices, rescue
from app.config import settings
from app.models import Bill, Transaction
from app.security.masking import mask_pii
from app.security.untrusted import untrusted_fields
from app.tools.registry import Tier, tool


class ReadTransactionsInput(BaseModel):
    days: int = Field(default=30, ge=1, le=365, description="How many days back to read")


@tool(
    name="read_transactions",
    description="Read the business's recent transactions (amounts in cents).",
    tier=Tier.READ_ONLY,
    input_model=ReadTransactionsInput,
)
def read_transactions(session: Session, args: ReadTransactionsInput) -> dict:
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=args.days)
    rows = session.exec(
        select(Transaction)
        .where(Transaction.account_id == settings.demo_account_id)
        .where(Transaction.booked_at >= since)
        .order_by(Transaction.booked_at)
    ).all()
    return {
        "count": len(rows),
        "transactions": [
            {
                "date": r.booked_at.date().isoformat(),
                "amount_cents": r.amount_cents,
                "counterparty": mask_pii(r.counterparty),
                "category": r.category,
                **untrusted_fields(session, "bank_memo", "memo", r.memo),
            }
            for r in rows
        ],
    }


class NoInput(BaseModel):
    pass


FORECAST_WEEKS = 12  # fixed: letting the model pick a horizon made it cut off the week asked


@tool(
    name="forecast_cash_flow",
    description="Project the weekly cash balance for the next 12 weeks and flag shortfall "
    "weeks, including each week's dates, upcoming bills (rent, wages, suppliers, known "
    "bills) and their total. Use this for any question about future bills, payroll or cash.",
    tier=Tier.READ_ONLY,
    input_model=NoInput,
)
def forecast_cash_flow(session: Session, args: NoInput) -> dict:
    return forecast.forecast_weekly(session, settings.demo_account_id, weeks=FORECAST_WEEKS)


@tool(
    name="find_overdue_invoices",
    description="List money customers owe the business that is past due. These are "
    "not bills the business must pay.",
    tier=Tier.READ_ONLY,
    input_model=NoInput,
)
def find_overdue_invoices(session: Session, args: NoInput) -> dict:
    overdue = invoices.find_overdue(session, settings.demo_account_id, today=date.today())
    return {
        "count": len(overdue),
        "total_cents": sum(i.amount_cents for i in overdue),
        "invoices": [
            {
                "invoice_id": i.id,
                "customer": i.customer,
                "amount_cents": i.amount_cents,
                "days_late": (date.today() - i.due_on).days,
                **untrusted_fields(session, "invoice_note", "note", i.note),
            }
            for i in overdue
        ],
    }


@tool(
    name="analyze_spending",
    description="Spending by category, 6-month margin trend and supplier cost change.",
    tier=Tier.READ_ONLY,
    input_model=NoInput,
)
def analyze_spending(session: Session, args: NoInput) -> dict:
    return analysis.business_summary(session, settings.demo_account_id)


@tool(
    name="list_bills",
    description="List the business's known unpaid bills (payables) with their ID, payee, "
    "amount and due date. Use the ID with pay_bill.",
    tier=Tier.READ_ONLY,
    input_model=NoInput,
)
def list_bills(session: Session, args: NoInput) -> dict:
    rows = session.exec(
        select(Bill)
        .where(Bill.account_id == settings.demo_account_id)
        .where(Bill.paid == False)  # noqa: E712 (SQL expression)
        .order_by(Bill.due_on)
    ).all()
    return {
        "count": len(rows),
        "bills": [
            {"bill_id": b.id, "payee": b.payee, "amount_cents": b.amount_cents,
             "due_on": b.due_on.isoformat()}
            for b in rows
        ],
    }


@tool(
    name="build_rescue_plan",
    description="Build a plan to close a forecast cash shortfall. Tries the cheapest fixes "
    "first (collect overdue invoices, longer supplier terms, then financing), re-runs the "
    "forecast with them applied and returns before/after balances, the steps, a backup and "
    "next_actions. Afterwards call each next_action tool with exactly the given arguments; "
    "anything that sends is held for the owner's approval.",
    tier=Tier.READ_ONLY,
    input_model=NoInput,
)
def build_rescue_plan(session: Session, args: NoInput) -> dict:
    return rescue.build_plan(session, settings.demo_account_id)


class RankFinancingInput(BaseModel):
    gap_usd: float = Field(ge=0, le=1_000_000, description="Cash gap to cover, in dollars")
    months_needed: int = Field(default=2, ge=1, le=36)


@tool(
    name="rank_financing",
    description="Rank financing options (and non-loan alternatives) for a cash gap, "
    "with total cost and affordability.",
    tier=Tier.READ_ONLY,
    input_model=RankFinancingInput,
)
def rank_financing(session: Session, args: RankFinancingInput) -> dict:
    return financing.rank_options(
        session, settings.demo_account_id, round(args.gap_usd * 100), args.months_needed
    )

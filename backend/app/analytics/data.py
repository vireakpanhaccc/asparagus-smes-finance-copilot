"""Shared data loading for analytics (pandas)."""

import pandas as pd
from sqlmodel import Session, select

from app.models import Bill, Transaction

COLUMNS = ["booked_at", "amount_cents", "counterparty", "category"]


def load_transactions(session: Session, account_id: str) -> pd.DataFrame:
    rows = session.exec(select(Transaction).where(Transaction.account_id == account_id)).all()
    df = pd.DataFrame([{c: getattr(r, c) for c in COLUMNS} for r in rows], columns=COLUMNS)
    if not df.empty:
        df["booked_at"] = pd.to_datetime(df["booked_at"])
        df = df.sort_values("booked_at").reset_index(drop=True)
    return df


def load_upcoming_bills(session: Session, account_id: str) -> list[tuple]:
    """Known unpaid payables as (due_on, payee, amount_cents_negative)."""
    rows = session.exec(
        select(Bill).where(Bill.account_id == account_id).where(Bill.paid == False)  # noqa: E712
    ).all()
    return [(b.due_on, b.payee, -abs(b.amount_cents)) for b in rows]

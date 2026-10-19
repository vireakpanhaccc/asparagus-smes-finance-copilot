"""Business financial analysis (Topic E's third requirement)."""

from datetime import date, timedelta

import pandas as pd
from sqlmodel import Session

from app.analytics.data import load_transactions

SUPPLIER_CATEGORY = "Supplies"


def business_summary(session: Session, account_id: str, today: date | None = None) -> dict:
    today = today or date.today()
    df = load_transactions(session, account_id)
    if df.empty:
        return {"note": "No transactions yet."}
    df = df[df["category"] != "Opening balance"]

    last30 = df[df["booked_at"] >= pd.Timestamp(today - timedelta(days=30))]
    money_in = int(last30.loc[last30["amount_cents"] > 0, "amount_cents"].sum())
    money_out = int(-last30.loc[last30["amount_cents"] < 0, "amount_cents"].sum())

    spend_by_cat = (
        (-last30[last30["amount_cents"] < 0].groupby("category")["amount_cents"].sum())
        .sort_values(ascending=False)
        .astype(int)
        .to_dict()
    )

    monthly = df.groupby(df["booked_at"].dt.to_period("M"))["amount_cents"]
    monthly_in = df[df["amount_cents"] > 0].groupby(df["booked_at"].dt.to_period("M"))[
        "amount_cents"
    ].sum()
    margin_trend = [
        {
            "month": str(period),
            "net_cents": int(net),
            "margin_pct": (
                float(round(100 * net / monthly_in[period], 1)) if monthly_in.get(period) else None
            ),
        }
        for period, net in monthly.sum().tail(6).items()
    ]

    sup = df[df["category"] == SUPPLIER_CATEGORY]
    cut = pd.Timestamp(today - timedelta(weeks=8))
    recent_sup = -int(sup.loc[sup["booked_at"] >= cut, "amount_cents"].sum())
    prior_sup = -int(sup.loc[
        (sup["booked_at"] < cut) & (sup["booked_at"] >= cut - pd.Timedelta(weeks=8)), "amount_cents"
    ].sum())
    supplier_change = (
        round(100 * (recent_sup - prior_sup) / prior_sup, 1) if prior_sup else None
    )

    return {
        "last_30_days": {
            "money_in_cents": money_in,
            "money_out_cents": money_out,
            "net_cents": money_in - money_out,
            "margin_pct": round(100 * (money_in - money_out) / money_in, 1) if money_in else None,
        },
        "spend_by_category_cents": spend_by_cat,
        "margin_trend": margin_trend,
        "supplier_cost_change_8w_pct": supplier_change,
    }

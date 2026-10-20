"""12-week cash-flow forecast (deterministic baseline - the LLM only explains it).

Algorithm (documented in docs/technical-document.md, section 5.1):
  1. Current balance = sum of all transactions.
  2. Recurring outflows: per counterparty with >= 3 payments, the median gap between
     payments classifies it as weekly (6-8 days), bi-weekly (13-16) or monthly (27-32).
     Next due date = last payment + gap; amount = median of the last 3 payments.
  3. Income: mean daily inflow per weekday over the last 8 weeks (captures slow days).
  4. Other outflows: mean daily non-recurring outflow over the last 8 weeks.
     Known upcoming bills (payables) are added on their due dates.
  5. Roll forward day by day; report each week's lowest balance and flag weeks that
     drop below zero (shortfall) or below the buffer.

TODO(stretch): compare against statsmodels ExponentialSmoothing in the docs.
"""

from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd
from sqlmodel import Session

from app.analytics.data import load_transactions, load_upcoming_bills

LOOKBACK_DAYS = 56
CADENCES = {"weekly": (6, 8), "biweekly": (13, 16), "monthly": (27, 32)}


@dataclass(frozen=True)
class WhatIf:
    """Changes the rescue plan tests against the forecast.

    events: one-off money in or out, as (date, label, cents)
    delays: payees whose payments move later, as (counterparty, days)
    """

    events: tuple[tuple[date, str, int], ...] = ()
    delays: tuple[tuple[str, int], ...] = ()


def detect_recurring(df: pd.DataFrame) -> list[dict]:
    out = df[df["amount_cents"] < 0]
    recurring = []
    for cp, g in out.groupby("counterparty"):
        if len(g) < 3:
            continue
        gaps = g["booked_at"].diff().dt.days.dropna()
        median_gap = float(gaps.median())
        for cadence, (lo, hi) in CADENCES.items():
            if lo <= median_gap <= hi:
                recurring.append(
                    {
                        "counterparty": cp,
                        "cadence": cadence,
                        "every_days": int(round(median_gap)),
                        "amount_cents": int(g["amount_cents"].tail(3).median()),
                        "last_date": g["booked_at"].max().date(),
                    }
                )
                break
    return recurring


def forecast_weekly(
    session: Session,
    account_id: str,
    weeks: int = 12,
    today: date | None = None,
    buffer_cents: int = 0,
    what_if: WhatIf | None = None,
) -> dict:
    today = today or date.today()
    what_if = what_if or WhatIf()
    delays = dict(what_if.delays)
    df = load_transactions(session, account_id)
    if df.empty:
        return {"weeks": [], "shortfall_weeks": [], "note": "No transactions yet."}

    balance = int(df["amount_cents"].sum())
    recurring = detect_recurring(df)
    recurring_cps = {r["counterparty"] for r in recurring}

    recent = df[df["booked_at"] >= pd.Timestamp(today - timedelta(days=LOOKBACK_DAYS))]
    inflow = recent[recent["amount_cents"] > 0].copy()
    daily_in = inflow.groupby(inflow["booked_at"].dt.date)["amount_cents"].sum()
    by_weekday = (
        pd.Series(daily_in.values, index=pd.to_datetime(daily_in.index).weekday)
        .groupby(level=0)
        .mean()
    )
    other_out = recent[(recent["amount_cents"] < 0) & (~recent["counterparty"].isin(recurring_cps))]
    other_daily_out = float(other_out["amount_cents"].sum()) / LOOKBACK_DAYS

    schedule: dict[date, list[tuple[str, int]]] = {}
    horizon = today + timedelta(weeks=weeks)
    def add(d: date, who: str, amt: int) -> None:
        d += timedelta(days=delays.get(who, 0))
        if today < d <= horizon:
            schedule.setdefault(d, []).append((who, amt))

    for r in recurring:
        d = r["last_date"] + timedelta(days=r["every_days"])
        while d <= horizon:
            if d > today:
                add(d, r["counterparty"], r["amount_cents"])
            d += timedelta(days=r["every_days"])
    for due, payee, amt in load_upcoming_bills(session, account_id):
        add(due, payee, amt)
    for d, label, amt in what_if.events:
        add(d, label, amt)

    result_weeks = []
    running = float(balance)
    for w in range(weeks):
        start = today + timedelta(days=7 * w + 1)
        low, bills = running, []  # plain floats -> JSON-safe
        for i in range(7):
            d = start + timedelta(days=i)
            running += float(by_weekday.get(d.weekday(), 0.0)) + other_daily_out
            for cp, amt in schedule.get(d, []):
                running += amt
                if amt < 0:  # what-if money in (e.g. a collected invoice) is not a bill
                    bills.append({"date": d.isoformat(), "counterparty": cp, "amount_cents": amt})
            low = min(low, running)
        result_weeks.append(
            {
                "week_start": start.isoformat(),
                "week_end": (start + timedelta(days=6)).isoformat(),
                "end_balance_cents": int(round(running)),
                "lowest_balance_cents": int(round(low)),
                "scheduled_bills": bills,
                "bills_total_cents": sum(b["amount_cents"] for b in bills),
                "shortfall": bool(low < 0),
                "below_buffer": bool(low < buffer_cents),
            }
        )

    return {
        "as_of": today.isoformat(),
        "current_balance_cents": balance,
        "recurring_detected": [
            {k: (str(v) if k == "last_date" else v) for k, v in r.items()} for r in recurring
        ],
        "weeks": result_weeks,
        "shortfall_weeks": [w["week_start"] for w in result_weeks if w["shortfall"]],
        "note": "Estimate from past transactions and known bills, not a guarantee.",
    }

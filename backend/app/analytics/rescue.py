"""Cash-flow rescue plan: close a forecast shortfall, cheapest fix first.

Deterministic like the rest of analytics: the model calls build_rescue_plan and
explains the result. Every "after" number comes from re-running the forecast with
the plan's changes applied (a what-if), so it is computed, never guessed.

Fixes, cheapest first, added until the lowest balance stays above the buffer:
  1. collect overdue invoices            free; assumes payment within COLLECT_WITHIN_DAYS
  2. longer terms from the main supplier free; the supplier may say no
  3. the best-ranked financing option    costs money; never double-counts invoices
If financing is not needed, it is offered as a backup in case a free fix fails.
"""

from datetime import date, timedelta

import pandas as pd
from sqlmodel import Session

from app.analytics import financing, invoices
from app.analytics.analysis import SUPPLIER_CATEGORY
from app.analytics.data import load_transactions
from app.analytics.forecast import WhatIf, forecast_weekly

SAFETY_BUFFER_CENTS = 50_000  # keep about two days of sales in the bank
COLLECT_WITHIN_DAYS = 14
SUPPLIER_DELAY_DAYS = 30
FINANCING_MONTHS = 2
WEEKS = 12

REMINDER_MESSAGE = (
    "Hello, a friendly reminder that our invoice to you is now overdue. Could you let us "
    "know when we can expect payment? Thank you!"
)


def _lowest(fc: dict) -> dict:
    week = min(fc["weeks"], key=lambda w: w["lowest_balance_cents"])
    return {
        "lowest_balance_cents": week["lowest_balance_cents"],
        "lowest_week": week["week_start"],
        "shortfall_weeks": fc["shortfall_weeks"],
    }


def _low(fc: dict) -> int:
    return _lowest(fc)["lowest_balance_cents"]


def _main_supplier(session: Session, account_id: str, today: date) -> str | None:
    df = load_transactions(session, account_id)
    if df.empty:
        return None
    recent = df[(df["category"] == SUPPLIER_CATEGORY)
                & (df["booked_at"] >= pd.Timestamp(today - timedelta(weeks=8)))]
    if recent.empty:
        return None
    return str(recent.groupby("counterparty")["amount_cents"].sum().idxmin())  # most spent


def _collect_overdue(session: Session, account_id: str, today: date) -> dict | None:
    overdue = invoices.find_overdue(session, account_id, today)
    if not overdue:
        return None
    by = today + timedelta(days=COLLECT_WITHIN_DAYS)
    total = sum(i.amount_cents for i in overdue)
    return {
        "kind": "collect_overdue",
        "title": f"Collect ${total / 100:,.2f} in overdue invoices",
        "how": "Send a payment reminder to " + ", ".join(i.customer for i in overdue) + ".",
        "cost_cents": 0,
        "assumption": f"Customers pay within {COLLECT_WITHIN_DAYS} days of the reminder "
        f"(by {by.isoformat()}).",
        "events": [(by, f"{i.customer} pays invoice #{i.id}", i.amount_cents) for i in overdue],
        "delays": [],
        "actions": [{"tool": "send_payment_reminders", "args": {
            "invoice_ids": [i.id for i in overdue], "message": REMINDER_MESSAGE}}],
    }


def _supplier_terms(session: Session, account_id: str, today: date) -> dict | None:
    supplier = _main_supplier(session, account_id, today)
    if supplier is None:
        return None
    return {
        "kind": "supplier_terms",
        "title": f"Ask {supplier} for {SUPPLIER_DELAY_DAYS}-day payment terms",
        "how": f"Send a short request to pay {supplier} {SUPPLIER_DELAY_DAYS} days later.",
        "cost_cents": 0,
        "assumption": f"{supplier} agrees, so each payment moves {SUPPLIER_DELAY_DAYS} days "
        "later.",
        "events": [],
        "delays": [(supplier, SUPPLIER_DELAY_DAYS)],
        "actions": [{"tool": "send_supplier_message", "args": {
            "supplier": supplier,
            "message": f"Hello {supplier}, could we move to {SUPPLIER_DELAY_DAYS}-day payment "
            "terms on our upcoming invoices? We value working with you. Thank you!"}}],
    }


def _financing(session: Session, account_id: str, today: date, gap_cents: int,
               exclude_kinds: tuple[str, ...] = ()) -> dict | None:
    ranked = financing.rank_options(session, account_id, gap_cents, FINANCING_MONTHS,
                                    today=today)
    loans = [o for o in ranked["options"] if o["kind"] not in ("supplier_terms", *exclude_kinds)]
    if not loans:
        return None
    best = loans[0]  # rank_options sorts loans by score
    draw = today + timedelta(days=7)
    n = 12 if best["kind"] == "term_loan" else FINANCING_MONTHS
    events = [(draw, best["name"], best["amount_cents"])]
    if best["monthly_payment_cents"]:
        events += [(draw + timedelta(days=30 * (k + 1)), f"{best['name']} payment",
                    -best["monthly_payment_cents"]) for k in range(n)]
    return {
        "kind": "financing",
        "title": f"Use {best['name']}",
        "how": f"Get ${best['amount_cents'] / 100:,.2f} for a total cost of "
        f"${best['total_cost_cents'] / 100:,.2f}.",
        "cost_cents": best["total_cost_cents"],
        "assumption": "The lender approves. Only the lender decides.",
        "events": events,
        "delays": [],
        "actions": [{"tool": "submit_loan_application", "args": {
            "product_id": best["product_id"], "amount_usd": best["amount_cents"] / 100,
            "term_months": n}}],
    }


def build_plan(session: Session, account_id: str, today: date | None = None) -> dict:
    today = today or date.today()
    base = forecast_weekly(session, account_id, weeks=WEEKS, today=today)
    if not base["weeks"]:
        return {"needed": False, "note": "No transactions yet."}

    before = _lowest(base)
    steps: list[dict] = []
    next_actions: list[dict] = []
    events: list[tuple] = []
    delays: list[tuple] = []
    used: set[str] = set()
    current = base
    levers = [x for x in (_collect_overdue(session, account_id, today),
                          _supplier_terms(session, account_id, today)) if x]

    while _low(current) < SAFETY_BUFFER_CENTS:
        if levers:
            lever = levers.pop(0)
        elif "financing" not in used:
            # Free fixes were not enough. Never advance invoices we are already collecting.
            exclude = ("invoice_advance",) if "collect_overdue" in used else ()
            lever = _financing(session, account_id, today, SAFETY_BUFFER_CENTS - _low(current),
                               exclude)
            if lever is None:
                break
        else:
            break
        events += lever["events"]
        delays += lever["delays"]
        low_before_step = _low(current)
        current = forecast_weekly(session, account_id, weeks=WEEKS, today=today,
                                  what_if=WhatIf(tuple(events), tuple(delays)))
        used.add(lever["kind"])
        steps.append({
            "step": len(steps) + 1,
            "kind": lever["kind"],
            "title": lever["title"],
            "how": lever["how"],
            "cost_cents": lever["cost_cents"],
            "assumption": lever["assumption"],
            "lowest_after_cents": _low(current),
            "improves_lowest_by_cents": _low(current) - low_before_step,
        })
        next_actions += lever["actions"]

    backup = None
    if steps and "financing" not in used:
        fallback = _financing(session, account_id, today,
                              SAFETY_BUFFER_CENTS - before["lowest_balance_cents"])
        if fallback:
            backup = {"when": "If a step above does not work out",
                      "title": fallback["title"], "how": fallback["how"],
                      "cost_cents": fallback["cost_cents"]}

    after = _lowest(current)
    return {
        "needed": before["lowest_balance_cents"] < SAFETY_BUFFER_CENTS,
        "safety_buffer_cents": SAFETY_BUFFER_CENTS,
        "before": before,
        "after": {**after, "closes_gap": after["lowest_balance_cents"] >= SAFETY_BUFFER_CENTS},
        "steps": steps,
        "backup": backup,
        "next_actions": next_actions,
        "weeks": [
            {"week_start": b["week_start"], "before_cents": b["lowest_balance_cents"],
             "after_cents": a["lowest_balance_cents"]}
            for b, a in zip(base["weeks"], current["weeks"], strict=True)
        ],
        "note": "Estimate: the forecast is re-run with each step applied. Messages and "
        "applications only go out after you approve them.",
    }

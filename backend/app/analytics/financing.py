"""Explainable, rule-based financing match.

  1. Eligibility filter (time in business, limits).
  2. Score each option on: total cost, affordability (monthly payment / monthly margin),
     fit to the gap, and speed.
  3. Weighted score -> label: Try first (non-loan), Best fit, Good fit, Stretch
     (payment > 25% of monthly margin).
  4. "Why it fits" / "Watch out" come from the factor values, so every claim is traceable.

Lender terms are ILLUSTRATIVE MOCK DATA. Keep lender names as placeholders.
"""

from dataclasses import dataclass
from datetime import date

from sqlmodel import Session

from app.analytics import analysis, invoices

STRETCH_RATIO = 0.25
WEIGHTS = {"cost": 0.4, "affordability": 0.35, "fit": 0.15, "speed": 0.10}


@dataclass(frozen=True)
class Product:
    id: str
    name: str
    kind: str  # credit_line | invoice_advance | term_loan | supplier_terms
    apr: float = 0.0
    flat_fee_pct: float = 0.0
    max_cents: int = 0
    term_months: int | None = None
    min_years_in_business: float = 0
    days_to_funds: int = 3


MOCK_PRODUCTS = [
    Product("lender-a-line", "[Lender A] Credit line", "credit_line", apr=0.18,
            max_cents=200_000, min_years_in_business=1, days_to_funds=2),
    Product("lender-b-advance", "[Lender B] Invoice advance", "invoice_advance",
            flat_fee_pct=0.025, days_to_funds=1),
    Product("lender-c-term", "[Lender C] 12-month term loan", "term_loan", apr=0.20,
            max_cents=300_000, term_months=12, min_years_in_business=2, days_to_funds=7),
    Product("supplier-terms", "Ask your supplier for longer terms", "supplier_terms",
            days_to_funds=0),
]


def _amortized(amount: int, apr: float, n: int) -> tuple[int, int]:
    """(monthly payment, total interest) to repay `amount` in n equal monthly payments."""
    r = apr / 12
    payment = int(amount * r / (1 - (1 + r) ** -n))
    return payment, payment * n - amount


def _evaluate(p: Product, gap: int, months: int, overdue_total: int) -> dict | None:
    if p.kind == "credit_line":
        amount = min(max(gap, 100_000), p.max_cents)
        # repaid in full over the months needed: principal + interest, not interest only
        payment, cost = _amortized(amount, p.apr, months)
    elif p.kind == "invoice_advance":
        if overdue_total == 0:
            return None
        amount = int(overdue_total * 0.8)
        cost = int(overdue_total * p.flat_fee_pct)
        payment = 0  # repaid when customers pay
    elif p.kind == "term_loan":
        amount = p.max_cents
        payment, cost = _amortized(amount, p.apr, p.term_months or 12)
    else:  # supplier_terms
        amount, cost, payment = 0, 0, 0
    return {"amount_cents": amount, "total_cost_cents": cost, "monthly_payment_cents": payment}


ADVANCE_RATE = 0.8  # an invoice advance pays out 80% of the overdue invoices


def _usd(cents: int) -> str:
    return f"${cents / 100:,.2f}"


def quote(
    session: Session, account_id: str, product_id: str, amount_cents: int, term_months: int,
    years_in_business: float = 3.0, today: date | None = None,
) -> dict:
    """Exact terms for one application, from the catalogue, never from the model.

    Raises ValueError when the product does not exist, is not a loan, or the amount or
    term is outside what the product allows. The result is what the owner approves.
    """
    p = next((p for p in MOCK_PRODUCTS if p.id == product_id), None)
    if p is None:
        raise ValueError(f"No such financing product: {product_id}")
    if p.kind == "supplier_terms":
        raise ValueError("Supplier terms are not a loan: there is nothing to apply for")
    if years_in_business < p.min_years_in_business:
        raise ValueError(f"{p.name} needs {p.min_years_in_business:g}+ years in business")

    if p.kind == "invoice_advance":
        overdue = sum(i.amount_cents for i in
                      invoices.find_overdue(session, account_id, today or date.today()))
        limit = int(overdue * ADVANCE_RATE)
        payment, cost = 0, round(amount_cents / ADVANCE_RATE * p.flat_fee_pct)
    else:
        limit = p.max_cents
        if p.term_months and term_months != p.term_months:
            raise ValueError(f"{p.name} has a fixed term of {p.term_months} months")
        if not 1 <= term_months <= 36:
            raise ValueError("The term must be 1 to 36 months")
        payment, cost = _amortized(amount_cents, p.apr, term_months)
    if amount_cents > limit:
        raise ValueError(f"{p.name} can lend at most {_usd(limit)}")

    return {
        "lender_product": p.name,
        "amount": _usd(amount_cents),
        "term_months": term_months,
        "monthly_payment": _usd(payment) if payment else "none (repaid when customers pay)",
        "total_cost": _usd(cost),
        "total_cost_cents": cost,
        "note": "Illustrative mock terms. Only the lender decides approval.",
    }


def rank_options(
    session: Session, account_id: str, gap_cents: int, months_needed: int,
    years_in_business: float = 3.0, today: date | None = None,
) -> dict:
    today = today or date.today()
    summary = analysis.business_summary(session, account_id, today=today)
    margin = max(summary.get("last_30_days", {}).get("net_cents", 0), 1)
    overdue_total = sum(i.amount_cents for i in invoices.find_overdue(session, account_id, today))

    options = []
    for p in MOCK_PRODUCTS:
        if years_in_business < p.min_years_in_business:
            continue
        ev = _evaluate(p, gap_cents, months_needed, overdue_total)
        if ev is None:
            continue
        ratio = ev["monthly_payment_cents"] / margin
        covers = p.kind == "supplier_terms" or ev["amount_cents"] >= gap_cents
        factors = {
            "cost": 1 - min(ev["total_cost_cents"] / max(margin, 1), 1),
            "affordability": 1 - min(ratio, 1),
            "fit": 1.0 if covers else 0.5,
            "speed": 1 - min(p.days_to_funds / 14, 1),
        }
        if p.kind == "term_loan" and ev["amount_cents"] > 2 * max(gap_cents, 1):
            factors["fit"] = 0.3  # much more than needed
        score = round(sum(WEIGHTS[k] * v for k, v in factors.items()), 3)

        why, watch = [], []
        if ev["total_cost_cents"] == 0:
            why.append("It costs nothing and there is nothing to apply for.")
        if p.kind == "credit_line":
            why.append("You only pay for what you draw, which suits a short gap.")
            watch.append("The rate can change and the line is reviewed yearly.")
        if p.kind == "invoice_advance":
            why.append("It is tied to money you are already owed, so no new monthly payment.")
            if not covers:
                watch.append("It covers only part of the gap.")
        if ratio > STRETCH_RATIO:
            watch.append(f"The payment would take {ratio:.0%} of your monthly margin.")
        if factors["fit"] < 0.5:
            watch.append("It is more than you need.")
        if p.kind == "supplier_terms":
            watch.append("Your supplier may say no.")

        options.append({
            "product_id": p.id, "name": p.name, "kind": p.kind, **ev,
            "payment_to_margin_pct": round(100 * ratio, 1), "score": score,
            "factors": {k: round(v, 2) for k, v in factors.items()},
            "why_it_fits": why, "watch_out": watch,
        })

    loans = sorted((o for o in options if o["kind"] != "supplier_terms"),
                   key=lambda o: o["score"], reverse=True)
    for i, o in enumerate(loans):
        o["label"] = ("Stretch" if o["payment_to_margin_pct"] > 100 * STRETCH_RATIO
                      else "Best fit" if i == 0 else "Good fit")
    non_loans = [dict(o, label="Try first") for o in options if o["kind"] == "supplier_terms"]

    return {
        "gap_cents": gap_cents,
        "monthly_margin_cents": margin,
        "options": non_loans + loans,
        "disclaimer": "Illustrative mock terms. Only the lender decides approval.",
    }

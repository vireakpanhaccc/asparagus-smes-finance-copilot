# Core algorithms

All numbers shown to the owner come from these deterministic functions. The language model selects which to call and explains the result; it never computes amounts.

## 1. Cash-flow forecast (`app/analytics/forecast.py`)

1. **Current balance** = sum of all transactions.
2. **Recurring outflows.** For each counterparty with at least 3 payments, the median gap between payments classifies it as weekly (6–8 days), bi-weekly (13–16) or monthly (27–32). Next due date = last payment + gap. Amount = median of the last 3 payments.
3. **Income pattern.** Mean daily inflow per weekday over the last 8 weeks. This captures slow days (e.g. Tuesdays) and recent softening.
4. **Other outflows.** Mean daily non-recurring outflow over the last 8 weeks.
5. **Known bills.** Unpaid payables (`Bill`) are placed on their due dates.
6. **Roll forward** day by day for 12 weeks. Each week reports its lowest balance; a week is flagged as a **shortfall** if the balance drops below zero.

Limitations: no seasonality beyond weekday effects; assumes recent patterns continue. Stretch goal: compare with Holt-Winters exponential smoothing.

## 2. Business analysis (`app/analytics/analysis.py`)

- Money in, money out and margin over the last 30 days
- Spending by category
- Net and margin per month for 6 months
- Supplier cost change: last 8 weeks vs the 8 weeks before

## 3. Financing match (`app/analytics/financing.py`)

1. **Eligibility filter**: time in business, product limits, whether there are invoices to advance against.
2. **Per-option figures**: amount, total cost in dollars, monthly payment. Credit lines and term loans use the standard amortised payment, so the monthly figure repays principal plus interest (a credit line over the months the gap lasts).
3. **Factor scores (0–1)**:
   - cost: 1 − total cost ÷ monthly margin
   - affordability: 1 − monthly payment ÷ monthly margin
   - fit: does it cover the gap; penalised if far larger than needed
   - speed: days to funds
4. **Weighted score**: cost 0.40, affordability 0.35, fit 0.15, speed 0.10.
5. **Labels**: non-loan options are **Try first**; the top loan is **Best fit**; any option whose payment exceeds 25% of monthly margin is **Stretch**.
6. **Explanations** are generated from the factor values, so every "why it fits" and "watch out" can be traced to a number.

Lender terms are illustrative mock data. The copilot ranks fit; only a lender decides approval.

## 4. Cash-flow rescue plan (`app/analytics/rescue.py`)

The agentic workflow: from a forecast shortfall to a plan with actions queued for approval.

1. **Detect**: run the 12-week forecast; a plan is needed if the lowest weekly balance is below the **$500 safety buffer** (about two days of sales).
2. **Fixes, cheapest first**, added one at a time until the lowest balance stays above the buffer:
   - collect overdue invoices (free; assumes payment within 14 days of a reminder)
   - ask the main supplier (largest supply spend, last 8 weeks) for 30-day terms (free)
   - the best-ranked financing option for what is still missing (never an invoice advance on invoices already being collected)
3. **What-if simulation**: after each fix the *same* forecast is re-run with the fix applied (`WhatIf`: extra one-off events and delayed payees), so every "after" balance is computed, not estimated by the model.
4. **Backup**: if financing was not needed, the best financing option is named as a fallback in case a free fix fails.
5. **Act**: the plan returns `next_actions` (e.g. `send_payment_reminders`, `send_supplier_message`) with exact arguments. The agent proposes them; each is held for the owner's approval.

On the sample data the plan takes the lowest balance from about −$220 to about +$2,200 with two free steps.

## 5. Prompt-injection detection (`app/security/untrusted.py`)

Regex heuristics for instruction-like text (e.g. "ignore previous instructions", fake system tags, "transfer … immediately"). Matches are logged; all untrusted text is escaped and wrapped regardless. This is a first layer only; the policy engine is the guarantee.

# SME Finance Copilot

**An AI finance copilot for small-business owners that forecasts cash shortfalls, matches financing options and drafts the fix, but never sends, submits or moves anything without the owner's recorded approval.**

International Track entry, Shenzhen FinTechathon 2026 · Topic E: SME Finance Copilot

> Sandbox only. All businesses, customers, amounts and lender terms are sample data. The WeBank connection is an **assumed partner integration, simulated in the sandbox**; no real bank is contacted.

![CI](https://github.com/<org>/sme-finance-copilot/actions/workflows/ci.yml/badge.svg)

## What it does

| Topic E requirement              | Feature                                                                                                                                                                           |
| -------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Cash-flow management with alerts | 12-week forecast from transaction history and known bills; flags shortfall weeks                                                                                                  |
| Financing-option matching        | Rule-based, explainable ranking with total cost, affordability and "why / watch out"                                                                                              |
| Business financial analysis      | Spending by category, 6-month margin trend, supplier cost change                                                                                                                  |
| Data without a bank link         | **My data** page: type a transaction, bill or invoice, or upload a CSV; validated, audited, and fed straight into the forecast. Bank rows are locked on the server; mistakes are fixed with an offsetting correction                                 |
| All three, as one agentic task   | **Cash-flow rescue plan**: detects the shortfall, tries the cheapest fixes first, re-runs the forecast with them applied (before/after chart) and queues each action for approval |

The owner asks in plain English ("Can I cover rent and payroll in December?"). The agent reads data, forecasts, finds overdue invoices and drafts reminders. Sending them stops at an approval card.

## Security in one paragraph

Every tool has a permission tier set in code: **read-only**, **suggest** or **needs approval**. A server-side policy engine enforces it, not the prompt. Actions that need approval are stored, shown to the owner, and only run with an **HMAC approval token bound to the exact payload**, which is single-use and expires in 10 minutes. Free text from customers is wrapped as untrusted data and scanned for injection attempts. Personal data is masked in logs. Every step goes into a **hash-chained audit log** that detects tampering. Details: [docs/security-design.md](docs/security-design.md).

## Quick start

**Docker (recommended)**

```bash
cp .env.example .env          # add LLM_API_KEY (free Z.ai key), APPROVAL_SECRET and OWNER_DEMO_TOKEN
docker compose up --build
# UI  http://localhost:3000    API docs  http://localhost:8000/docs
```

**Local** (Python 3.11+, Node 20+)

```bash
cp .env.example .env              # fill in LLM_API_KEY, APPROVAL_SECRET, OWNER_DEMO_TOKEN
echo "NEXT_PUBLIC_OWNER_TOKEN=<same value as OWNER_DEMO_TOKEN>" > frontend/.env.local
python3 -m venv backend/.venv && source backend/.venv/bin/activate   # macOS has no `python`, only `python3`
make setup        # pip + npm install
make reseed       # sample data: bank link + 403 bank rows, a sample CSV upload, 3 typed entries (clears the audit log)
make api          # terminal 1, port 8000
make web          # terminal 2, port 3000
```

Notes for a new machine:

- **Secrets have no defaults.** The API refuses to start until `APPROVAL_SECRET` (32+ characters) and `OWNER_DEMO_TOKEN` (16+) are set. Generate each with `python3 -c "import secrets; print(secrets.token_hex(32))"`.

- **Keep the frontend on port 3000.** The API's CORS only allows `http://localhost:3000`; on another port every request fails with "Failed to fetch".
- Keep the venv activated in every terminal that runs `make api`, `make seed` or `make test`.
- `make seed` keeps existing data; `make reseed` wipes it and the audit log. An empty database sends the owner to `/setup` (first-time setup) instead of Overview.
- Older databases are upgraded automatically when the API or the seed script starts (`app/db.py`, `_migrate`).
- Stop `next dev` before running `npm run build`: both write `.next/` and the dev server will start returning 500s.

## Tests

```bash
make test
```

The suite runs without an API key; the agent loop uses a scripted fake model. Key security tests:

| Test                                                               | Proves                                                        |
| ------------------------------------------------------------------ | ------------------------------------------------------------- |
| `test_needs_approval_tool_is_held_not_run`                         | The agent cannot send on its own                              |
| `test_payload_changed_after_approval_is_blocked`                   | Approval is bound to the exact content                        |
| `test_token_cannot_be_reused` / `test_expired_approval_is_blocked` | Single use, 10-minute expiry                                  |
| `test_reading_injected_note_is_logged_and_wrapped`                 | Prompt injection in a customer note is treated as data        |
| `test_audit_chain_detects_tampering`                               | Editing history is detectable                                 |
| `test_masks_cambodian_phone_numbers`                               | PII masked in logs                                            |
| `test_data_endpoints_refuse_missing_or_wrong_token`                | No business data, logs or pending actions without the owner   |
| `test_injected_transfer_instruction_cannot_move_money`             | The planted "$5,000 transfer" note cannot move money          |
| `test_bill_changed_after_approval_is_blocked`                      | A payment runs only for the exact bill the owner approved     |
| `test_agent_builds_plan_and_holds_every_action`                    | The rescue plan proposes actions; none runs without the owner |
| `test_bad_csv_imports_nothing_and_says_why`                        | A CSV with one bad line imports nothing and names the line    |
| `test_bank_row_cannot_be_edited` / `…_deleted`                     | Bank rows are locked on the server (403 + audit `blocked`)    |
| `test_correction_creates_linked_manual_row`                        | A bank mistake is fixed by an offsetting entry, not a rewrite |
| `test_demo_seed_adds_user_data_without_changing_the_story`         | The demo seed keeps the December shortfall                    |

## Repository layout

```
backend/            FastAPI + agent + security core (Python)
  app/agent/          agent loop, system prompt, LLM provider (OpenAI-compatible API: Z.ai GLM / fake)
  app/tools/          tools, each with a permission tier
  app/policy/         policy engine, payload-bound approval tokens
  app/security/       PII masking, untrusted-text handling, hash-chained audit log
  app/analytics/      forecast, business analysis, financing ranking (deterministic)
  app/connectors/     mock WeBank adapter, CSV adapter
  app/api/            REST + SSE endpoints
  scripts/seed_data.py  deterministic sample data
  tests/              pytest suite
frontend/           Next.js UI: overview, financing, my data, audit log, first-time setup; the Copilot is a chat bot on every page
docs/               technical documentation + security self-assessment
evidence/           exported audit logs, test report, demo video link
```

## Working on this project

- **Design spec for My data and Setup:** [docs/handoff-my-data.md](docs/handoff-my-data.md). Where the build differs from it, see "Known gaps" below.
- **Data sources.** Every transaction, bill and invoice has a `source`: `bank` (synced, or a payment the Copilot made after approval), `file` (CSV upload) or `manual` (typed). `bank` rows can never be edited or deleted: the check is server-side (`_guard` in `backend/app/api/data_records.py`), not just hidden buttons. All of it lives under `/api/data/*`; `/api/connect*` still handles bank-link consent.
- **Demo seed.** `seed(..., sample_user_data=True)` adds the file and typed rows by carving them out of matching bank rows, so the forecast, KPIs and December shortfall stay the same. Tests use the plain seed.
- **Colours** are the `brand.*` tokens in `frontend/tailwind.config.ts`; use those, not raw hex.
- **Checks before a PR:** `cd backend && ruff check . && pytest`, then `cd frontend && npm run typecheck`.

### Known gaps

- `frontend/messages/km.json` (Khmer) exists but nothing loads it yet: there is no language switcher. The Khmer text needs a native speaker's review.
- No browser tests (Playwright was optional in the handoff and is not set up).
- The live-sync transaction feed from the old Connect page has no place in the new UI; the backend stream (`/api/connect/live`) still exists.
- In Docker the demo CSV upload is missing: the backend image only copies `backend/`, so `samples/cash_transactions.csv` is not found and the seed skips it.
- "Synced n min ago" on the bank card is mock data (`ConsentGrant.last_sync_at`).

## Submission map

| Checklist item                            | Where                                                                                                                                      |
| ----------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| 01 Technical documentation                | [docs/architecture.md](docs/architecture.md), [docs/algorithms.md](docs/algorithms.md), [docs/security-design.md](docs/security-design.md) |
| 02 Presentation deck                      | link here                                                                                                                                  |
| 03 Demo video                             | link in [evidence/README.md](evidence/README.md)                                                                                           |
| 04 Source code, README, deployment, tests | this repository                                                                                                                            |
| 05 Security self-assessment               | [docs/security-self-assessment.md](docs/security-self-assessment.md)                                                                       |
| 06 Execution evidence                     | [evidence/](evidence/)                                                                                                                     |

## Third-party components

| Component                                       | Licence     |
| ----------------------------------------------- | ----------- |
| FastAPI, Pydantic, SQLModel, Starlette, Uvicorn | MIT / BSD-3 |
| pandas, NumPy                                   | BSD-3       |
| slowapi, sse-starlette                          | MIT / BSD-3 |
| httpx                                           | BSD-3       |
| Next.js, React, Recharts, Tailwind CSS          | MIT         |
| IBM Plex Sans, IBM Plex Mono, Noto Sans Khmer (Google Fonts) | SIL OFL 1.1 |

Model: GLM-4.5-Flash / GLM-4.7-Flash (Zhipu AI) via the Z.ai API free tier, used under Z.ai's terms. Lender names in the app are placeholders.

## Team

| Name | Role | University |
| ---- | ---- | ---------- |
|      |      |            |

Licence: MIT

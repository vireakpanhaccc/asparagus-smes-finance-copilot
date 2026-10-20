# SME Finance Copilot

**An AI finance copilot for small-business owners that forecasts cash shortfalls, matches financing options and drafts the fix, but never sends, submits or moves anything without the owner's recorded approval.**

International Track entry, Shenzhen FinTechathon 2026 · Topic E: SME Finance Copilot

> Sandbox only. All businesses, customers, amounts and lender terms are sample data. The WeBank connection is an **assumed partner integration, simulated in the sandbox**; no real bank is contacted.

![CI](https://github.com/vireakpanhaccc/asparagus-smes-finance-copilot/actions/workflows/ci.yml/badge.svg)

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

Every tool has a permission tier set in code: **read-only**, **suggest** or **needs approval**. A server-side policy engine enforces it, not the prompt. Actions that need approval are stored, shown to the owner, and only run with an **HMAC approval token bound to the exact payload**, which is single-use and expires in 10 minutes. Free text from customers is wrapped as untrusted data and scanned for injection attempts. Personal data is masked in logs. Every step goes into a **hash-chained audit log** that detects tampering. Details: [docs/technical-document.md](docs/technical-document.md) §6.

## How to run it

### 1. Prerequisites

- **Python 3.11+** and **Node.js 20+** (or only **Docker**, see step 5)
- A free **Z.ai API key** for the language model: <https://z.ai/manage-apikey/apikey-list> (the `*-flash` models are free). Without a key the app runs, but the Copilot chat answers "The AI service is busy".

### 2. One-time setup

```bash
git clone https://github.com/vireakpanhaccc/asparagus-smes-finance-copilot.git
cd asparagus-smes-finance-copilot
cp .env.example .env
```

Generate two secrets (run the command twice; each prints a new random value):

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Open `.env` and fill in:

| Variable | Value |
|---|---|
| `LLM_API_KEY` | your Z.ai key |
| `APPROVAL_SECRET` | the first generated value |
| `OWNER_DEMO_TOKEN` | the second generated value |

The web app needs the same owner token. Create `frontend/.env.local` with one line:

```bash
echo "NEXT_PUBLIC_OWNER_TOKEN=<the same value as OWNER_DEMO_TOKEN>" > frontend/.env.local
```

Install the dependencies (macOS has `python3`, not `python`):

```bash
python3 -m venv .venv
source .venv/bin/activate
make setup          # backend (pip) and frontend (npm) packages
```

### 3. Load the demo data

```bash
make reseed         # Sample Café: 6 months of bank transactions, a CSV upload, typed entries;
                    # also clears the audit log
```

### 4. Start the app (two terminals, venv active in both)

```bash
make api            # terminal 1: API on http://localhost:8000
make web            # terminal 2: web app on http://localhost:3000
```

Open **http://localhost:3000**. The API documentation, where every endpoint can be tried, is at **http://localhost:8000/docs** (paste your `OWNER_DEMO_TOKEN` into the `x-owner-token` field).

### 5. Or run everything with Docker

After step 2 (only `.env` is needed):

```bash
docker compose up --build
```

Then open http://localhost:3000. Docker uses PostgreSQL and loads the demo data on first start.

## How to test it

| What | Command | Expected |
|---|---|---|
| Backend tests (no API key or `.env` needed; the agent uses a scripted fake model) | `make test` | `199 passed` |
| Lint and frontend type-check | `make lint` | no errors |
| Manual end-to-end cases | see the Execution Evidence Report | 10 task cases and 16 attack cases, all passing |

Quick manual check after starting the app: on **Overview**, click **Build a rescue plan**. The Copilot builds the plan and shows two **Needs your OK** cards; nothing is sent until you click **Approve and send**, and every step appears on the **Audit log** page.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| The API stops with "Refusing to start: … is not set / is a published default" | `APPROVAL_SECRET` or `OWNER_DEMO_TOKEN` is missing, too short (32 / 16 characters) or a default. Generate new values (step 2). |
| The web app shows "owner authentication required" | `frontend/.env.local` is missing or its token differs from `OWNER_DEMO_TOKEN`. Fix it and restart `make web`. |
| The chat says "The AI service is busy right now" | No or invalid `LLM_API_KEY`, or the free model is rate-limiting. Wait a minute and retry. |
| Every request fails with "Failed to fetch" | The web app is not on port 3000 (the API only allows that origin), or the API is not running. |
| The page loads but new colours or styles are missing | A stale Next.js cache. Stop `make web`, run `rm -rf frontend/.next`, start it again and hard-reload the browser (Cmd + Shift + R). |
| The app opens the Setup page instead of Overview | The database is empty. Run `make reseed`. |

Notes:

- `make seed` keeps existing data; `make reseed` wipes it and the audit log.
- Older databases are upgraded automatically when the API or the seed script starts (`app/db.py`, `_migrate`).
- Stop `make web` before running `npm run build`; both write `.next/`.

## Key security tests

199 tests. The suite runs without an API key or a `.env` (the agent loop uses a scripted fake model, and the tests set their own secrets). Key security tests:

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
| `test_two_tabs_approving_at_once_run_the_action_once`              | One approval runs once, even with simultaneous requests       |
| `test_default_or_weak_secrets_are_refused`                         | The API will not start with a missing or published secret     |
| `test_unsafe_reminder_is_refused_before_any_card`                  | Outgoing messages cannot carry links, contacts or accounts    |
| `test_contact_changed_after_approval_blocks_the_send`              | Recipients are rebuilt and re-checked before sending          |
| `test_application_that_does_not_fit_is_refused`                    | Loans only for real products and allowed amounts and terms    |
| `test_model_never_sees_numbers_or_contacts_in_notes`               | Free text is masked before it reaches the model               |
| `test_disguised_and_chinese_injections_are_detected`               | Fullwidth, invisible-character and Chinese injections caught  |
| `test_contracted_or_past_tense_claims_are_corrected`               | The reply cannot claim an action that only waits for approval |
| `test_sandbox_off_fails_closed_and_says_why`                       | Switching sandbox off refuses actions instead of sending      |

The full list of controls and their tests is in [docs/security-self-assessment.md](docs/security-self-assessment.md); the manual test results are summarised in [evidence/README.md](evidence/README.md) and documented in full in the Execution Evidence Report.

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

- **Data sources.** Every transaction, bill and invoice has a `source`: `bank` (synced, or a payment the Copilot made after approval), `file` (CSV upload) or `manual` (typed). `bank` rows can never be edited or deleted: the check is server-side (`_guard` in `backend/app/api/data_records.py`), not just hidden buttons. All of it lives under `/api/data/*`; `/api/connect*` still handles bank-link consent.
- **Demo seed.** `seed(..., sample_user_data=True)` adds the file and typed rows by carving them out of matching bank rows, so the forecast, KPIs and December shortfall stay the same. Tests use the plain seed.
- **Colours** are the `brand.*` tokens in `frontend/tailwind.config.ts`; use those, not raw hex.
- **Checks before a PR:** `cd backend && ruff check . && pytest`, then `cd frontend && npm run typecheck`.

### Known gaps

- `frontend/messages/km.json` (Khmer) exists but nothing loads it yet: there is no language switcher. The Khmer text needs a native speaker's review.
- No browser tests: the frontend is checked by type-check and build only.
- The live-sync transaction feed from the old Connect page has no place in the new UI; the backend stream (`/api/connect/live`) still exists.
- In Docker the demo CSV upload is missing: the backend image only copies `backend/`, so `samples/cash_transactions.csv` is not found and the seed skips it.
- "Synced n min ago" on the bank card is mock data (`ConsentGrant.last_sync_at`).

## Submission map

| Checklist item                            | Where                                                                                                                                      |
| ----------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| 01 Technical documentation                | [docs/technical-document.md](docs/technical-document.md) (architecture, algorithms, security design, testing) |
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

Licence: MIT

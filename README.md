# SME Finance Copilot

**An AI finance copilot for small-business owners that forecasts cash shortfalls, matches financing options and drafts the fix, but never sends, submits or moves anything without the owner's recorded approval.**

International Track entry, Shenzhen FinTechathon 2026 · Topic E: SME Finance Copilot

> Sandbox only. All businesses, customers, amounts and lender terms are sample data. The WeBank connection is an **assumed partner integration, simulated in the sandbox**; no real bank is contacted.

![CI](https://github.com/<org>/sme-finance-copilot/actions/workflows/ci.yml/badge.svg)

## What it does

| Topic E requirement | Feature |
|---|---|
| Cash-flow management with alerts | 12-week forecast from transaction history and known bills; flags shortfall weeks |
| Financing-option matching | Rule-based, explainable ranking with total cost, affordability and "why / watch out" |
| Business financial analysis | Spending by category, 6-month margin trend, supplier cost change |
| Data without a bank link | **Manual entry** on the Connect page: add a transaction, bill or invoice, or upload a CSV; validated, audited, and fed straight into the forecast |
| All three, as one agentic task | **Cash-flow rescue plan**: detects the shortfall, tries the cheapest fixes first, re-runs the forecast with them applied (before/after chart) and queues each action for approval |

The owner asks in plain English ("Can I cover rent and payroll in December?"). The agent reads data, forecasts, finds overdue invoices and drafts reminders. Sending them stops at an approval card.

## Security in one paragraph

Every tool has a permission tier set in code: **read-only**, **suggest** or **needs approval**. A server-side policy engine enforces it, not the prompt. Actions that need approval are stored, shown to the owner, and only run with an **HMAC approval token bound to the exact payload**, which is single-use and expires in 10 minutes. Free text from customers is wrapped as untrusted data and scanned for injection attempts. Personal data is masked in logs. Every step goes into a **hash-chained audit log** that detects tampering. Details: [docs/security-design.md](docs/security-design.md).

## Quick start

**Docker (recommended)**

```bash
cp .env.example .env          # add LLM_API_KEY (free Z.ai key) and a random APPROVAL_SECRET
docker compose up --build
# UI  http://localhost:3000    API docs  http://localhost:8000/docs
```

**Local**

```bash
cp .env.example .env
make setup        # pip + npm install
make seed         # 6 months of Sample Café data
make api          # terminal 1
make web          # terminal 2
```

## Tests

```bash
make test
```

The suite runs without an API key; the agent loop uses a scripted fake model. Key security tests:

| Test | Proves |
|---|---|
| `test_needs_approval_tool_is_held_not_run` | The agent cannot send on its own |
| `test_payload_changed_after_approval_is_blocked` | Approval is bound to the exact content |
| `test_token_cannot_be_reused` / `test_expired_approval_is_blocked` | Single use, 10-minute expiry |
| `test_reading_injected_note_is_logged_and_wrapped` | Prompt injection in a customer note is treated as data |
| `test_audit_chain_detects_tampering` | Editing history is detectable |
| `test_masks_cambodian_phone_numbers` | PII masked in logs |
| `test_data_endpoints_refuse_missing_or_wrong_token` | No business data, logs or pending actions without the owner |
| `test_injected_transfer_instruction_cannot_move_money` | The planted "$5,000 transfer" note cannot move money |
| `test_bill_changed_after_approval_is_blocked` | A payment runs only for the exact bill the owner approved |
| `test_agent_builds_plan_and_holds_every_action` | The rescue plan proposes actions; none runs without the owner |
| `test_bad_csv_imports_nothing_and_says_why` | A CSV with one bad line imports nothing and names the line |

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
frontend/           Next.js UI: overview, copilot, financing, audit log, connect
docs/               technical documentation + security self-assessment
evidence/           exported audit logs, test report, demo video link
```

## Submission map

| Checklist item | Where |
|---|---|
| 01 Technical documentation | [docs/architecture.md](docs/architecture.md), [docs/algorithms.md](docs/algorithms.md), [docs/security-design.md](docs/security-design.md) |
| 02 Presentation deck | link here |
| 03 Demo video | link in [evidence/README.md](evidence/README.md) |
| 04 Source code, README, deployment, tests | this repository |
| 05 Security self-assessment | [docs/security-self-assessment.md](docs/security-self-assessment.md) |
| 06 Execution evidence | [evidence/](evidence/) |

## Third-party components

| Component | Licence |
|---|---|
| FastAPI, Pydantic, SQLModel, Starlette, Uvicorn | MIT / BSD-3 |
| pandas, NumPy | BSD-3 |
| slowapi, sse-starlette | MIT / BSD-3 |
| httpx | BSD-3 |
| Next.js, React, Recharts, Tailwind CSS | MIT |
| Inter, IBM Plex Mono (Google Fonts) | SIL OFL 1.1 |

Model: GLM-4.5-Flash / GLM-4.7-Flash (Zhipu AI) via the Z.ai API free tier, used under Z.ai's terms. Lender names in the app are placeholders.

## Team

| Name | Role | University |
|---|---|---|
| | | |

Licence: MIT

# Security self-assessment report

*Fill in the bracketed parts before submitting. Keep it honest; judges value a clear known-risk list.*

## 1. Scope

SME Finance Copilot v[0.1], sandbox deployment, sample data only. Assessed on [date] by [names].

## 2. Permission-tier implementation

See [security-design.md](security-design.md). Enforcement point: `PolicyEngine.call()` and `PolicyEngine.execute()` in `backend/app/policy/engine.py`. Tiers are declared per tool in `backend/app/tools/`.

## 3. Controls and evidence

| # | Control | Implementation | Test | Status |
|---|---|---|---|---|
| C1 | Tier enforcement on server | `policy/engine.py` | `test_needs_approval_tool_is_held_not_run` | [Pass] |
| C2 | Approval required to act | pending action + token | `test_execute_without_approval_is_blocked` | [Pass] |
| C3 | Approval bound to payload | SHA-256 + HMAC | `test_payload_changed_after_approval_is_blocked`, `test_owner_must_approve_what_they_saw` | [Pass] |
| C4 | Single use, expiry | status + 10-min TTL | `test_token_cannot_be_reused`, `test_expired_approval_is_blocked` | [Pass] |
| C5 | Forged tokens rejected | HMAC with server secret | `test_forged_token_is_blocked` | [Pass] |
| C6 | Unknown tools / bad input blocked | registry + Pydantic | `test_unknown_tool_and_bad_input_are_blocked` | [Pass] |
| C7 | Prompt injection treated as data | wrap + detect + log | `test_reading_injected_note_is_logged_and_wrapped` | [Pass] |
| C8 | Model never sees tokens | `ToolOutcome.for_llm()` | `test_model_never_sees_approval_tokens` | [Pass] |
| C9 | PII masked in logs | `security/masking.py` | `test_masks_*`, `test_audit_details_are_masked` | [Pass] |
| C10 | Tamper-evident audit log | hash chain | `test_audit_chain_detects_tampering` | [Pass] |
| C11 | Loop cannot run away | step cap | `test_loop_stops_after_max_steps` | [Pass] |
| C12 | No data without the owner | `require_owner` on every data, audit and approval endpoint; live stream checks a `?token=` | `test_data_endpoints_refuse_missing_or_wrong_token`, `test_live_stream_refuses_missing_or_wrong_token` | [Pass] |
| C13 | Money moves only to known bills, for the stored amount | `pay_bill` takes only `bill_id` (extra fields rejected); payee/amount built and re-checked by the server | `test_model_cannot_add_an_account_or_amount`, `test_bill_changed_after_approval_is_blocked`, `test_injected_transfer_instruction_cannot_move_money` | [Pass] |
| C14 | Plan actions never run by themselves; supplier messages only to known suppliers | rescue plan is read-only, its actions are held; `send_supplier_message` recipient check | `test_agent_builds_plan_and_holds_every_action`, `test_supplier_messages_go_only_to_existing_suppliers` | [Pass] |
| C15 | Manual entries are owner-only, validated, audited and all-or-nothing for CSV | `/api/data/*` with `require_owner`, Pydantic limits, audit entries, injection flag at entry | `test_manual_entry_requires_the_owner`, `test_invalid_entries_are_rejected`, `test_bad_csv_imports_nothing_and_says_why`, `test_injected_instructions_in_an_entry_are_flagged` | [Pass] |

Attach: `evidence/test_report.txt`.

## 4. Known risks

| # | Risk | Likelihood | Impact | Mitigation now | Next step |
|---|---|---|---|---|---|
| R1 | Model gives a wrong or misleading explanation | Medium | Medium | Numbers come from code; UI shows tool results | Evaluation set of scripted questions |
| R2 | Injection detection is heuristic and can miss novel phrasing | Medium | Low | Policy engine blocks unapproved actions regardless | Classifier-based detection |
| R3 | Owner approves without reading | Medium | Medium | Card shows full payload; sandbox only | Amount thresholds, second confirmation for large actions |
| R4 | Single shared demo owner token; token in browser bundle; live stream passes it in the URL (can reach server logs) | High (demo) | High (prod) | Sandbox only, no real data | OAuth/OIDC login, MFA, per-user sessions, short-lived stream tickets |
| R5 | Forecast assumes recent patterns continue | Medium | Medium | Labelled as estimate; shows inputs | Seasonality, confidence bands |
| R6 | Masking regex over-masks (dates) or misses formats | Low | Low | Errs on masking | Format-specific validators |
| R7 | Transaction data sent to a third-party LLM API | Medium | Medium | PII masked in read tools where possible | Data-processing agreement; regional or self-hosted model |
| R8 | Audit log chain can be rebuilt by someone with DB write access | Low | Medium | Detects edits by app users | Periodic hash anchoring to external storage |
| R9 | Lender terms are mock data | n/a | n/a | Clearly labelled | Real product feeds via partners |
| R10 | In-memory conversation store | Medium | Low | Demo only | Persist conversations |

## 5. Compliance considerations

- Not financial advice; no approval promises; total cost always shown.
- Consent: read-only scope, 90-day expiry, revocable; grants and revocations logged.
- Sample data only; no real customer data processed.

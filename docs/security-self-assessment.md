# Security Self-Assessment Report

SME Finance Copilot · Shenzhen International FinTechathon 2026 · Topic E

## 1. Scope and method

| | |
|---|---|
| System | SME Finance Copilot v0.1.0: web client, FastAPI backend, GLM model via an OpenAI-compatible API |
| Environment | Sandbox deployment with sample data only. The WeBank link is simulated; no real bank, message or payment is involved. |
| Assessed | 20 October 2026, by Team Asparagus |
| Method | (1) Code review against the four attack classes in the judging criteria: induced transfers, data extraction, privilege escalation and prompt injection. (2) 199 automated tests, all passing (`evidence/test_report.txt`). (3) Manual attack scenarios run against the live system, with screenshots and logs (Execution Evidence Report, cases SA-01 to SA-15). |

## 2. Permission-tier implementation

Every tool declares its tier in code (`backend/app/tools/`). The tier is enforced by the server in `PolicyEngine.call()` and `PolicyEngine.execute()` (`backend/app/policy/engine.py`), never by the prompt.

| Tier | Tools | What the server does |
|---|---|---|
| Read-only | `read_transactions`, `forecast_cash_flow`, `find_overdue_invoices`, `list_bills`, `analyze_spending`, `rank_financing`, `build_rescue_plan` | Validates input, runs, logs. Results reach the model with names and notes wrapped as untrusted data. |
| Suggest | `draft_payment_reminders`, `draft_loan_application`, `draft_supplier_message` | Validates input, runs, logs. Output is a draft; nothing leaves the system. |
| Needs approval | `send_payment_reminders`, `submit_loan_application`, `pay_bill`, `send_supplier_message` | **Never runs when the model calls it.** The server builds the payload from its own records, stores it with a SHA-256 fingerprint and shows it to the owner. It runs only after the owner approves that exact payload, with a single-use HMAC token valid for 10 minutes, and after the server re-checks the underlying record. |

The model never sees approval tokens, credentials or customer contact details, and has no tool that accepts an account number or a free payment amount.

## 3. Coverage of the judged attack classes

| Attack class | How it is stopped | Controls |
|---|---|---|
| **Induced transfers** | The only payment tool takes a bill ID; payee and amount come from the stored bill and are re-checked before paying. Every send, submit or payment waits for a payload-bound, single-use approval. Loan terms come from the catalogue. Outgoing messages cannot carry account numbers or payment links. | C1–C5, C13, C14, C18, C19, C22, C29 |
| **Data extraction** | Customer contacts never reach the model and are always returned masked. Outgoing messages are screened for contact details, links and account numbers. The model refuses to reveal its prompt or settings. PII is masked in logs. Every data endpoint requires the owner. | C8, C9, C12, C17, C21 |
| **Privilege escalation** | The model can only request tools through the policy engine and cannot approve its own proposals. Owner endpoints require the owner token; the server refuses to start with a missing, short or published secret. Bank records cannot be edited or deleted. | C1, C6, C8, C12, C15, C16, C20 |
| **Prompt injection** | Untrusted text (notes, memos and every name) is escaped, wrapped and scanned, including fullwidth, invisible-character and Chinese variants. Detections are logged and reported to the owner. Even a fully deceived model can only propose an action, which the owner sees in full. | C7, C10, C11, C23, C24, C28 |

## 4. Controls and evidence

Status verified on 20 October 2026: 199 of 199 automated tests pass. The "Manual" column refers to cases in the Execution Evidence Report.

| # | Control | Implementation | Automated tests | Manual | Status |
|---|---|---|---|---|---|
| C1 | Tier enforced on the server | `policy/engine.py` | `test_needs_approval_tool_is_held_not_run`, `test_agent_cannot_send_without_owner` | SA-05 | Pass |
| C2 | Nothing acts without approval | Pending action + token | `test_execute_without_approval_is_blocked`, `test_declined_action_cannot_run` | TC-04 | Pass |
| C3 | Approval bound to the exact payload | SHA-256 fingerprint + HMAC | `test_payload_changed_after_approval_is_blocked`, `test_owner_must_approve_what_they_saw` | SA-11 | Pass |
| C4 | Approval single use, also under simultaneous requests; 10-minute expiry | Atomic conditional status update; TTL | `test_token_cannot_be_reused`, `test_two_tabs_approving_at_once_run_the_action_once`, `test_one_token_used_twice_at_once_runs_once`, `test_expired_approval_is_blocked` | SA-12 | Pass |
| C5 | Forged tokens rejected | HMAC with a server secret | `test_forged_token_is_blocked` | | Pass |
| C6 | Unknown tools and invalid input blocked | Registry + Pydantic validation | `test_unknown_tool_and_bad_input_are_blocked`, `test_tool_calls_are_parsed_and_bad_arguments_become_empty` | | Pass |
| C7 | Untrusted notes and memos treated as data | Escape + wrap + scan + log | `test_reading_injected_note_is_logged_and_wrapped`, `test_wrapper_cannot_be_closed_from_inside` | SA-01 | Pass |
| C8 | Model never sees approval tokens | `ToolOutcome.for_llm()` | `test_model_never_sees_approval_tokens` | | Pass |
| C9 | PII masked in logs, outbox, API and everything the model reads | `security/masking.py`; free text masked before wrapping for the model | `test_masks_cambodian_phone_numbers`, `test_masks_emails_and_account_numbers`, `test_audit_details_are_masked`, `test_invoice_contact_is_masked_in_api`, `test_model_never_sees_numbers_or_contacts_in_notes` | SA-01, SA-07 | Pass |
| C10 | Tamper-evident audit log | Hash chain + verification | `test_audit_chain_detects_tampering`, `test_every_tool_call_is_audited` | SA-15 | Pass |
| C11 | Agent cannot loop or misreport | Step cap; server-side reply check | `test_loop_stops_after_max_steps`, `test_false_approval_claim_is_corrected`, `test_claiming_sent_while_held_is_corrected`, `test_contracted_or_past_tense_claims_are_corrected` | SA-05 | Pass |
| C12 | No data without the owner | `require_owner` on every data, audit and approval route; unset token refuses everyone | `test_data_endpoints_refuse_missing_or_wrong_token`, `test_every_data_route_needs_the_owner_token`, `test_live_stream_refuses_missing_or_wrong_token`, `test_unset_owner_token_refuses_everyone` | SA-09 | Pass |
| C13 | Money moves only to known bills, for the stored amount | `pay_bill` takes only `bill_id`; payment built and re-checked by the server | `test_model_cannot_add_an_account_or_amount`, `test_bill_changed_after_approval_is_blocked`, `test_editing_or_deleting_a_bill_blocks_its_pending_payment`, `test_injected_transfer_instruction_cannot_move_money` | SA-04 | Pass |
| C14 | Plan actions never run by themselves; supplier messages only to known suppliers | Rescue plan is read-only; recipient check | `test_agent_builds_plan_and_holds_every_action`, `test_supplier_messages_go_only_to_existing_suppliers` | TC-03 | Pass |
| C15 | Owner data entry validated, audited, all-or-nothing for CSV | `/api/data/*` with Pydantic limits and audit entries | `test_manual_entry_requires_the_owner`, `test_invalid_entries_are_rejected`, `test_bad_csv_imports_nothing_and_says_why`, `test_csv_upload_all_or_nothing` | TC-06 | Pass |
| C16 | No default or weak secrets | Startup refuses missing, short or published secrets | `test_default_or_weak_secrets_are_refused`, `test_strong_secrets_are_accepted` | SA-13 | Pass |
| C17 | Outgoing messages cannot leak data | Links, emails, account and phone numbers refused before a card exists and again before sending | `test_unsafe_reminder_is_refused_before_any_card`, `test_unsafe_supplier_message_is_refused`, `test_normal_messages_are_allowed` | SA-06 | Pass |
| C18 | Reminder recipients built and re-checked by the server | Customers, amounts and a contact fingerprint in the approved payload | `test_reminder_card_shows_who_gets_it`, `test_unknown_or_paid_invoice_is_refused`, `test_contact_changed_after_approval_blocks_the_send` | TC-04 | Pass |
| C19 | Loan terms from the catalogue, total cost shown | Server-built quote; unknown products and out-of-limit amounts or terms refused | `test_card_shows_lender_payment_and_total_cost`, `test_application_that_does_not_fit_is_refused`, `test_approved_application_is_submitted_once_in_sandbox` | SA-08 | Pass |
| C20 | Bank records immutable | Server-side lock (403 + audit); corrections as linked entries | `test_bank_row_cannot_be_edited`, `test_bank_row_cannot_be_deleted`, `test_a_payment_the_copilot_made_is_locked_too`, `test_correction_creates_linked_manual_row` | SA-10 | Pass |
| C21 | Prompt and settings not disclosed; clarification before acting; shortfalls stated plainly; bills looked up before paying | System rules 8–13 | `test_model_gets_clarification_privacy_secrecy_and_honesty_rules` | SA-07, TC-09, TC-02 | Pass |
| C22 | Sandbox off fails closed | Action tools refuse to run; action marked failed with the reason | `test_sandbox_off_fails_closed_and_says_why` | SA-14 | Pass |
| C23 | Names wrapped as untrusted at any depth | `wrap_names()` at the model boundary; wrapper tags never shown to the owner | `test_injected_name_is_wrapped_flagged_and_logged`, `test_names_deep_inside_results_are_wrapped`, `test_reply_never_shows_wrapper_tags` | SA-02 | Pass |
| C24 | Disguised and Chinese injections detected | Unicode normalisation, invisible-character removal, Chinese patterns | `test_disguised_and_chinese_injections_are_detected`, `test_ordinary_notes_are_not_flagged` | SA-03 | Pass |
| C25 | Consent enforced: read-only, expires, revocable | Expiry and revocation checked for every sync | `test_expired_or_revoked_consent_stops_the_bank_link`, `test_an_active_bank_link_shows_up_and_revoking_hides_it` | TC-07 | Pass |
| C26 | Every action traceable end to end | Action and payload reference on each audit entry | `test_audit_follows_one_action_from_held_to_done`, `test_reference_is_never_masked_as_an_account_number` | TC-04 | Pass |
| C27 | Spreadsheet formula injection blocked in exports | Leading `=`, `+`, `-`, `@` neutralised | `test_csv_export_neutralises_formulas` | | Pass |
| C28 | Model output cannot inject markup into the page | Chat formatting rendered as plain page elements, never raw HTML | None (no frontend test setup; verified manually) | SA-01, TC-02 | Pass |
| C29 | An action is never held twice | An identical waiting action (same fingerprint) is reused; double-sends blocked in the client | `test_same_action_proposed_twice_gives_one_card` | TC-04 | Pass |

## 5. Known risks

| # | Risk | Likelihood | Impact | Mitigation now | Next step |
|---|---|---|---|---|---|
| R1 | The model gives a wrong or misleading explanation | Medium | Medium | Every number comes from code; the reply check corrects false action claims; the UI shows each tool step | Evaluation set of scripted questions, run before each release |
| R2 | Injection detection is pattern-based and can miss new phrasing or other languages | Medium | Low | Normalised English and Chinese patterns; all untrusted text wrapped regardless; the policy engine blocks unapproved actions whatever the model believes | Classifier-based detection; more languages |
| R3 | The owner approves without reading | Medium | Medium | Card headline states recipients, amounts, lender and total cost; full payload one click away; sandbox only | Second confirmation above an amount threshold |
| R4 | Single shared owner token, visible in the browser bundle; the live stream passes it in the URL, where it can reach server logs | High (demo) | High (production) | Random secret required at startup; sandbox only; no real data | OAuth/OIDC login with MFA, per-user sessions, short-lived stream tickets |
| R5 | The outgoing-message filter is pattern-based; an account number written in words would pass | Low | Medium | The owner sees the full message before approving; recipients are fixed by the server | Allow-list message templates for each action type |
| R6 | The forecast assumes recent patterns continue | Medium | Medium | Labelled as an estimate; inputs shown | Seasonality, confidence bands |
| R7 | Masking can over-mask (long numbers) or miss unusual formats | Low | Low | Errs on the side of masking | Format-specific validators per country |
| R8 | Transaction data is sent to a third-party model API | Medium | Medium | Contacts are never sent; phone numbers, emails and account numbers in free text are masked before the model sees them | Data-processing agreement; regional or self-hosted model (provider is a configuration change) |
| R9 | Someone with direct database write access could rebuild the audit chain; two entries written at the same instant could split it | Low | Medium | Detects any edit made through the application | Single-writer queue; periodic hash anchoring to external storage |
| R10 | Lender terms are mock data | n/a | n/a | Clearly labelled; "only the lender decides approval" | Real product feeds through partners |
| R11 | Conversations are kept in memory without a size limit | Medium | Low | Demo only; reset on restart | Persist conversations with retention limits |
| R12 | An LLM API key was once committed to the public repository history | Low | Medium | The key was revoked; the repository template now has no secrets | Secret scanning in CI |

## 6. Compliance considerations

- **Advice and disclosure:** the copilot ranks financing options but never promises approval; every loan card shows total cost, not just a rate.
- **Consent:** read-only bank access, 90-day expiry and revocation are enforced on every sync; grants and revocations are logged.
- **Data minimisation:** customer contacts never reach the model and are shown masked; outgoing messages may not carry contact details, links or account numbers.
- **Accountability:** every tool call, approval, block, failure and data change is in a tamper-evident log that can be exported as CSV.
- **Safe defaults:** sandbox mode fails closed, and the server refuses to start without strong secrets.
- **Data:** sample data only; no real customer data has been processed.

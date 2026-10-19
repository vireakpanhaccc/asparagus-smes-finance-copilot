"use client";

import { useState } from "react";
import { apiPost, type ApprovalCard as Card } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

// Plain-language headline for the owner. Unknown tools fall back to the tool name; the
// exact payload is always one click away under "Show exact details".
function describe(tool: string, p: Record<string, unknown>): { headline: string; quote?: string } {
  const quote = typeof p.message === "string" ? p.message : undefined;
  switch (tool) {
    case "send_payment_reminders": {
      const n = Array.isArray(p.invoice_ids) ? p.invoice_ids.length : 0;
      return { headline: `Send ${n} payment reminder${n === 1 ? "" : "s"}`, quote };
    }
    case "send_supplier_message":
      return { headline: `Send a message to ${String(p.supplier ?? "your supplier")}`, quote };
    case "submit_loan_application":
      return {
        headline: `Submit a loan application for $${Number(p.amount_usd ?? 0).toLocaleString("en-US")} over ${String(p.term_months ?? "?")} months`,
      };
    case "pay_bill":
      return { headline: `Pay bill #${String(p.bill_id ?? "?")}` };
    default:
      return { headline: tool.replace(/_/g, " "), quote };
  }
}

// Shows the EXACT payload the server stored. "Approve" sends back the payload hash
// the owner saw; the server refuses if anything changed since.
export default function ApprovalCard({ card, onDone }: { card: Card; onDone: (msg: string) => void }) {
  const { t } = useI18n();
  const [busy, setBusy] = useState(false);
  const [state, setState] = useState<"open" | "done" | "declined" | "error">("open");
  const [error, setError] = useState("");
  const { headline, quote } = describe(card.tool, card.payload);

  async function approve() {
    setBusy(true);
    try {
      await apiPost(`/approvals/${card.action_id}/approve`, { payload_hash: card.payload_hash });
      setState("done");
      onDone(`${card.tool}: done in sandbox, logged in the audit log.`);
    } catch (e) {
      setState("error");
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function decline() {
    setBusy(true);
    await apiPost(`/approvals/${card.action_id}/decline`).catch(() => undefined);
    setState("declined");
    setBusy(false);
  }

  return (
    <div className="flex flex-col gap-2 rounded-xl border-[1.5px] border-warn-accent bg-white p-3">
      <div className="text-[11px] font-bold uppercase tracking-wider text-warn">{t("approval.title")}</div>
      <div className="text-[13px] font-semibold leading-snug">{headline}</div>
      {quote && (
        <blockquote className="border-l-2 border-[#c9c9c4] pl-2.5 text-xs leading-snug text-ink-soft">
          “{quote}”
        </blockquote>
      )}
      <details className="text-xs text-muted">
        <summary className="cursor-pointer select-none">Show exact details</summary>
        <pre className="mt-2 max-h-48 overflow-auto rounded bg-paper p-2 text-[11px] text-ink">
          {JSON.stringify(card.payload, null, 2)}
        </pre>
        <p className="mt-1">
          Sandbox only · payload fingerprint <span className="font-mono">{card.payload_hash.slice(0, 12)}…</span>
        </p>
      </details>
      {state === "open" && (
        <div className="flex gap-2">
          <button className="btn-primary flex-1 text-[13px]" disabled={busy} onClick={approve}>
            {t("approval.approve")}
          </button>
          <button className="btn-outline flex-1 text-[13px]" disabled={busy} onClick={decline}>
            {t("approval.decline")}
          </button>
        </div>
      )}
      {state === "done" && <p className="text-sm font-semibold text-teal">Approved and run.</p>}
      {state === "declined" && <p className="text-sm">Declined. Nothing was sent.</p>}
      {state === "error" && <p className="text-sm text-danger">Blocked: {error}</p>}
    </div>
  );
}

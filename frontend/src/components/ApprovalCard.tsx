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
      // Recipients are built by the server from the stored invoices, not by the model.
      const to = Array.isArray(p.recipients)
        ? (p.recipients as { customer?: string; amount?: string }[])
            .map((r) => `${r.customer ?? "?"} (${r.amount ?? "?"})`)
            .join(", ")
        : "";
      return { headline: `Send payment reminders to ${to || "your customers"}`, quote };
    }
    case "send_supplier_message":
      return { headline: `Send a message to ${String(p.supplier ?? "your supplier")}`, quote };
    case "submit_loan_application":
      return {
        headline: `Apply for ${String(p.amount ?? "?")} from ${String(p.lender_product ?? "a lender")} over ${String(p.term_months ?? "?")} months: total cost ${String(p.total_cost ?? "?")}, monthly payment ${String(p.monthly_payment ?? "?")}`,
      };
    case "pay_bill":
      return {
        headline: `Pay ${String(p.amount ?? "?")} to ${String(p.payee ?? `bill #${String(p.bill_id ?? "?")}`)}, due ${String(p.due_on ?? "?")}`,
      };
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
    <div className="flex flex-col gap-2 rounded-xl border-[1.5px] border-brand-amber/60 bg-white p-3">
      <div className="text-[11px] font-bold uppercase tracking-wider text-brand-amber">{t("approval.title")}</div>
      <div className="text-[13px] font-semibold leading-snug">{headline}</div>
      {quote && (
        <blockquote className="border-l-2 border-brand-field pl-2.5 text-xs leading-snug text-brand-sub">
          “{quote}”
        </blockquote>
      )}
      <details className="text-xs text-brand-muted">
        <summary className="cursor-pointer select-none">Show exact details</summary>
        <pre className="mt-2 max-h-48 overflow-auto rounded bg-brand-panel p-2 text-[11px] text-brand-ink">
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
      {state === "done" && <p className="text-sm font-semibold text-brand-blue">Approved and run.</p>}
      {state === "declined" && <p className="text-sm">Declined. Nothing was sent.</p>}
      {state === "error" && <p className="text-sm text-brand-red700">Blocked: {error}</p>}
    </div>
  );
}

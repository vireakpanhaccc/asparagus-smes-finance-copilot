"use client";

import { useState } from "react";
import { apiPost, type ApprovalCard as Card } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

// Shows the EXACT payload the server stored. "Approve" sends back the payload hash
// the owner saw; the server refuses if anything changed since.
export default function ApprovalCard({ card, onDone }: { card: Card; onDone: (msg: string) => void }) {
  const { t } = useI18n();
  const [busy, setBusy] = useState(false);
  const [state, setState] = useState<"open" | "done" | "declined" | "error">("open");
  const [error, setError] = useState("");

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
    <div className="rounded-xl border-2 border-teal bg-teal-light p-4">
      <span className="badge bg-teal text-white">{t("approval.title")}</span>
      <h3 className="mt-2 font-mono text-sm font-semibold">{card.tool}</h3>
      <pre className="mt-2 max-h-48 overflow-auto rounded bg-white p-2 text-xs">
        {JSON.stringify(card.payload, null, 2)}
      </pre>
      <p className="mt-1 text-xs text-black/50">
        Sandbox only · payload fingerprint {card.payload_hash.slice(0, 12)}…
      </p>
      {state === "open" && (
        <div className="mt-3 flex gap-2">
          <button className="btn-primary" disabled={busy} onClick={approve}>
            {t("approval.approve")}
          </button>
          <button className="btn-outline text-danger" disabled={busy} onClick={decline}>
            {t("approval.decline")}
          </button>
        </div>
      )}
      {state === "done" && <p className="mt-3 text-sm font-semibold text-teal">Approved and run.</p>}
      {state === "declined" && <p className="mt-3 text-sm">Declined. Nothing was sent.</p>}
      {state === "error" && <p className="mt-3 text-sm text-danger">Blocked: {error}</p>}
    </div>
  );
}

"use client";

import { useEffect, useState } from "react";
import { apiDelete, type DataSources } from "@/lib/api";
import { shortDate, timeAgo } from "@/lib/format";

// Shows what the bank link can do and lets the owner revoke it. Bank rows already synced stay.
export default function ManageLinkDialog({
  bank,
  onClose,
  onRevoked,
}: {
  bank: DataSources["bank"] | null;
  onClose: () => void;
  onRevoked: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!bank) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [bank, onClose]);

  if (!bank || !bank.grant_id) return null;

  async function revoke() {
    setBusy(true);
    setError("");
    try {
      await apiDelete(`/connect/${bank!.grant_id}`);
      onRevoked();
      onClose();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-[60] grid place-items-center p-4">
      <div className="absolute inset-0 bg-[rgba(20,33,61,0.45)]" onClick={onClose} aria-hidden="true" />
      <div role="dialog" aria-modal="true" aria-labelledby="link-title" className="relative w-full max-w-md space-y-4 rounded-2xl bg-white p-6 shadow-2xl">
        <h2 id="link-title" className="text-lg font-bold">{bank.provider}</h2>
        <dl className="space-y-1.5 text-sm">
          <div className="flex justify-between gap-4"><dt className="text-brand-muted">Access</dt><dd>Read your transactions and balance</dd></div>
          <div className="flex justify-between gap-4"><dt className="text-brand-muted">Scope</dt><dd className="font-mono text-xs">{bank.scope}</dd></div>
          <div className="flex justify-between gap-4"><dt className="text-brand-muted">Until</dt><dd>{bank.expires_at ? shortDate(bank.expires_at) : "–"}</dd></div>
          <div className="flex justify-between gap-4"><dt className="text-brand-muted">Last sync</dt><dd>{bank.last_sync_at ? timeAgo(bank.last_sync_at) : "–"}</dd></div>
        </dl>
        <p className="rounded-lg bg-brand-blue50 p-3 text-sm text-brand-blue700">
          It can never move money with this access. If you revoke it, entries already synced stay in My data, still locked.
        </p>
        {error && <p role="alert" className="text-sm text-brand-red700">{error}</p>}
        <div className="flex justify-end gap-2">
          <button className="btn-outline" onClick={onClose}>Close</button>
          <button className="btn border border-brand-red700 bg-white text-brand-red700 hover:bg-brand-red50" onClick={revoke} disabled={busy}>
            {busy ? "Revoking…" : "Revoke access"}
          </button>
        </div>
      </div>
    </div>
  );
}

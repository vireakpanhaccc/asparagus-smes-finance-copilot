"use client";

import { useEffect, useState } from "react";
import TierBadge from "@/components/TierBadge";
import { apiDownload, apiGet, type AuditEntry } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

const FILTERS = ["all", "held", "blocked", "ignored"] as const;
type Chain = { chain_intact: boolean; first_broken_id: number | null };

export default function AuditPage() {
  const { t } = useI18n();
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>("all");
  const [chain, setChain] = useState<Chain | null>(null);

  async function verify() {
    setChain(await apiGet<Chain>("/audit/verify").catch(() => null));
  }

  // Verify on load so the banner is always current; the button re-checks on demand.
  useEffect(() => {
    apiGet<AuditEntry[]>("/audit").then(setEntries).catch(() => setEntries([]));
    void verify();
  }, []);

  // Counts come from the same data as the rows, so chips always match the table.
  const count = (f: string) => (f === "all" ? entries.length : entries.filter((e) => e.result === f).length);
  const shown = filter === "all" ? entries : entries.filter((e) => e.result === filter);

  return (
    <div className="space-y-4 p-4 pb-24 lg:p-8 lg:pb-24">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold lg:text-[26px]">{t("audit.title")}</h1>
          <p className="mt-1 text-sm text-muted">
            Every action the Copilot took, held or was stopped from taking. Personal data is masked.
          </p>
        </div>
        <div className="flex gap-2">
          <button className="btn-outline" onClick={verify}>{t("audit.verify")}</button>
          <button className="btn-outline" onClick={() => apiDownload("/audit/export.csv", "audit_log.csv")}>
            {t("audit.export")}
          </button>
        </div>
      </header>

      {chain && (
        <div
          role="status"
          className={`rounded-xl border px-4 py-3 text-sm ${
            chain.chain_intact
              ? "border-teal/30 bg-teal-light text-teal-dark"
              : "border-danger/30 bg-danger-bg text-danger"
          }`}
        >
          {chain.chain_intact ? (
            <>
              <b>Chain intact.</b> None of the {entries.length} entries has been changed since it was written.
            </>
          ) : (
            <>
              <b>Tampering detected</b> at entry {chain.first_broken_id}.
            </>
          )}
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        {FILTERS.map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            aria-pressed={filter === f}
            className={`btn min-h-[36px] rounded-full capitalize ${
              filter === f ? "bg-ink-soft text-white" : "border border-line bg-white"
            }`}
          >
            {f} · {count(f)}
          </button>
        ))}
      </div>

      <div className="overflow-x-auto rounded-xl border border-line bg-white">
        <table className="w-full min-w-[640px] table-fixed text-sm">
          <colgroup>
            <col className="w-40" /><col className="w-28" /><col /><col className="w-36" /><col className="w-28" />
          </colgroup>
          <thead className="border-b border-line bg-paper text-left text-xs uppercase tracking-wide text-muted">
            <tr>
              <th className="p-3">Time (UTC)</th><th className="p-3">Who</th><th className="p-3">Action</th>
              <th className="p-3">Tier</th><th className="p-3">Result</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((e) => (
              <tr key={e.id} className={`border-b border-side ${["blocked", "ignored"].includes(e.result) ? "bg-danger-bg/60" : ""}`}>
                <td className="p-3 font-mono text-xs">{e.ts.replace("T", " ").slice(0, 19)}</td>
                <td className="p-3">{e.actor}</td>
                <td className="p-3">
                  <code className="font-mono text-xs">{e.action}</code>
                  <div className="truncate text-xs text-muted" title={e.detail}>{e.detail}</div>
                </td>
                <td className="p-3"><TierBadge value={e.tier} /></td>
                <td className="p-3"><TierBadge value={e.result} /></td>
              </tr>
            ))}
            {shown.length === 0 && (
              <tr><td colSpan={5} className="p-6 text-center text-muted">No entries.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

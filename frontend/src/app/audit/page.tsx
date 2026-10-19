"use client";

import { useEffect, useState } from "react";
import TierBadge from "@/components/TierBadge";
import { apiDownload, apiGet, type AuditEntry } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

const FILTERS = ["all", "held", "blocked", "ignored"] as const;

export default function AuditPage() {
  const { t } = useI18n();
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>("all");
  const [chain, setChain] = useState<string>("");

  useEffect(() => {
    apiGet<AuditEntry[]>("/audit").then(setEntries).catch(() => setEntries([]));
  }, []);

  async function verify() {
    const r = await apiGet<{ chain_intact: boolean; first_broken_id: number | null }>("/audit/verify");
    setChain(r.chain_intact ? "Chain intact: no entry has been changed." : `Tampering detected at entry ${r.first_broken_id}.`);
  }

  // Counts come from the same data as the rows, so chips always match the table.
  const count = (f: string) => (f === "all" ? entries.length : entries.filter((e) => e.result === f).length);
  const shown = filter === "all" ? entries : entries.filter((e) => e.result === filter);

  return (
    <div className="max-w-6xl space-y-4">
      <header className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold">{t("audit.title")}</h1>
          <p className="text-sm text-black/60">
            Every action the Copilot took, held or was blocked from taking. Personal data is masked.
          </p>
        </div>
        <div className="flex gap-2">
          <button className="btn-outline" onClick={verify}>{t("audit.verify")}</button>
          <button className="btn-outline" onClick={() => apiDownload("/audit/export.csv", "audit_log.csv")}>
            {t("audit.export")}
          </button>
        </div>
      </header>
      {chain && <p className="text-sm font-semibold">{chain}</p>}

      <div className="flex gap-2">
        {FILTERS.map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`btn rounded-full ${filter === f ? "bg-ink text-white" : "border border-black/15 bg-white"}`}
          >
            {f} · {count(f)}
          </button>
        ))}
      </div>

      <div className="card overflow-x-auto p-0">
        <table className="w-full table-fixed text-sm">
          <colgroup>
            <col className="w-36" /><col className="w-24" /><col /><col className="w-32" /><col className="w-24" />
          </colgroup>
          <thead className="border-b text-left text-black/60">
            <tr>
              <th className="p-3">Time (UTC)</th><th className="p-3">Who</th><th className="p-3">Action</th>
              <th className="p-3">Tier</th><th className="p-3">Result</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((e) => (
              <tr key={e.id} className={`border-b ${["blocked", "ignored"].includes(e.result) ? "bg-danger-bg/60" : ""}`}>
                <td className="p-3 font-mono text-xs">{e.ts.replace("T", " ").slice(0, 19)}</td>
                <td className="p-3">{e.actor}</td>
                <td className="p-3">
                  <code className="font-mono text-xs">{e.action}</code>
                  <div className="truncate text-xs text-black/60" title={e.detail}>{e.detail}</div>
                </td>
                <td className="p-3"><TierBadge value={e.tier} /></td>
                <td className="p-3"><TierBadge value={e.result} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

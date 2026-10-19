"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import AddDataMenu from "@/components/data/AddDataMenu";
import { BillsTab, InvoicesTab, TransactionsTab, type TabActions } from "@/components/data/DataTabs";
import EntryPanel, { type EntryKind, type PanelMode } from "@/components/data/EntryPanel";
import ManageLinkDialog from "@/components/data/ManageLinkDialog";
import SourceCards from "@/components/data/SourceCards";
import { apiDelete, apiGet, apiUpload, type DataSources } from "@/lib/api";
import { useCopilot } from "@/lib/copilot";
import { shortDate } from "@/lib/format";
import { useI18n } from "@/lib/i18n";

type Tab = "transactions" | "bills" | "invoices";
const TAB_KIND: Record<Tab, EntryKind> = { transactions: "transaction", bills: "bill", invoices: "invoice" };

export default function DataPage() {
  const { t } = useI18n();
  const { send } = useCopilot();
  const [tab, setTab] = useState<Tab>("transactions");
  const [sources, setSources] = useState<DataSources | null>(null);
  const [version, setVersion] = useState(0);
  const [panel, setPanel] = useState<PanelMode | null>(null);
  const [managing, setManaging] = useState(false);
  const [notice, setNotice] = useState<{ ok: boolean; text: string } | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const refresh = useCallback(() => {
    setVersion((v) => v + 1);
    apiGet<DataSources>("/data/sources")
      .then(setSources)
      .catch((e: Error) => setNotice({ ok: false, text: e.message }));
  }, []);
  useEffect(refresh, [refresh]);

  async function remove(path: string) {
    setNotice(null);
    try {
      const r = await apiDelete<{ summary: string }>(path);
      setNotice({ ok: true, text: `Deleted: ${r.summary}. Your forecast no longer includes it.` });
      refresh();
    } catch (e) {
      setNotice({ ok: false, text: (e as Error).message });
    }
  }

  async function upload(file: File | undefined) {
    if (!file) return;
    setNotice(null);
    try {
      const r = await apiUpload<{ rows: number; filename: string }>("/data/upload", file);
      setNotice({ ok: true, text: `${r.rows} transactions imported from ${r.filename}. Your forecast now includes them.` });
      setTab("transactions");
      refresh();
    } catch (e) {
      setNotice({ ok: false, text: (e as Error).message });
    }
    if (fileInput.current) fileInput.current.value = "";
  }

  const actions: TabActions = {
    version,
    onEdit: (kind, row) => setPanel({ type: "edit", kind, row } as PanelMode),
    onCorrect: (row) => setPanel({ type: "correction", row }),
    onDelete: remove,
  };
  const tabs: { key: Tab; label: string; count?: number }[] = [
    { key: "transactions", label: t("data.tab.transactions"), count: sources?.totals.transactions },
    { key: "bills", label: t("data.tab.bills"), count: sources?.totals.bills },
    { key: "invoices", label: t("data.tab.invoices"), count: sources?.totals.invoices },
  ];

  return (
    <div className="space-y-4 px-4 pb-24 pt-6 lg:px-10 lg:py-7 lg:pb-24">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold lg:text-[26px]">{t("data.title")}</h1>
          <p className="mt-1 text-sm text-brand-muted">
            Everything the Copilot reads to build your forecast, and where it came from
            {sources?.range.first && sources.range.last
              ? ` · ${shortDate(sources.range.first)} to ${shortDate(sources.range.last)}`
              : ""}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button className="btn-outline" onClick={() => void send("Check my data for mistakes or gaps")}>
            {t("data.ask")}
          </button>
          <AddDataMenu
            onType={() => setPanel({ type: "new", kind: TAB_KIND[tab] })}
            onUpload={() => fileInput.current?.click()}
          />
        </div>
      </header>

      <input ref={fileInput} type="file" accept=".csv,text/csv" className="sr-only" aria-label="Choose a CSV file"
        onChange={(e) => void upload(e.target.files?.[0])} />

      {notice && (
        <p role={notice.ok ? "status" : "alert"}
          className={`rounded-xl px-4 py-3 text-sm ${notice.ok ? "bg-brand-blue50 text-brand-blue700" : "bg-brand-red50 text-brand-red800"}`}>
          {notice.text}
        </p>
      )}

      <SourceCards
        sources={sources}
        onManage={() => setManaging(true)}
        onUpload={() => fileInput.current?.click()}
        onType={() => setPanel({ type: "new", kind: "transaction" })}
      />

      <div role="tablist" className="flex gap-6 overflow-x-auto border-b border-brand-line">
        {tabs.map((x) => (
          <button
            key={x.key}
            role="tab"
            aria-selected={tab === x.key}
            onClick={() => {
              setTab(x.key);
              setNotice(null);
            }}
            className={`-mb-px min-h-[44px] whitespace-nowrap border-b-2 px-0.5 text-sm ${
              tab === x.key ? "border-brand-blue font-semibold text-brand-ink" : "border-transparent text-brand-sub hover:text-brand-ink"
            }`}
          >
            {x.label}
            {x.count !== undefined && <span className="ml-1 font-mono text-xs"> · {x.count.toLocaleString("en-US")}</span>}
          </button>
        ))}
      </div>

      {tab === "transactions" && <TransactionsTab key="t" {...actions} />}
      {tab === "bills" && <BillsTab key="b" {...actions} />}
      {tab === "invoices" && <InvoicesTab key="i" {...actions} />}

      <EntryPanel
        mode={panel}
        onClose={() => setPanel(null)}
        onSaved={(text) => {
          setNotice({ ok: true, text });
          refresh();
        }}
      />
      <ManageLinkDialog
        bank={managing ? sources?.bank ?? null : null}
        onClose={() => setManaging(false)}
        onRevoked={() => {
          setNotice({ ok: true, text: "Bank access revoked. Entries already synced stay, still locked." });
          refresh();
        }}
      />
    </div>
  );
}

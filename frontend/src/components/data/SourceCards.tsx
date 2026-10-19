"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import type { DataSources } from "@/lib/api";
import { shortDate, timeAgo } from "@/lib/format";

// Where the data came from. Bank is locked; files and typed entries can be edited.
export default function SourceCards({
  sources,
  onManage,
  onUpload,
  onType,
}: {
  sources: DataSources | null;
  onManage: () => void;
  onUpload: () => void;
  onType: () => void;
}) {
  if (!sources) {
    return <div className="grid gap-3 md:grid-cols-3">{[0, 1, 2].map((i) => <div key={i} className="h-[118px] animate-pulse rounded-xl bg-brand-panel" />)}</div>;
  }
  const { bank, files, manual } = sources;
  return (
    <div className="grid gap-3 md:grid-cols-3">
      <Card
        title={bank.linked ? bank.provider ?? "Bank" : "Bank"}
        badge={bank.linked ? <span className="text-xs font-semibold text-brand-blue">● Live</span> : null}
        big={bank.transactions}
        unit="transactions · locked"
        line={
          bank.linked
            ? `Read-only · synced ${bank.last_sync_at ? timeAgo(bank.last_sync_at) : "just now"} · until ${bank.expires_at ? shortDate(bank.expires_at) : "–"}`
            : "No active bank link"
        }
        action={
          bank.linked ? (
            <button className="font-semibold text-brand-blue hover:underline" onClick={onManage}>Manage link</button>
          ) : (
            <Link href="/setup?step=bank" className="font-semibold">Link a bank</Link>
          )
        }
      />
      <Card
        title="Uploaded files"
        big={files.transactions}
        unit="transactions · editable"
        line={files.latest ? `${files.latest.filename} · ${shortDate(files.latest.uploaded_at)}` : "No files yet"}
        action={<button className="font-semibold text-brand-blue hover:underline" onClick={onUpload}>Upload another</button>}
      />
      <Card
        title="Added by you"
        big={manual.total}
        unit="entries · editable"
        line={`${manual.transactions} transactions · ${manual.bills} bills · ${manual.invoices} invoices`}
        action={<button className="font-semibold text-brand-blue hover:underline" onClick={onType}>Type an entry</button>}
      />
    </div>
  );
}

function Card({
  title, badge, big, unit, line, action,
}: {
  title: string; badge?: ReactNode; big: number; unit: string; line: string; action: ReactNode;
}) {
  return (
    <section className="card flex flex-col gap-1.5">
      <div className="flex items-center justify-between gap-2">
        <h2 className="truncate text-sm font-semibold">{title}</h2>
        {badge}
      </div>
      <div className="flex items-baseline gap-2">
        <span className="font-mono text-2xl font-semibold">{big.toLocaleString("en-US")}</span>
        <span className="text-xs text-brand-muted">{unit}</span>
      </div>
      <p className="truncate text-xs text-brand-muted" title={line}>{line}</p>
      <div className="mt-1 text-sm">{action}</div>
    </section>
  );
}

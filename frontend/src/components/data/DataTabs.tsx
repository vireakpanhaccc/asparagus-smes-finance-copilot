"use client";

import { useCallback, useEffect, useState } from "react";
import {
  apiDownload,
  apiGet,
  money,
  type BillRecord,
  type InvoiceRecord,
  type Listing,
  type SourceCounts,
  type TxListing,
  type TxRecord,
} from "@/lib/api";
import { shortDate } from "@/lib/format";
import {
  Cell,
  DataTable,
  InfoLine,
  Pill,
  RowActions,
  SearchBox,
  SignedAmount,
  SourceBadge,
  SourceChips,
  type ChipValue,
} from "./parts";

export type TabActions = {
  version: number; // bump to refetch after a save or delete
  onEdit: (kind: "transaction" | "bill" | "invoice", row: never) => void;
  onCorrect: (row: TxRecord) => void;
  onDelete: (path: string) => Promise<void>;
};

// One search + source filter + data fetch shared by all three tabs. State resets when the
// tab changes because each tab is mounted with its own key.
function useListing<T>(path: string, version: number) {
  const [q, setQ] = useState("");
  const [debounced, setDebounced] = useState("");
  const [source, setSource] = useState<ChipValue>("");
  const [data, setData] = useState<Listing<T> | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const id = setTimeout(() => setDebounced(q), 250);
    return () => clearTimeout(id);
  }, [q]);

  const params = useCallback(() => {
    const p = new URLSearchParams();
    if (debounced) p.set("q", debounced);
    if (source) p.set("source", source);
    return p;
  }, [debounced, source]);

  useEffect(() => {
    setError("");
    apiGet<Listing<T>>(`${path}?${params()}`)
      .then(setData)
      .catch((e: Error) => setError(e.message));
  }, [path, params, version]);

  return { q, setQ, source, setSource, data, error, params };
}

function Toolbar({
  placeholder, q, setQ, counts, source, setSource, extra,
}: {
  placeholder: string; q: string; setQ: (v: string) => void; counts: SourceCounts | null;
  source: ChipValue; setSource: (v: ChipValue) => void; extra?: React.ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <SearchBox value={q} onChange={setQ} placeholder={placeholder} />
      <SourceChips counts={counts} value={source} onChange={setSource} />
      {extra}
    </div>
  );
}

// ---- transactions ------------------------------------------------------------------------------

export function TransactionsTab({ version, onEdit, onCorrect, onDelete }: TabActions) {
  const { q, setQ, source, setSource, data, error, params } = useListing<TxRecord>("/data/transactions", version);
  const [extra, setExtra] = useState<TxRecord[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const first = data as TxListing | null;

  // A fresh first page replaces anything loaded with "Load more".
  useEffect(() => {
    setExtra([]);
    setCursor(first?.next_cursor ?? null);
  }, [first]);

  async function more() {
    if (!cursor) return;
    const p = params();
    p.set("cursor", cursor);
    const page = await apiGet<TxListing>(`/data/transactions?${p}`);
    setExtra((x) => [...x, ...page.rows]);
    setCursor(page.next_cursor);
  }

  const rows = [...(first?.rows ?? []), ...extra];
  return (
    <div className="space-y-3">
      <Toolbar
        placeholder="Search who, category or note…"
        q={q} setQ={setQ} counts={first?.counts ?? null} source={source} setSource={setSource}
        extra={
          <button className="btn-outline ml-auto" onClick={() => void apiDownload(`/data/transactions.csv?${params()}`, "transactions.csv")}>
            Export CSV
          </button>
        }
      />
      <InfoLine>
        Bank entries are locked: nobody, not even the Copilot, can change them. Spotted a mistake? Use{" "}
        <b>Add correction</b> to add an entry that offsets it.
      </InfoLine>
      <DataTable
        head={["Date", "Who", "Category", "Note", "Amount", "Source", ""]}
        widths={["w-24", "", "w-32", "", "w-28", "w-24", "w-44"]}
        empty={error || (first ? "No transactions match." : "Loading…")}
        rows={rows.map((r) => (
          <tr key={r.id} className="border-b border-brand-line2">
            <Cell mono>{shortDate(r.booked_at)}</Cell>
            <Cell>{r.counterparty}</Cell>
            <Cell>{r.category}</Cell>
            <Cell>{r.memo}</Cell>
            <td className="p-3 text-right"><SignedAmount cents={r.amount_cents} /></td>
            <td className="p-3"><SourceBadge source={r.source} /></td>
            <td className="p-3 text-right">
              <RowActions
                locked={r.locked}
                onEdit={() => onEdit("transaction", r as never)}
                onCorrect={() => onCorrect(r)}
                onDelete={() => void onDelete(`/data/transactions/${r.id}`)}
              />
            </td>
          </tr>
        ))}
      />
      {first && (
        <div className="flex items-center justify-between text-sm text-brand-muted">
          <span>Showing {rows.length.toLocaleString("en-US")} of {first.total.toLocaleString("en-US")}</span>
          {cursor && <button className="btn-outline" onClick={() => void more()}>Load more</button>}
        </div>
      )}
    </div>
  );
}

// ---- bills -------------------------------------------------------------------------------------

export function BillsTab({ version, onEdit, onDelete }: TabActions) {
  const { q, setQ, source, setSource, data, error } = useListing<BillRecord>("/data/bills", version);
  return (
    <div className="space-y-3">
      <Toolbar placeholder="Search who you pay…" q={q} setQ={setQ} counts={data?.counts ?? null} source={source} setSource={setSource} />
      <InfoLine>Bills you add are placed on their due dates in the forecast. You can edit or delete them any time.</InfoLine>
      <DataTable
        head={["Due", "Pay to", "Category", "Note", "Amount", "Status", "Source", ""]}
        widths={["w-24", "", "w-28", "", "w-28", "w-36", "w-24", "w-28"]}
        empty={error || (data ? "No bills yet." : "Loading…")}
        rows={(data?.rows ?? []).map((r) => {
          const d = r.days_until_due;
          const label = r.paid ? "Paid" : d < 0 ? `Overdue · ${-d} days` : d === 0 ? "Due today" : `Due in ${d} days`;
          const tone = r.paid ? "blue" : r.in_shortfall_week ? "red" : d < 0 ? "amber" : "neutral";
          return (
            <tr key={r.id} className="border-b border-brand-line2">
              <Cell mono>{shortDate(r.due_on)}</Cell>
              <Cell>{r.payee}</Cell>
              <Cell>{r.category}</Cell>
              <Cell>{r.note}</Cell>
              <td className="p-3 text-right font-mono font-semibold text-brand-red700">{money(r.amount_cents, 2)}</td>
              <td className="p-3"><Pill tone={tone}>{label}</Pill></td>
              <td className="p-3"><SourceBadge source={r.source} /></td>
              <td className="p-3 text-right">
                <RowActions locked={r.locked} onEdit={() => onEdit("bill", r as never)} onDelete={() => void onDelete(`/data/bills/${r.id}`)} />
              </td>
            </tr>
          );
        })}
      />
    </div>
  );
}

// ---- invoices ----------------------------------------------------------------------------------

export function InvoicesTab({ version, onEdit, onDelete }: TabActions) {
  const { q, setQ, source, setSource, data, error } = useListing<InvoiceRecord>("/data/invoices", version);
  return (
    <div className="space-y-3">
      <Toolbar placeholder="Search customers…" q={q} setQ={setQ} counts={data?.counts ?? null} source={source} setSource={setSource} />
      <InfoLine>
        Unpaid invoices power overdue alerts and payment reminders. Notes are treated as data, never as instructions.
      </InfoLine>
      <DataTable
        head={["Due", "Customer", "Contact", "Note", "Amount", "Status", ""]}
        widths={["w-24", "w-36", "w-36", "", "w-28", "w-40", "w-28"]}
        empty={error || (data ? "No invoices yet." : "Loading…")}
        rows={(data?.rows ?? []).map((r) => (
          <tr key={r.id} className="border-b border-brand-line2 align-top">
            <Cell mono>{shortDate(r.due_on)}</Cell>
            <Cell>{r.customer}</Cell>
            <Cell mono>{r.customer_contact}</Cell>
            <td className="p-3">
              <div className="truncate" title={r.note}>{r.note}</div>
              {r.note_flagged && (
                <div className="mt-1"><Pill tone="red">Has instructions · treated as data</Pill></div>
              )}
            </td>
            <td className="p-3 text-right font-mono font-semibold text-brand-blue">{money(r.amount_cents, 2)}</td>
            <td className="p-3">
              {r.paid ? (
                <Pill tone="blue">Paid</Pill>
              ) : r.days_overdue > 0 ? (
                <Pill tone="amber">Overdue · {r.days_overdue} days</Pill>
              ) : (
                <Pill tone="neutral">Due {shortDate(r.due_on)}</Pill>
              )}
            </td>
            <td className="p-3 text-right">
              <RowActions locked={r.locked} onEdit={() => onEdit("invoice", r as never)} onDelete={() => void onDelete(`/data/invoices/${r.id}`)} />
            </td>
          </tr>
        ))}
      />
    </div>
  );
}

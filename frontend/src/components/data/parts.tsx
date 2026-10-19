"use client";

import { useState, type ReactNode } from "react";
import { money, type SourceCounts, type SourceKind } from "@/lib/api";

// ---- amounts: money in is blue with +, money out is red with a true minus sign (U+2212) ----

export function SignedAmount({ cents }: { cents: number }) {
  return (
    <span className={`font-mono font-semibold ${cents < 0 ? "text-brand-red700" : "text-brand-blue"}`}>
      {cents > 0 ? "+" : ""}
      {money(cents, 2)}
    </span>
  );
}

// ---- badges and pills -----------------------------------------------------------------------

const SOURCE_LABEL: Record<SourceKind, string> = { bank: "Bank", file: "File", manual: "By you" };

export function SourceBadge({ source }: { source: SourceKind }) {
  const style = source === "bank" ? "bg-brand-line2 text-brand-sub" : "bg-brand-blue50 text-brand-blue700";
  return <span className={`badge whitespace-nowrap ${style}`}>{SOURCE_LABEL[source]}</span>;
}

export type PillTone = "neutral" | "blue" | "red" | "amber";
const TONES: Record<PillTone, string> = {
  neutral: "bg-brand-panel text-brand-sub",
  blue: "bg-brand-blue50 text-brand-blue700",
  red: "bg-brand-red50 text-brand-red800",
  amber: "bg-brand-amber50 text-brand-amber",
};

export function Pill({ tone, children }: { tone: PillTone; children: ReactNode }) {
  return <span className={`badge whitespace-nowrap ${TONES[tone]}`}>{children}</span>;
}

// ---- info line -------------------------------------------------------------------------------

export function InfoLine({ children }: { children: ReactNode }) {
  return (
    <p className="flex items-start gap-2 rounded-lg bg-brand-panel px-3 py-2.5 text-sm text-brand-sub">
      <svg aria-hidden="true" width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" className="mt-0.5 shrink-0">
        <rect x="3.5" y="7" width="9" height="6.5" rx="1.5" />
        <path d="M5.5 7V5a2.5 2.5 0 0 1 5 0v2" />
      </svg>
      <span>{children}</span>
    </p>
  );
}

// ---- source chips: zero-count chips are hidden, except All -------------------------------------

export type ChipValue = "" | SourceKind;
const CHIPS: { value: ChipValue; label: string; key: keyof SourceCounts }[] = [
  { value: "", label: "All", key: "all" },
  { value: "bank", label: "Bank", key: "bank" },
  { value: "file", label: "File", key: "file" },
  { value: "manual", label: "By you", key: "manual" },
];

export function SourceChips({
  counts,
  value,
  onChange,
}: {
  counts: SourceCounts | null;
  value: ChipValue;
  onChange: (v: ChipValue) => void;
}) {
  return (
    <>
      {CHIPS.filter((c) => c.value === "" || (counts?.[c.key] ?? 0) > 0 || c.value === value).map((c) => (
        <button
          key={c.label}
          aria-pressed={value === c.value}
          onClick={() => onChange(c.value)}
          className={`btn min-h-[36px] rounded-full px-3.5 ${
            value === c.value
              ? "bg-brand-ink text-white"
              : "border border-brand-blue100 bg-white text-brand-ink hover:bg-brand-panel"
          }`}
        >
          {c.label}
          <span className="ml-1 font-mono text-xs">· {counts?.[c.key] ?? 0}</span>
        </button>
      ))}
    </>
  );
}

// ---- search ------------------------------------------------------------------------------------

export function SearchBox({
  value,
  onChange,
  placeholder,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder: string;
}) {
  return (
    <>
      <label className="sr-only" htmlFor="data-search">
        {placeholder}
      </label>
      <input
        id="data-search"
        type="search"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="h-11 w-full rounded-full border border-brand-field bg-brand-panel px-4 text-sm sm:w-[280px]"
      />
    </>
  );
}

// ---- table: fixed layout so nothing is cut off; long text truncates with a tooltip ----------------

export function DataTable({
  head,
  widths,
  rows,
  empty,
}: {
  head: string[];
  widths: string[];
  rows: ReactNode[];
  empty: string;
}) {
  return (
    <div className="overflow-x-auto rounded-xl border border-brand-line bg-white">
      <table className="w-full min-w-[820px] table-fixed text-sm">
        <colgroup>
          {widths.map((w, i) => (
            <col key={i} className={w} />
          ))}
        </colgroup>
        <thead className="border-b border-brand-line bg-brand-panel text-left text-xs uppercase tracking-wide text-brand-muted">
          <tr>
            {head.map((h, i) => (
              <th key={i} scope="col" className={`p-3 font-semibold ${h === "Amount" ? "text-right" : ""}`}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows}
          {rows.length === 0 && (
            <tr>
              <td colSpan={head.length} className="p-6 text-center text-brand-muted">
                {empty}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

export function Cell({ children, mono, right }: { children: ReactNode; mono?: boolean; right?: boolean }) {
  const text = typeof children === "string" ? children : undefined;
  return (
    <td title={text} className={`truncate p-3 ${mono ? "font-mono text-xs" : ""} ${right ? "text-right" : ""}`}>
      {children}
    </td>
  );
}

// ---- row actions ---------------------------------------------------------------------------------

export function RowActions({
  locked,
  onEdit,
  onCorrect,
  onDelete,
}: {
  locked: boolean;
  onEdit: () => void;
  onCorrect?: () => void;
  onDelete: () => void;
}) {
  const [asking, setAsking] = useState(false);
  if (locked) {
    return (
      <span className="inline-flex items-center gap-2.5 whitespace-nowrap text-xs">
        <span className="text-brand-muted">🔒 Locked</span>
        {onCorrect && (
          <button className="font-semibold text-brand-blue hover:underline" onClick={onCorrect}>
            Add correction
          </button>
        )}
      </span>
    );
  }
  if (asking) {
    return (
      <span className="inline-flex items-center gap-2.5 whitespace-nowrap text-xs">
        <button className="font-semibold text-brand-red700 hover:underline" onClick={onDelete}>
          Confirm
        </button>
        <button className="text-brand-muted hover:underline" onClick={() => setAsking(false)}>
          Cancel
        </button>
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-3 whitespace-nowrap text-xs">
      <button className="font-semibold text-brand-blue hover:underline" onClick={onEdit}>
        Edit
      </button>
      <button className="font-semibold text-brand-red700 hover:underline" onClick={() => setAsking(true)}>
        Delete
      </button>
    </span>
  );
}

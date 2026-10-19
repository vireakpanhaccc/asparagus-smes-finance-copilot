"use client";

import Link from "next/link";
import { useState, type FormEvent, type ReactNode } from "react";
import { apiPost } from "@/lib/api";

// Manual entry for businesses with no bank link, or for what the link misses
// (cash sales, upcoming bills, invoices). The server validates and audits every entry.

type Tab = "transaction" | "bill" | "invoice";
type Added = { status: string; summary?: string };

const TABS: { key: Tab; label: string }[] = [
  { key: "transaction", label: "Transaction" },
  { key: "bill", label: "Bill" },
  { key: "invoice", label: "Invoice" },
];
const INPUT = "h-11 w-full rounded-lg border border-line bg-white px-3 text-sm";
// Local date, not UTC: in UTC+7 a UTC date is still "yesterday" before 7 a.m.
const today = () => {
  const d = new Date();
  return new Date(d.getTime() - d.getTimezoneOffset() * 60_000).toISOString().slice(0, 10);
};

export default function ManualEntryCard() {
  const [tab, setTab] = useState<Tab>("transaction");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null);

  async function run(form: HTMLFormElement, call: () => Promise<Added>) {
    setBusy(true);
    setResult(null);
    try {
      const r = await call();
      const what = `Added: ${r.summary}`;
      setResult({ ok: true, text: `${what}. Your forecast now includes it.` });
      form.reset();
    } catch (e) {
      setResult({ ok: false, text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }

  function submit(path: string, toBody: (f: FormData) => unknown) {
    return (e: FormEvent<HTMLFormElement>) => {
      e.preventDefault();
      const form = e.currentTarget;
      const body = toBody(new FormData(form));
      run(form, () => apiPost<Added>(path, body));
    };
  }

  const text = (f: FormData, k: string) => String(f.get(k) ?? "").trim();
  const amount = (f: FormData) => Number(f.get("amount_usd"));

  return (
    <div className="card space-y-4">
      <div>
        <h2 id="manual-entry" className="font-semibold">Or add entries by hand</h2>
        <p className="text-sm text-muted">
          No bank link, or something it missed? Add it here. Every entry is checked and recorded in
          the audit log.
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => {
              setTab(t.key);
              setResult(null);
            }}
            className={`btn rounded-full ${tab === t.key ? "bg-ink-soft text-white" : "border border-line bg-white"}`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "transaction" && (
        <form
          className="grid gap-3 sm:grid-cols-2"
          onSubmit={submit("/manual/transactions", (f) => ({
            booked_on: text(f, "booked_on"),
            direction: text(f, "direction"),
            amount_usd: amount(f),
            counterparty: text(f, "counterparty"),
            category: text(f, "category") || "Uncategorized",
            memo: text(f, "memo"),
          }))}
        >
          <Field label="Date">
            <input name="booked_on" type="date" defaultValue={today()} max={today()} required className={INPUT} />
          </Field>
          <Field label="Money in or out">
            <select name="direction" className={INPUT} defaultValue="in">
              <option value="in">Money in</option>
              <option value="out">Money out</option>
            </select>
          </Field>
          <Field label="Amount ($)">
            <input name="amount_usd" type="number" min="0.01" step="0.01" required className={INPUT} />
          </Field>
          <Field label="Who">
            <input name="counterparty" placeholder="e.g. Cash sales" maxLength={120} required className={INPUT} />
          </Field>
          <Field label="Category">
            <input name="category" placeholder="e.g. Sales, Rent, Supplies" maxLength={120} className={INPUT} />
          </Field>
          <Field label="Note (optional)">
            <input name="memo" maxLength={500} className={INPUT} />
          </Field>
          <Submit busy={busy} label="Add transaction" />
        </form>
      )}

      {tab === "bill" && (
        <form
          className="grid gap-3 sm:grid-cols-2"
          onSubmit={submit("/manual/bills", (f) => ({
            payee: text(f, "payee"),
            amount_usd: amount(f),
            due_on: text(f, "due_on"),
          }))}
        >
          <Field label="Pay to">
            <input name="payee" placeholder="e.g. Annual shop insurance" maxLength={120} required className={INPUT} />
          </Field>
          <Field label="Amount ($)">
            <input name="amount_usd" type="number" min="0.01" step="0.01" required className={INPUT} />
          </Field>
          <Field label="Due date">
            <input name="due_on" type="date" min={today()} required className={INPUT} />
          </Field>
          <Submit busy={busy} label="Add bill" />
        </form>
      )}

      {tab === "invoice" && (
        <form
          className="grid gap-3 sm:grid-cols-2"
          onSubmit={submit("/manual/invoices", (f) => ({
            customer: text(f, "customer"),
            amount_usd: amount(f),
            due_on: text(f, "due_on"),
            customer_contact: text(f, "customer_contact"),
            note: text(f, "note"),
          }))}
        >
          <Field label="Customer">
            <input name="customer" maxLength={120} required className={INPUT} />
          </Field>
          <Field label="Amount they owe ($)">
            <input name="amount_usd" type="number" min="0.01" step="0.01" required className={INPUT} />
          </Field>
          <Field label="Due date">
            <input name="due_on" type="date" required className={INPUT} />
          </Field>
          <Field label="Phone or email (optional)">
            <input name="customer_contact" maxLength={120} className={INPUT} />
          </Field>
          <Field label="Note (optional)">
            <input name="note" maxLength={500} className={INPUT} />
          </Field>
          <Submit busy={busy} label="Add invoice" />
        </form>
      )}


      {result && (
        <p className={`text-sm ${result.ok ? "text-teal" : "text-danger"}`}>
          {result.text}{" "}
          {result.ok && (
            <Link href="/overview" className="font-semibold underline">
              See the overview
            </Link>
          )}
        </p>
      )}
    </div>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="space-y-1 text-sm">
      <span className="text-muted">{label}</span>
      {children}
    </label>
  );
}

function Submit({ busy, label }: { busy: boolean; label: string }) {
  return (
    <div className="sm:col-span-2">
      <button className="btn-primary" disabled={busy}>
        {busy ? "Saving…" : label}
      </button>
    </div>
  );
}

"use client";

import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import {
  apiPatch,
  apiPost,
  money,
  type BillRecord,
  type InvoiceRecord,
  type TxRecord,
} from "@/lib/api";
import { today } from "@/lib/format";

export type EntryKind = "transaction" | "bill" | "invoice";
export type PanelMode =
  | { type: "new"; kind: EntryKind }
  | { type: "edit"; kind: "transaction"; row: TxRecord }
  | { type: "edit"; kind: "bill"; row: BillRecord }
  | { type: "edit"; kind: "invoice"; row: InvoiceRecord }
  | { type: "correction"; row: TxRecord };

const KINDS: { key: EntryKind; label: string }[] = [
  { key: "transaction", label: "Transaction" },
  { key: "bill", label: "Bill to pay" },
  { key: "invoice", label: "Invoice to collect" },
];
const CATEGORIES = {
  in: ["Sales", "Catering", "Other income"],
  out: ["Ingredients", "Supplies", "Wages", "Rent", "Utilities", "Other"],
  bill: ["Rent", "Supplies", "Equipment", "Insurance", "Tax", "Other"],
};

type Form = {
  direction: "in" | "out";
  amount: string;
  who: string;
  date: string;
  category: string;
  note: string;
  contact: string;
};
type Errors = Partial<Record<keyof Form, string>>;

const addDays = (iso: string, days: number) => {
  const d = new Date(`${iso}T12:00:00`);
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
};

function initial(mode: PanelMode): Form {
  const blank: Form = { direction: "in", amount: "", who: "", date: today(), category: "", note: "", contact: "" };
  if (mode.type === "new") return { ...blank, date: mode.kind === "bill" ? today() : today() };
  if (mode.type === "correction") {
    const r = mode.row; // prefill the offsetting entry: same amount, opposite direction
    return { ...blank, direction: r.amount_cents < 0 ? "in" : "out", amount: (Math.abs(r.amount_cents) / 100).toFixed(2) };
  }
  if (mode.kind === "transaction") {
    const r = mode.row;
    return {
      ...blank, direction: r.amount_cents < 0 ? "out" : "in", amount: (Math.abs(r.amount_cents) / 100).toFixed(2),
      who: r.counterparty, date: r.booked_at, category: r.category, note: r.memo,
    };
  }
  if (mode.kind === "bill") {
    const r = mode.row;
    return { ...blank, amount: (r.amount_cents / 100).toFixed(2), who: r.payee, date: r.due_on, category: r.category, note: r.note };
  }
  const r = mode.row; // the contact is masked by the server, so it starts empty (see below)
  return { ...blank, amount: (r.amount_cents / 100).toFixed(2), who: r.customer, date: r.due_on, note: r.note };
}

function validate(kind: EntryKind, correction: boolean, f: Form): Errors {
  const e: Errors = {};
  if (!/^\d+(\.\d{1,2})?$/.test(f.amount.trim())) e.amount = "Enter an amount with up to 2 decimals, like 12.50.";
  else if (Number(f.amount) <= 0) e.amount = "The amount must be more than 0.";
  else if (Number(f.amount) > 1_000_000) e.amount = "The amount can't be more than $1,000,000.";
  if (!correction) {
    const name = f.who.trim();
    if (name.length < 1 || name.length > 120) e.who = "Enter 1 to 120 characters.";
    const t = today();
    if (!f.date) e.date = "Pick a date.";
    else if (f.date < addDays(t, -365) || f.date > addDays(t, 365)) e.date = "The date must be within a year of today.";
    else if (kind === "transaction" && f.date > t) e.date = "A transaction can't be in the future.";
    else if (kind === "bill" && f.date < t) e.date = "A bill must be due today or later.";
  }
  if (f.note.length > 500) e.note = "Keep the note to 500 characters.";
  if (f.contact.length > 120) e.contact = "Keep this to 120 characters.";
  return e;
}

export default function EntryPanel({
  mode,
  onClose,
  onSaved,
}: {
  mode: PanelMode | null;
  onClose: () => void;
  onSaved: (message: string) => void;
}) {
  const [kind, setKind] = useState<EntryKind>("transaction");
  const [form, setForm] = useState<Form>(initial({ type: "new", kind: "transaction" }));
  const [errors, setErrors] = useState<Errors>({});
  const [serverError, setServerError] = useState("");
  const [busy, setBusy] = useState(false);
  const dialog = useRef<HTMLDivElement>(null);
  const opener = useRef<Element | null>(null);

  // Reset whenever the panel is opened for something new; remember who to give focus back to.
  useEffect(() => {
    if (!mode) return;
    opener.current = document.activeElement;
    setKind(mode.type === "new" ? mode.kind : mode.type === "correction" ? "transaction" : mode.kind);
    setForm(initial(mode));
    setErrors({});
    setServerError("");
    const id = setTimeout(() => dialog.current?.querySelector<HTMLElement>("[data-autofocus]")?.focus(), 30);
    return () => {
      clearTimeout(id);
      if (opener.current instanceof HTMLElement) opener.current.focus();
    };
  }, [mode]);

  if (!mode) return null;
  const m: PanelMode = mode; // a const, so the narrowing below survives inside save()
  const correction = mode.type === "correction";
  const editing = mode.type === "edit";
  const set = <K extends keyof Form>(k: K, v: Form[K]) => setForm((f) => ({ ...f, [k]: v }));

  function trapFocus(e: KeyboardEvent) {
    if (e.key === "Escape") {
      e.stopPropagation();
      onClose();
      return;
    }
    if (e.key !== "Tab" || !dialog.current) return;
    const items = Array.from(
      dialog.current.querySelectorAll<HTMLElement>("button, input, select, textarea, a[href], [tabindex]:not([tabindex='-1'])"),
    ).filter((el) => !el.hasAttribute("disabled") && el.offsetParent !== null);
    if (items.length === 0) return;
    const first = items[0];
    const last = items[items.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  }

  async function save() {
    const found = validate(kind, correction, form);
    setErrors(found);
    setServerError("");
    if (Object.keys(found).length > 0) {
      dialog.current?.querySelector<HTMLElement>("[aria-invalid='true']")?.focus();
      return;
    }
    const amount = Number(form.amount);
    const note = form.note.trim();
    setBusy(true);
    try {
      if (m.type === "correction") {
        await apiPost(`/data/transactions/${m.row.id}/correction`, { direction: form.direction, amount_usd: amount, note });
        onSaved("Correction added. The bank entry itself is unchanged.");
      } else if (m.type === "edit") {
        if (m.kind === "transaction") {
          await apiPatch(`/data/transactions/${m.row.id}`, {
            booked_on: form.date, direction: form.direction, amount_usd: amount,
            counterparty: form.who.trim(), category: form.category.trim() || "Uncategorized", memo: note,
          });
        } else if (m.kind === "bill") {
          await apiPatch(`/data/bills/${m.row.id}`, {
            payee: form.who.trim(), amount_usd: amount, due_on: form.date, category: form.category || "Other", note,
          });
        } else {
          await apiPatch(`/data/invoices/${m.row.id}`, {
            customer: form.who.trim(), amount_usd: amount, due_on: form.date, note,
            // blank keeps the stored contact: the form only ever sees the masked one
            ...(form.contact.trim() ? { customer_contact: form.contact.trim() } : {}),
          });
        }
        onSaved("Changes saved.");
      } else {
        const path = kind === "transaction" ? "transactions" : kind === "bill" ? "bills" : "invoices";
        const body =
          kind === "transaction"
            ? { booked_on: form.date, direction: form.direction, amount_usd: amount, counterparty: form.who.trim(),
                category: form.category.trim() || "Uncategorized", memo: note }
            : kind === "bill"
              ? { payee: form.who.trim(), amount_usd: amount, due_on: form.date, category: form.category || "Other", note }
              : { customer: form.who.trim(), amount_usd: amount, due_on: form.date, customer_contact: form.contact.trim(), note };
        const r = await apiPost<{ summary: string }>(`/data/${path}`, body);
        onSaved(`Added: ${r.summary}.`);
      }
      onClose();
    } catch (e) {
      setServerError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const title = correction ? "Add correction" : editing ? "Edit entry" : "Type an entry";
  const saveLabel = correction
    ? "Add correction"
    : editing
      ? "Save changes"
      : kind === "transaction"
        ? form.direction === "in" ? "Save money in" : "Save money out"
        : kind === "bill" ? "Save bill" : "Save invoice";
  const chips = kind === "bill" ? CATEGORIES.bill : form.direction === "in" ? CATEGORIES.in : CATEGORIES.out;
  const input = "h-11 w-full rounded-lg border border-brand-field bg-brand-panel px-3 text-sm";

  return (
    <div className="fixed inset-0 z-[60]" onKeyDown={trapFocus}>
      <div className="absolute inset-0 bg-[rgba(20,33,61,0.45)]" onClick={onClose} aria-hidden="true" />
      <div
        ref={dialog}
        role="dialog"
        aria-modal="true"
        aria-labelledby="entry-title"
        className="absolute inset-y-0 right-0 flex w-full flex-col bg-white shadow-2xl sm:w-[480px]"
      >
        <div className="flex items-center justify-between border-b border-brand-line px-5 py-4">
          <h2 id="entry-title" className="text-lg font-bold">{title}</h2>
          <button aria-label="Close" onClick={onClose} className="grid h-11 w-11 place-items-center rounded-lg border border-brand-line">
            <svg aria-hidden="true" width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
              <path d="M3 3l10 10M13 3L3 13" />
            </svg>
          </button>
        </div>

        <div className="flex-1 space-y-4 overflow-y-auto px-5 py-4">
          {mode.type === "new" && (
            <div role="tablist" aria-label="Entry type" className="grid grid-cols-3 gap-1 rounded-lg bg-brand-line2 p-1">
              {KINDS.map((k) => (
                <button
                  key={k.key}
                  role="tab"
                  aria-selected={kind === k.key}
                  onClick={() => {
                    setKind(k.key);
                    setErrors({});
                    setForm((f) => ({ ...f, date: today(), category: "" }));
                  }}
                  className={`min-h-[40px] rounded-md px-1 text-[13px] font-semibold ${
                    kind === k.key ? "bg-white text-brand-ink shadow-sm" : "text-brand-sub"
                  }`}
                >
                  {k.label}
                </button>
              ))}
            </div>
          )}

          {correction && (
            <p className="rounded-lg bg-brand-panel p-3 text-sm text-brand-sub">
              Bank entries are locked, so you can&apos;t change them. This adds your own entry that offsets{" "}
              <b>{mode.row.counterparty}</b> ({money(mode.row.amount_cents, 2)} on {mode.row.booked_at}). Adjust the
              amount if only part of it was wrong.
            </p>
          )}

          {kind === "transaction" && (
            <div className="grid grid-cols-2 gap-2" role="group" aria-label="Money in or out">
              <button
                aria-pressed={form.direction === "in"}
                onClick={() => { set("direction", "in"); set("category", ""); }}
                className={`min-h-[44px] rounded-lg border-2 text-sm font-semibold ${
                  form.direction === "in" ? "border-brand-blue bg-brand-blue50 text-brand-blue700" : "border-brand-line text-brand-sub"
                }`}
              >
                + Money in
              </button>
              <button
                aria-pressed={form.direction === "out"}
                onClick={() => { set("direction", "out"); set("category", ""); }}
                className={`min-h-[44px] rounded-lg border-2 text-sm font-semibold ${
                  form.direction === "out" ? "border-brand-red700 bg-brand-red50 text-brand-red800" : "border-brand-line text-brand-sub"
                }`}
              >
                − Money out
              </button>
            </div>
          )}

          <Field label="Amount" error={errors.amount} id="f-amount">
            <div className="relative">
              <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 font-mono text-2xl text-brand-muted">$</span>
              <input
                id="f-amount"
                data-autofocus
                inputMode="decimal"
                placeholder="0.00"
                value={form.amount}
                onChange={(e) => set("amount", e.target.value)}
                aria-invalid={!!errors.amount}
                aria-describedby={errors.amount ? "f-amount-err" : undefined}
                className="h-14 w-full rounded-lg border border-brand-field bg-brand-panel pl-9 pr-3 font-mono text-2xl font-semibold"
              />
            </div>
          </Field>

          {!correction && (
            <>
              <Field label={kind === "bill" ? "Pay to" : kind === "invoice" ? "Customer" : "Who"} error={errors.who} id="f-who">
                <input id="f-who" value={form.who} maxLength={120} onChange={(e) => set("who", e.target.value)}
                  aria-invalid={!!errors.who} aria-describedby={errors.who ? "f-who-err" : undefined} className={input} />
              </Field>
              <Field label={kind === "bill" || kind === "invoice" ? "Due date" : "Date"} error={errors.date} id="f-date">
                <input id="f-date" type="date" value={form.date} onChange={(e) => set("date", e.target.value)}
                  min={kind === "bill" ? today() : addDays(today(), -365)}
                  max={kind === "transaction" ? today() : addDays(today(), 365)}
                  aria-invalid={!!errors.date} aria-describedby={errors.date ? "f-date-err" : undefined} className={input} />
              </Field>
              {kind !== "invoice" && (
                <fieldset>
                  <legend className="mb-1.5 text-sm font-semibold">Category</legend>
                  <div className="flex flex-wrap gap-1.5">
                    {chips.map((c) => (
                      <button
                        key={c}
                        aria-pressed={form.category === c}
                        onClick={() => set("category", form.category === c ? "" : c)}
                        className={`min-h-[36px] rounded-full border px-3.5 text-[13px] font-medium ${
                          form.category === c ? "border-brand-blue bg-brand-blue50 text-brand-blue700" : "border-brand-blue100 text-brand-ink"
                        }`}
                      >
                        {c}
                      </button>
                    ))}
                  </div>
                </fieldset>
              )}
              {kind === "invoice" && (
                <Field
                  label="Customer phone or email"
                  error={errors.contact}
                  id="f-contact"
                  helper={
                    editing && mode.kind === "invoice" && mode.row.customer_contact
                      ? `Leave blank to keep the current contact (${mode.row.customer_contact}). Used only for reminders you approve. Masked in every log.`
                      : "Used only for reminders you approve. Masked in every log."
                  }
                >
                  <input id="f-contact" value={form.contact} maxLength={120} onChange={(e) => set("contact", e.target.value)}
                    aria-invalid={!!errors.contact} className={input} />
                </Field>
              )}
            </>
          )}

          <Field label="Note (optional)" error={errors.note} id="f-note">
            <textarea id="f-note" rows={3} value={form.note} onChange={(e) => set("note", e.target.value)}
              aria-invalid={!!errors.note} className="w-full rounded-lg border border-brand-field bg-brand-panel p-3 text-sm" />
            <div className="mt-1 text-right text-xs text-brand-muted">{form.note.length}/500</div>
          </Field>

          {serverError && (
            <p role="alert" className="rounded-lg bg-brand-red50 p-3 text-sm text-brand-red800">{serverError}</p>
          )}
        </div>

        <div className="space-y-2 border-t border-brand-line px-5 py-4">
          <button className="btn-primary w-full" onClick={save} disabled={busy}>
            {busy ? "Saving…" : saveLabel}
          </button>
          <p className="text-center text-xs text-brand-muted">
            Marked &ldquo;By you&rdquo; · you can edit or delete it later · recorded in the audit log
          </p>
        </div>
      </div>
    </div>
  );
}

function Field({
  label, error, id, helper, children,
}: {
  label: string; error?: string; id: string; helper?: string; children: ReactNode;
}) {
  return (
    <div>
      <label htmlFor={id} className="mb-1.5 block text-sm font-semibold">{label}</label>
      {children}
      {helper && !error && <p className="mt-1 text-xs text-brand-muted">{helper}</p>}
      {error && <p id={`${id}-err`} className="mt-1 text-xs font-semibold text-brand-red700">{error}</p>}
    </div>
  );
}

"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type DragEvent, type FormEvent } from "react";
import ManualEntryCard from "@/components/ManualEntryCard";
import { apiDelete, apiPost, apiUpload, money, streamUrl } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

type Grant = { id: number; provider: string; scope: string; expires_at: string };
type LiveTx = { id: number; amount_cents: number; counterparty: string; booked_at: string };

// Assumed partner integration, simulated in the sandbox. No real bank is contacted.
const PROVIDERS = ["WeBank (mock)", "Cambodian bank / KHQR (mock)", "Mobile wallet (mock)"];

export default function ConnectPage() {
  const { t } = useI18n();
  const [provider, setProvider] = useState(PROVIDERS[0]);
  const [grant, setGrant] = useState<Grant | null>(null);
  const [live, setLive] = useState<LiveTx[]>([]);
  const [connectError, setConnectError] = useState("");
  const source = useRef<EventSource | null>(null);

  useEffect(() => () => source.current?.close(), []);

  async function connect() {
    setConnectError("");
    try {
      const g = await apiPost<Grant>("/connect", { provider, days_valid: 90 });
      setGrant(g);
      const es = new EventSource(streamUrl("/connect/live"));
      es.addEventListener("transaction", (ev) => {
        const tx = JSON.parse((ev as MessageEvent).data) as LiveTx;
        setLive((l) => [tx, ...l].slice(0, 8));
      });
      es.addEventListener("stopped", () => es.close());
      source.current = es;
    } catch (e) {
      setConnectError((e as Error).message);
    }
  }

  async function revoke() {
    if (!grant) return;
    await apiDelete(`/connect/${grant.id}`);
    source.current?.close();
    setGrant(null);
    setLive([]);
  }

  return (
    <div className="space-y-5 p-4 pb-24 lg:p-8 lg:pb-24">
      <header>
        <h1 className="text-xl font-bold lg:text-[26px]">Connect your data</h1>
        <p className="mt-1 text-sm text-muted">
          Choose how the Copilot gets your transactions. You only need one.
        </p>
      </header>

      <div className="grid gap-4 lg:grid-cols-2">
        {/* Option A: bank link */}
        <section className="card flex flex-col gap-3">
          <div className="flex items-center justify-between gap-2">
            <h2 className="font-semibold">A · Link a bank account</h2>
            <span className="badge bg-teal-light text-teal">Recommended</span>
          </div>
          <p className="text-sm text-muted">Transactions sync automatically. No typing.</p>
          <fieldset className="flex flex-col gap-1" disabled={!!grant}>
            <legend className="mb-1 text-sm font-semibold">Choose your provider</legend>
            {PROVIDERS.map((p) => (
              <label key={p} className="flex min-h-[44px] items-center gap-2 text-sm">
                <input
                  type="radio"
                  name="provider"
                  checked={provider === p}
                  onChange={() => setProvider(p)}
                  className="h-4 w-4 accent-teal"
                />
                {p}
              </label>
            ))}
          </fieldset>
          <div className="rounded-lg bg-paper p-3 text-sm">
            <div className="mb-1 font-semibold">The Copilot is asking for:</div>
            <div>✓ Read your transactions and balance</div>
            <div>✓ For 90 days, and you can revoke it any time</div>
            <div className="text-danger">✕ It can never move money with this access</div>
          </div>
          <button className="btn-primary" onClick={connect} disabled={!!grant}>
            {grant ? "Connected" : "Allow read-only access"}
          </button>
          {connectError && <p className="text-sm text-danger">{connectError}</p>}
        </section>

        {/* Option B: CSV */}
        <CsvCard />
      </div>

      {/* Connected sources */}
      {grant && (
        <section className="card space-y-3">
          <div className="text-sm font-semibold">Connected sources</div>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
            <span className="h-2.5 w-2.5 rounded-full bg-teal" aria-hidden="true" />
            <b>{grant.provider}</b>
            <span className="text-muted">
              {grant.scope} · until {grant.expires_at.slice(0, 10)} · live sync on
            </span>
            <button className="btn-outline ml-auto text-danger" onClick={revoke}>
              Revoke access
            </button>
          </div>
          <ul className="divide-y divide-side text-sm">
            {live.map((tx) => (
              <li key={tx.id} className="flex justify-between py-2">
                <span>{tx.counterparty}</span>
                <span className="font-mono">{money(tx.amount_cents, 2)}</span>
              </li>
            ))}
            {live.length === 0 && <li className="py-2 text-muted">Waiting for new transactions…</li>}
          </ul>
        </section>
      )}

      <ManualEntryCard />

      <p className="text-xs text-muted">
        Simulated in the sandbox. Every grant and revoke is written to the audit log. {t("connect.scope")}
      </p>
    </div>
  );
}

// Transactions CSV goes to /manual/csv (all rows or none). Bills and invoices are entered
// by hand below, because the server has no CSV import for them.
function CsvCard() {
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [drag, setDrag] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null);
  const input = useRef<HTMLInputElement>(null);

  function pick(f: File | undefined | null) {
    setResult(null);
    setFile(f ?? null);
  }

  function onDrop(e: DragEvent) {
    e.preventDefault();
    setDrag(false);
    pick(e.dataTransfer.files[0]);
  }

  async function upload(e: FormEvent) {
    e.preventDefault();
    if (!file) {
      setResult({ ok: false, text: "Choose a CSV file first." });
      return;
    }
    setBusy(true);
    setResult(null);
    try {
      const r = await apiUpload<{ rows: number }>("/manual/csv", file);
      setResult({ ok: true, text: `${r.rows} transactions imported. Your forecast now includes them.` });
      setFile(null);
      if (input.current) input.current.value = "";
    } catch (err) {
      setResult({ ok: false, text: (err as Error).message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card flex flex-col gap-3">
      <h2 className="font-semibold">B · Upload a CSV file</h2>
      <p className="text-sm text-muted">
        For banks we don&apos;t connect to yet. Export your statement and upload it.
      </p>
      <form className="flex flex-col gap-3" onSubmit={upload}>
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDrag(true);
          }}
          onDragLeave={() => setDrag(false)}
          onDrop={onDrop}
          className={`rounded-lg border border-dashed p-5 text-center text-sm ${
            drag ? "border-teal bg-teal-light" : "border-[#b8b8b3] bg-paper"
          }`}
        >
          <div>
            {file ? (
              <b>{file.name}</b>
            ) : (
              <>
                Drop a file here or{" "}
                <button type="button" className="font-semibold text-teal underline" onClick={() => input.current?.click()}>
                  browse
                </button>
              </>
            )}
          </div>
          <div className="mt-1 text-xs text-muted">.csv · up to 1 MB · 5,000 rows</div>
          <input
            ref={input}
            type="file"
            accept=".csv,text/csv"
            className="sr-only"
            aria-label="CSV file"
            onChange={(e) => pick(e.target.files?.[0])}
          />
        </div>

        <ul className="space-y-1.5 text-sm">
          <li className="flex justify-between gap-2">
            <span>
              <b>Transactions</b> · 3 to 6 months
            </span>
            <span className="text-xs font-semibold text-warn">Required</span>
          </li>
          <li className="flex justify-between gap-2">
            <span>
              <b>Unpaid invoices</b> and <b>upcoming bills</b>
            </span>
            <a href="#manual-entry" className="text-xs font-semibold">
              Add by hand ↓
            </a>
          </li>
        </ul>

        <p className="text-xs text-muted">
          Columns: <code className="font-mono">date, amount, counterparty, category, memo</code>. Positive =
          money in, negative = money out. If any line is invalid, nothing is imported and the line is named.
        </p>

        <div className="flex flex-wrap items-center gap-3">
          <button className="btn-primary" disabled={busy}>
            {busy ? "Checking…" : "Upload and check"}
          </button>
          <a href="/templates/transactions-template.csv" download className="text-sm font-semibold">
            Download template
          </a>
        </div>
      </form>

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
    </section>
  );
}

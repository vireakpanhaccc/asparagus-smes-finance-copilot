"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type DragEvent } from "react";
import EntryPanel, { type PanelMode } from "@/components/data/EntryPanel";
import { apiDownload, apiGet, apiPost, apiUpload, type DataSources } from "@/lib/api";

// Assumed partner integration, simulated in the sandbox. No real bank is contacted.
const PROVIDERS = ["WeBank (mock)", "Cambodian bank / KHQR (mock)", "Mobile wallet (mock)"];
const STEPS = ["Link your bank", "Add what the bank misses", "Check and start"];

export default function SetupPage() {
  const router = useRouter();
  const [step, setStep] = useState(1);

  // /setup?step=bank (from "Link another bank") opens step 1; read it after mount
  useEffect(() => {
    if (new URLSearchParams(window.location.search).get("step") === "bank") setStep(1);
  }, []);

  return (
    <div className="min-h-screen bg-brand-panel">
      <header className="flex items-center justify-between px-5 py-4 lg:px-10">
        <div className="flex items-center gap-2.5">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-brand-blue" aria-hidden="true">
            <span className="h-2.5 w-2.5 rounded-full bg-brand-red" />
          </span>
          <span className="text-[15px] font-bold">SME Finance Copilot</span>
        </div>
        <Link href="/overview" className="min-h-[44px] content-center text-sm font-semibold">
          Finish later
        </Link>
      </header>

      <main className="mx-auto w-full max-w-[640px] px-4 pb-16 pt-2">
        <ol className="mb-5 grid grid-cols-3 gap-2" aria-label="Setup progress">
          {STEPS.map((label, i) => {
            const n = i + 1;
            return (
              <li
                key={label}
                aria-current={step === n ? "step" : undefined}
                className={`border-t-4 pt-2 text-xs sm:text-[13px] ${
                  n < step ? "border-brand-blue text-brand-sub" : step === n ? "border-brand-blue font-semibold text-brand-ink" : "border-brand-line text-brand-muted"
                }`}
              >
                {n} · {label}
              </li>
            );
          })}
        </ol>

        {step === 1 && <BankStep onNext={() => setStep(2)} />}
        {step === 2 && <FilesStep onNext={() => setStep(3)} />}
        {step === 3 && <DoneStep onGo={() => router.push("/overview")} />}
      </main>
    </div>
  );
}

function BankStep({ onNext }: { onNext: () => void }) {
  const [provider, setProvider] = useState(PROVIDERS[0]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function allow() {
    setBusy(true);
    setError("");
    try {
      await apiPost("/connect", { provider, days_valid: 90 });
      onNext();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card space-y-5 p-6 sm:p-8">
      <div>
        <h1 className="text-2xl font-bold">Where does your business bank?</h1>
        <p className="mt-1.5 text-sm text-brand-sub">
          Linking it means no typing. The Copilot can only read. It can never move money.
        </p>
      </div>
      <fieldset className="space-y-2">
        <legend className="sr-only">Choose your provider</legend>
        {PROVIDERS.map((p) => (
          <label
            key={p}
            className={`flex min-h-[56px] cursor-pointer items-center gap-3 rounded-xl border-2 px-4 text-[15px] font-medium ${
              provider === p ? "border-brand-blue bg-brand-blue50" : "border-brand-line hover:bg-brand-panel"
            }`}
          >
            <input type="radio" name="provider" checked={provider === p} onChange={() => setProvider(p)} className="h-4 w-4 accent-brand-blue" />
            {p}
          </label>
        ))}
      </fieldset>
      <p className="flex items-start gap-2 rounded-lg bg-brand-blue50 p-3 text-sm text-brand-blue700">
        <span aria-hidden="true">🔒</span>
        Read-only for 90 days. Revoke any time. Bank entries stay locked, so nobody can change them.
      </p>
      {error && <p role="alert" className="text-sm text-brand-red700">{error}</p>}
      <button className="btn-primary h-[52px] w-full text-base" onClick={allow} disabled={busy}>
        {busy ? "Connecting…" : "Allow read-only access"}
      </button>
      <button className="block w-full text-center text-sm font-semibold text-brand-blue hover:underline" onClick={onNext}>
        No bank app? Skip and upload a file or type entries instead
      </button>
    </section>
  );
}

function FilesStep({ onNext }: { onNext: () => void }) {
  const [panel, setPanel] = useState<PanelMode | null>(null);
  const [drag, setDrag] = useState(false);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<string[]>([]);
  const [error, setError] = useState("");
  const input = useRef<HTMLInputElement>(null);

  async function upload(file: File | undefined | null) {
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      const r = await apiUpload<{ rows: number; filename: string }>("/data/upload", file);
      setDone((d) => [...d, `${r.rows} transactions imported from ${r.filename}`]);
    } catch (e) {
      setError((e as Error).message); // names the bad line; nothing was imported
    } finally {
      setBusy(false);
      if (input.current) input.current.value = "";
    }
  }

  function onDrop(e: DragEvent) {
    e.preventDefault();
    setDrag(false);
    void upload(e.dataTransfer.files[0]);
  }

  return (
    <section className="card space-y-5 p-6 sm:p-8">
      <div>
        <h1 className="text-2xl font-bold">Add what the bank misses</h1>
        <p className="mt-1.5 text-sm text-brand-sub">
          Cash sales, a bill to pay, an invoice to collect, or a CSV statement. Add what you have now; you can add more later.
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-2 rounded-xl border border-brand-line p-4">
          <h2 className="font-semibold">Upload a file</h2>
          <div
            onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
            onDragLeave={() => setDrag(false)}
            onDrop={onDrop}
            className={`rounded-lg border border-dashed p-4 text-center text-sm ${drag ? "border-brand-blue bg-brand-blue50" : "border-brand-field bg-brand-panel"}`}
          >
            {busy ? "Checking…" : (
              <>
                Drop a CSV here or{" "}
                <button className="font-semibold text-brand-blue underline" onClick={() => input.current?.click()}>browse</button>
              </>
            )}
            <input ref={input} type="file" accept=".csv,text/csv" className="sr-only" aria-label="Choose a CSV file"
              onChange={(e) => void upload(e.target.files?.[0])} />
          </div>
          <button className="text-sm font-semibold text-brand-blue hover:underline"
            onClick={() => void apiDownload("/data/template.csv", "transactions-template.csv")}>
            Download template
          </button>
        </div>

        <div className="space-y-2 rounded-xl border border-brand-line p-4">
          <h2 className="font-semibold">Type entries</h2>
          <p className="text-sm text-brand-sub">Add a transaction, a bill or an invoice by hand.</p>
          <button className="btn-outline w-full" onClick={() => setPanel({ type: "new", kind: "transaction" })}>
            Type an entry
          </button>
        </div>
      </div>

      {error && <p role="alert" className="rounded-lg bg-brand-red50 p-3 text-sm text-brand-red800">{error}</p>}
      {done.length > 0 && (
        <ul role="status" className="space-y-1 rounded-lg bg-brand-blue50 p-3 text-sm text-brand-blue700">
          {done.map((d, i) => <li key={i}>✓ {d}</li>)}
        </ul>
      )}

      <button className="btn-primary h-[52px] w-full text-base" onClick={onNext}>
        {done.length > 0 ? "Continue" : "Skip"}
      </button>

      <EntryPanel
        mode={panel}
        onClose={() => setPanel(null)}
        onSaved={(text) => setDone((d) => [...d, text.replace(/\.$/, "")])}
      />
    </section>
  );
}

function DoneStep({ onGo }: { onGo: () => void }) {
  const [sources, setSources] = useState<DataSources | null>(null);
  useEffect(() => {
    apiGet<DataSources>("/data/sources").then(setSources).catch(() => setSources(null));
  }, []);

  const rows: [string, string][] = sources
    ? [
        ["Bank", sources.bank.linked ? `${sources.bank.provider} · ${sources.bank.transactions.toLocaleString("en-US")} transactions, locked` : "Not linked"],
        ["Uploaded files", sources.files.transactions > 0 ? `${sources.files.transactions.toLocaleString("en-US")} transactions` : "None"],
        ["Added by you", sources.manual.total > 0 ? `${sources.manual.transactions} transactions · ${sources.manual.bills} bills · ${sources.manual.invoices} invoices` : "None"],
      ]
    : [];

  return (
    <section className="card space-y-5 p-6 sm:p-8">
      <div>
        <h1 className="text-2xl font-bold">Check and start</h1>
        <p className="mt-1.5 text-sm text-brand-sub">Here is what the Copilot will read. You can change any of it in My data.</p>
      </div>
      <dl className="divide-y divide-brand-line2 rounded-xl border border-brand-line">
        {rows.map(([k, v]) => (
          <div key={k} className="flex justify-between gap-4 px-4 py-3 text-sm">
            <dt className="text-brand-muted">{k}</dt>
            <dd className="text-right font-medium">{v}</dd>
          </div>
        ))}
        {!sources && <div className="px-4 py-3 text-sm text-brand-muted">Loading…</div>}
      </dl>
      <button className="btn-primary h-[52px] w-full text-base" onClick={onGo}>Go to my overview</button>
    </section>
  );
}

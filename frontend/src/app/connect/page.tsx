"use client";

import { useEffect, useRef, useState } from "react";
import ManualEntryCard from "@/components/ManualEntryCard";
import { apiDelete, apiPost, money, streamUrl } from "@/lib/api";
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
  const source = useRef<EventSource | null>(null);

  useEffect(() => () => source.current?.close(), []);

  async function connect() {
    const g = await apiPost<Grant>("/connect", { provider, days_valid: 90 });
    setGrant(g);
    const es = new EventSource(streamUrl("/connect/live"));
    es.addEventListener("transaction", (ev) => {
      const tx = JSON.parse((ev as MessageEvent).data) as LiveTx;
      setLive((l) => [tx, ...l].slice(0, 8));
    });
    es.addEventListener("stopped", () => es.close());
    source.current = es;
  }

  async function revoke() {
    if (!grant) return;
    await apiDelete(`/connect/${grant.id}`);
    source.current?.close();
    setGrant(null);
  }

  return (
    <div className="max-w-3xl space-y-5">
      <h1 className="text-2xl font-bold">{t("connect.title")}</h1>

      {!grant ? (
        <div className="card space-y-4">
          <div className="space-y-2">
            {PROVIDERS.map((p) => (
              <label key={p} className="flex items-center gap-2 text-sm">
                <input type="radio" checked={provider === p} onChange={() => setProvider(p)} /> {p}
              </label>
            ))}
          </div>
          <div className="rounded-lg bg-paper p-3 text-sm">
            <b>SME Finance Copilot is asking for:</b>
            <ul className="mt-1 list-disc pl-5">
              <li>Read your transactions and balance (transactions:read)</li>
              <li>For 90 days, revocable any time</li>
            </ul>
            <p className="mt-2 text-black/60">{t("connect.scope")}</p>
          </div>
          <button className="btn-primary" onClick={connect}>Allow read-only access</button>
        </div>
      ) : (
        <div className="card space-y-3">
          <div className="flex items-center justify-between">
            <div>
              <div className="font-semibold">{grant.provider}</div>
              <div className="text-sm text-black/60">
                {grant.scope} · until {grant.expires_at.slice(0, 10)}
              </div>
            </div>
            <span className="badge bg-teal-light text-teal">● Live sync</span>
          </div>
          <ul className="divide-y text-sm">
            {live.map((tx) => (
              <li key={tx.id} className="flex justify-between py-2">
                <span>{tx.counterparty}</span>
                <span className="font-mono">{money(tx.amount_cents, 2)}</span>
              </li>
            ))}
            {live.length === 0 && <li className="py-2 text-black/50">Waiting for new transactions…</li>}
          </ul>
          <button className="btn-outline text-danger" onClick={revoke}>Revoke access</button>
        </div>
      )}

      <ManualEntryCard />
    </div>
  );
}

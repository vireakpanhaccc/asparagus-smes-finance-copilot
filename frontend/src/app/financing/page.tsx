"use client";

import { useEffect, useState } from "react";
import { apiGet, money, type FinancingOption, type Forecast } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

type Ranked = { gap_cents: number; monthly_margin_cents: number; options: FinancingOption[]; disclaimer: string };

const LABEL_STYLE: Record<string, string> = {
  "Best fit": "bg-teal text-white",
  "Good fit": "bg-teal-light text-teal",
  Stretch: "bg-warn-bg text-warn",
  "Try first": "bg-black/5 text-black/70",
};

export default function FinancingPage() {
  const { t } = useI18n();
  const [ranked, setRanked] = useState<Ranked | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    // Size the need from the forecast's deepest dip (plus a buffer).
    apiGet<Forecast>("/forecast")
      .then((f) => {
        const low = Math.min(0, ...f.weeks.map((w) => w.lowest_balance_cents));
        const gap = Math.max(-low, 0) + 50_000;
        return apiGet<Ranked>(`/financing?gap_cents=${gap}&months=2`);
      })
      .then(setRanked)
      .catch((e: Error) => setError(e.message));
  }, []);

  if (error) return <p className="text-danger">{error}</p>;
  if (!ranked) return <p>Loading…</p>;

  return (
    <div className="max-w-6xl space-y-5">
      <header>
        <h1 className="text-2xl font-bold">{t("financing.title")}</h1>
        <p className="text-sm text-black/60">
          Need: about {money(ranked.gap_cents)} · monthly margin {money(ranked.monthly_margin_cents)} ·{" "}
          {ranked.disclaimer}
        </p>
      </header>
      <div className="grid gap-4 md:grid-cols-2">
        {ranked.options.map((o) => (
          <article key={o.product_id} className={`card ${o.label === "Best fit" ? "border-2 border-teal" : ""}`}>
            <div className="flex items-start justify-between gap-2">
              <h2 className="font-semibold">{o.name}</h2>
              <span className={`badge ${LABEL_STYLE[o.label] ?? ""}`}>{o.label}</span>
            </div>
            <dl className="mt-3 grid grid-cols-3 gap-2 text-sm">
              <Stat label="Amount" value={o.amount_cents ? money(o.amount_cents) : "–"} />
              <Stat label="Total cost" value={money(o.total_cost_cents)} />
              <Stat label="Monthly payment" value={o.monthly_payment_cents ? money(o.monthly_payment_cents) : "–"} />
            </dl>
            {o.why_it_fits.length > 0 && (
              <p className="mt-3 text-sm"><b>{t("financing.why")}</b> {o.why_it_fits.join(" ")}</p>
            )}
            {o.watch_out.length > 0 && (
              <p className="mt-1 text-sm text-black/70"><b>{t("financing.watch")}</b> {o.watch_out.join(" ")}</p>
            )}
            <div className="mt-3 text-xs text-black/50">
              Payment vs monthly margin: {o.payment_to_margin_pct}% · Submitting needs your approval
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-black/50">{label}</dt>
      <dd className="font-mono">{value}</dd>
    </div>
  );
}

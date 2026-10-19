"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import ForecastChart from "@/components/ForecastChart";
import { apiGet, money, type Analysis, type Forecast } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

export default function OverviewPage() {
  const { t } = useI18n();
  const [forecast, setForecast] = useState<Forecast | null>(null);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([apiGet<Forecast>("/forecast"), apiGet<Analysis>("/analysis")])
      .then(([f, a]) => {
        setForecast(f);
        setAnalysis(a);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  if (error) return <p className="text-danger">Could not reach the API: {error}</p>;
  if (!forecast || !analysis) return <p>Loading…</p>;

  const shortfall = forecast.weeks.find((w) => w.shortfall);
  const last30 = analysis.last_30_days;

  return (
    <div className="max-w-6xl space-y-5">
      <header>
        <h1 className="text-2xl font-bold">{t("overview.title")}</h1>
        <p className="text-sm text-black/60">Sample Café · synced from WeBank (mock connection)</p>
      </header>

      {shortfall && (
        <div className="flex items-center justify-between rounded-xl border border-warn-border bg-warn-bg p-4 text-warn">
          <div>
            <div className="font-bold">
              {t("overview.shortfall")} {shortfall.week_start}
            </div>
            <div className="text-sm">
              Balance is forecast to dip to {money(shortfall.lowest_balance_cents)}.
            </div>
          </div>
          <div className="flex shrink-0 gap-2">
            <Link href="/copilot?ask=rescue" className="btn bg-warn text-white">
              Build a rescue plan
            </Link>
            <Link href="/financing" className="btn border border-warn-border bg-white text-warn">
              See financing options
            </Link>
          </div>
        </div>
      )}

      <section className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Kpi label={t("overview.cash")} value={money(forecast.current_balance_cents)} />
        <Kpi label={t("overview.in")} value={money(last30.money_in_cents)} />
        <Kpi label={t("overview.out")} value={money(last30.money_out_cents)} />
        <Kpi label={t("overview.margin")} value={`${last30.margin_pct ?? "–"}%`} />
      </section>

      <section className="grid gap-4 lg:grid-cols-3">
        <div className="card lg:col-span-2">
          <h2 className="mb-2 font-semibold">{t("overview.forecast")}</h2>
          <ForecastChart weeks={forecast.weeks} />
          <p className="mt-2 text-xs text-black/50">{forecast.note}</p>
        </div>
        <div className="card">
          {/* Business analysis: Topic E's third requirement */}
          <h2 className="mb-3 font-semibold">Spending by category · 30 days</h2>
          <ul className="space-y-1 text-sm">
            {Object.entries(analysis.spend_by_category_cents).map(([cat, cents]) => (
              <li key={cat} className="flex justify-between">
                <span>{cat}</span>
                <span className="font-mono">{money(cents)}</span>
              </li>
            ))}
          </ul>
          {analysis.supplier_cost_change_8w_pct !== null && (
            <p className="mt-3 text-sm">
              Supplier costs {analysis.supplier_cost_change_8w_pct > 0 ? "up" : "down"}{" "}
              {Math.abs(analysis.supplier_cost_change_8w_pct)}% over 8 weeks.
            </p>
          )}
        </div>
      </section>

      <p className="text-xs text-black/50">{t("overview.footer")}</p>
    </div>
  );
}

function Kpi({ label, value }: { label: string; value: string }) {
  return (
    <div className="card">
      <div className="text-sm text-black/60">{label}</div>
      <div className="mt-1 font-mono text-2xl font-semibold">{value}</div>
    </div>
  );
}

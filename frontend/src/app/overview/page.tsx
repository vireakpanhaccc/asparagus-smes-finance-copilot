"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import ForecastChart from "@/components/ForecastChart";
import { apiGet, money, type Analysis, type DataSources, type Forecast } from "@/lib/api";
import { RESCUE_PROMPT, useCopilot } from "@/lib/copilot";
import { useI18n } from "@/lib/i18n";

export default function OverviewPage() {
  const { t } = useI18n();
  const router = useRouter();
  const { send, setOpen } = useCopilot();
  const [forecast, setForecast] = useState<Forecast | null>(null);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [error, setError] = useState("");
  const askedFromUrl = useRef(false);

  // First run: nothing linked, uploaded or typed yet -> guided setup instead of an empty dashboard.
  useEffect(() => {
    apiGet<DataSources>("/data/sources")
      .then((s) => !s.has_data && router.replace("/setup"))
      .catch(() => undefined); // the forecast request below reports API problems
  }, [router]);

  useEffect(() => {
    Promise.all([apiGet<Forecast>("/forecast"), apiGet<Analysis>("/analysis")])
      .then(([f, a]) => {
        setForecast(f);
        setAnalysis(a);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  // Other pages link here with ?ask=<question> (or ?ask=rescue) to start a chat turn.
  useEffect(() => {
    if (askedFromUrl.current) return; // React strict mode runs effects twice in dev
    askedFromUrl.current = true;
    const ask = new URLSearchParams(window.location.search).get("ask");
    if (!ask) return;
    window.history.replaceState(null, "", "/overview");
    void send(ask === "rescue" ? RESCUE_PROMPT : ask);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (error) return <p className="p-8 text-brand-red700">Could not reach the API: {error}</p>;
  if (!forecast || !analysis) return <p className="p-8">Loading…</p>;

  const shortfall = forecast.weeks.find((w) => w.shortfall);
  const last30 = analysis.last_30_days;
  const costChange = analysis.supplier_cost_change_8w_pct;

  return (
    <div className="flex">
      <div className="flex min-w-0 flex-1 flex-col gap-5 p-4 pb-24 lg:p-8 lg:pb-24">
        <header>
          <h1 className="text-xl font-bold lg:text-[26px]">{t("overview.title")}</h1>
          <p className="mt-1 text-sm text-brand-muted">Sample Café · bank link, uploaded files and your own entries</p>
        </header>

        {shortfall && (
          <section className="flex flex-col gap-3 rounded-xl border border-brand-amber/30 bg-brand-amber50 p-4 text-brand-amber sm:flex-row sm:items-center sm:justify-between">
            <div>
              <div className="text-[15px] font-bold lg:text-base">
                {t("overview.shortfall")} {shortfall.week_start}
              </div>
              <div className="text-sm">Balance may dip to {money(shortfall.lowest_balance_cents)}.</div>
            </div>
            <div className="flex shrink-0 gap-2">
              <button
                className="btn flex-1 bg-brand-amber text-white hover:bg-brand-amber/90 sm:flex-none"
                onClick={() => {
                  setOpen(true);
                  void send(RESCUE_PROMPT);
                }}
              >
                Build a rescue plan
              </button>
              <Link
                href="/financing"
                className="btn flex-1 border border-brand-amber/30 bg-white text-brand-amber hover:bg-white/80 hover:text-brand-amber sm:flex-none"
              >
                <span className="sm:hidden">Financing</span>
                <span className="hidden sm:inline">See financing options</span>
              </Link>
            </div>
          </section>
        )}

        <section className="grid grid-cols-2 gap-2.5 lg:grid-cols-4 lg:gap-3">
          <Kpi label={t("overview.cash")} value={money(forecast.current_balance_cents)} />
          <Kpi label={t("overview.in")} value={money(last30.money_in_cents)} />
          <Kpi label={t("overview.out")} value={money(last30.money_out_cents)} />
          <Kpi label={t("overview.margin")} value={`${last30.margin_pct ?? "–"}%`} />
        </section>

        <section className="card flex flex-col gap-2.5">
          <h2 className="text-[15px] font-semibold">{t("overview.forecast")}</h2>
          <div className="rounded-lg bg-brand-panel p-2">
            <ForecastChart weeks={forecast.weeks} />
          </div>
          <p className="text-xs text-brand-muted">{forecast.note}</p>
        </section>

        {/* Business analysis: Topic E's third requirement */}
        <section className="card flex flex-col gap-2.5">
          <h2 className="text-[15px] font-semibold">Spending by category · 30 days</h2>
          <ul className="grid gap-x-8 gap-y-1.5 text-sm md:grid-cols-2">
            {Object.entries(analysis.spend_by_category_cents).map(([cat, cents]) => (
              <li key={cat} className="flex justify-between border-b border-brand-line2 py-1">
                <span>{cat}</span>
                <span className="font-mono">{money(cents)}</span>
              </li>
            ))}
          </ul>
          {costChange !== null && (
            <p className="text-sm">
              Supplier costs {costChange > 0 ? "up" : "down"} {Math.abs(costChange)}% over 8 weeks.{" "}
              <button
                className="font-semibold text-brand-blue underline-offset-2 hover:underline"
                onClick={() => void send("Why are my supplier costs up?")}
              >
                Ask why
              </button>
            </p>
          )}
        </section>

        <p className="text-xs text-brand-muted">{t("overview.footer")}</p>
      </div>

    </div>
  );
}

function Kpi({ label, value }: { label: string; value: string }) {
  return (
    <div className="card p-3 lg:p-4">
      <div className="text-xs text-brand-muted lg:text-[13px]">{label}</div>
      <div className="mt-1 font-mono text-xl font-semibold lg:mt-1.5 lg:text-2xl">{value}</div>
    </div>
  );
}

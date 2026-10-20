"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type ReactNode } from "react";
import ForecastChart, { ForecastLegend } from "@/components/ForecastChart";
import { apiGet, money, type Analysis, type DataSources, type Forecast } from "@/lib/api";
import { RESCUE_PROMPT, useCopilot } from "@/lib/copilot";
import { useI18n } from "@/lib/i18n";

export default function OverviewPage() {
  const { t } = useI18n();
  const router = useRouter();
  const { send, setOpen, busy } = useCopilot();
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
  const prev30 = analysis.previous_30_days;
  const costChange = analysis.supplier_cost_change_8w_pct;
  const cash = forecast.current_balance_cents;
  const spend = Object.entries(analysis.spend_by_category_cents);
  const maxSpend = Math.max(1, ...spend.map(([, cents]) => cents));

  return (
    <div className="flex">
      <div className="flex min-w-0 flex-1 flex-col gap-5 p-4 pb-24 lg:p-8 lg:pb-24">
        <header>
          <h1 className="text-xl font-bold lg:text-[26px]">{t("overview.title")}</h1>
          <p className="mt-1 text-sm text-brand-muted">Sample Café · bank link, uploaded files and your own entries</p>
        </header>

        {shortfall && (
          <section role="alert" className="flex flex-col gap-3 rounded-xl border-[1.5px] border-brand-red200 bg-brand-red50 p-4 text-brand-red800 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <div className="text-[15px] font-bold lg:text-base">
                {t("overview.shortfall")} {shortfall.week_start}
              </div>
              <div className="text-sm">Balance may dip to {money(shortfall.lowest_balance_cents)}.</div>
            </div>
            <div className="flex shrink-0 gap-2">
              <button
                className="btn flex-1 bg-brand-red700 text-white hover:bg-brand-red800 disabled:opacity-60 sm:flex-none"
                disabled={busy}
                onClick={() => {
                  setOpen(true);
                  void send(RESCUE_PROMPT);
                }}
              >
                Build a rescue plan
              </button>
              <Link
                href="/financing"
                className="btn flex-1 border border-brand-red200 bg-white text-brand-red800 hover:bg-white/80 hover:text-brand-red800 sm:flex-none"
              >
                <span className="sm:hidden">Financing</span>
                <span className="hidden sm:inline">See financing options</span>
              </Link>
            </div>
          </section>
        )}

        <section className="grid grid-cols-2 gap-2.5 lg:grid-cols-4 lg:gap-3">
          {/* cash 30 days ago = cash now minus the last 30 days' net */}
          <Kpi label={t("overview.cash")} value={money(cash)} icon={ICONS.cash}
            trend={trend(pctChange(cash, cash - last30.net_cents), "%", true)} />
          <Kpi label={t("overview.in")} value={money(last30.money_in_cents)} icon={ICONS.in}
            trend={trend(pctChange(last30.money_in_cents, prev30.money_in_cents), "%", true)} />
          <Kpi label={t("overview.out")} value={money(last30.money_out_cents)} icon={ICONS.out}
            trend={trend(pctChange(last30.money_out_cents, prev30.money_out_cents), "%", false)} />
          <Kpi label={t("overview.margin")} value={`${last30.margin_pct ?? "–"}%`} icon={ICONS.margin}
            trend={trend(
              last30.margin_pct !== null && prev30.margin_pct !== null ? last30.margin_pct - prev30.margin_pct : null,
              " pts", true,
            )} />
        </section>

        <section className="card flex flex-col gap-2.5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-[15px] font-semibold">{t("overview.forecast")}</h2>
            <ForecastLegend />
          </div>
          <div className="rounded-lg bg-brand-panel p-2">
            <ForecastChart weeks={forecast.weeks} />
          </div>
          <p className="text-xs text-brand-muted">{forecast.note}</p>
        </section>

        {/* Business analysis: Topic E's third requirement */}
        <section className="card flex flex-col gap-2.5">
          <h2 className="text-[15px] font-semibold">Spending by category · 30 days</h2>
          <ul className="grid gap-x-10 gap-y-3 text-sm md:grid-cols-2">
            {spend.map(([cat, cents]) => (
              <li key={cat} className="grid grid-cols-[6.5rem_1fr_auto] items-center gap-3">
                <span className="truncate">{cat}</span>
                {/* bar length relative to the largest category */}
                <span className="h-2 rounded-full bg-brand-line2" aria-hidden="true">
                  <span
                    className="block h-full rounded-full bg-brand-blue"
                    style={{ width: `max(4px, ${(100 * cents) / maxSpend}%)` }}
                  />
                </span>
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

type Trend = { up: boolean; text: string; tone: "good" | "bad" | "flat" } | null;

function pctChange(now: number, before: number): number | null {
  return before ? (100 * (now - before)) / Math.abs(before) : null;
}

// Colour by meaning, not direction: more money out is bad, more money in is good.
function trend(change: number | null, unit: "%" | " pts", upIsGood: boolean): Trend {
  if (change === null || !Number.isFinite(change)) return null;
  if (Math.abs(change) < 0.5) return { up: false, text: "No change", tone: "flat" };
  const up = change > 0;
  return { up, text: `${Math.abs(change).toFixed(1)}${unit}`, tone: up === upIsGood ? "good" : "bad" };
}

const TONE = { good: "text-brand-green700", bad: "text-brand-red700", flat: "text-brand-ink" };

const icon = (path: ReactNode) => (
  <svg aria-hidden="true" width="30" height="30" viewBox="0 0 20 20" fill="none" stroke="currentColor"
    strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    {path}
  </svg>
);

const ICONS = {
  cash: icon(<><path d="M4 6.5V6a2 2 0 0 1 2-2h8v2.5" /><rect x="3" y="6.5" width="14" height="9.5" rx="2" /><circle cx="13.5" cy="11.25" r="1" /></>),
  in: icon(<><path d="M10 3v8M6.5 7.5 10 11l3.5-3.5" /><path d="M3 13v1.5A2.5 2.5 0 0 0 5.5 17h9a2.5 2.5 0 0 0 2.5-2.5V13" /></>),
  out: icon(<><path d="M10 11V3M6.5 6.5 10 3l3.5 3.5" /><path d="M3 13v1.5A2.5 2.5 0 0 0 5.5 17h9a2.5 2.5 0 0 0 2.5-2.5V13" /></>),
  margin: icon(<><path d="M15 5 5 15" /><circle cx="6" cy="6" r="2" /><circle cx="14" cy="14" r="2" /></>),
};

function Kpi({ label, value, icon, trend }: { label: string; value: string; icon: ReactNode; trend: Trend }) {
  return (
    <div className="card flex items-stretch gap-3 p-3 lg:p-4">
      <div className="min-w-0 flex-1">
        <div className="text-xs text-brand-muted lg:text-[13px]">{label}</div>
        <div className="mt-1 font-mono text-xl font-semibold lg:text-2xl">{value}</div>
        {trend && (
          <div className="mt-1 text-xs">
            <span className={`text-sm font-semibold ${TONE[trend.tone]}`}>
              {trend.tone !== "flat" && <span aria-hidden="true">{trend.up ? "▲ " : "▼ "}</span>}
              <span className="sr-only">{trend.tone === "flat" ? "" : trend.up ? "Up " : "Down "}</span>
              {trend.text}
            </span>{" "}
            <span className="text-brand-muted">vs previous 30 days</span>
          </div>
        )}
      </div>
      {/* full-height icon tile: from the label down to the change line */}
      <span className="grid w-12 shrink-0 place-items-center self-stretch rounded-xl bg-brand-panel text-brand-sub lg:w-16">
        {icon}
      </span>
    </div>
  );
}

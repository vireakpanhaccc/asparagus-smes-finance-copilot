"use client";

import { useEffect, useState } from "react";
import { apiGet, money, type FinancingOption, type Forecast } from "@/lib/api";
import { useCopilot } from "@/lib/copilot";
import { useI18n } from "@/lib/i18n";

type Ranked = { gap_cents: number; monthly_margin_cents: number; options: FinancingOption[]; disclaimer: string };

const BUFFER_CENTS = 50_000;
const MONTHS = 2;

const LABEL_STYLE: Record<string, string> = {
  "Best fit": "bg-teal text-white",
  "Good fit": "bg-teal-light text-teal",
  Stretch: "bg-warn-bg text-warn",
};
const BAR_STYLE: Record<string, string> = {
  "Best fit": "bg-teal",
  "Good fit": "bg-teal",
  Stretch: "bg-warn-accent",
};

export default function FinancingPage() {
  const { t } = useI18n();
  const { send } = useCopilot();
  const [ranked, setRanked] = useState<Ranked | null>(null);
  const [dipCents, setDipCents] = useState(0);
  const [error, setError] = useState("");

  useEffect(() => {
    // Size the need from the forecast's deepest dip (plus a buffer).
    apiGet<Forecast>("/forecast")
      .then((f) => {
        const low = Math.min(0, ...f.weeks.map((w) => w.lowest_balance_cents));
        const dip = Math.max(-low, 0);
        setDipCents(dip);
        return apiGet<Ranked>(`/financing?gap_cents=${dip + BUFFER_CENTS}&months=${MONTHS}`);
      })
      .then(setRanked)
      .catch((e: Error) => setError(e.message));
  }, []);

  if (error) return <p className="p-8 text-danger">{error}</p>;
  if (!ranked) return <p className="p-8">Loading…</p>;

  const tryFirst = ranked.options.filter((o) => o.kind === "supplier_terms");
  const loans = ranked.options.filter((o) => o.kind !== "supplier_terms");

  return (
    <div className="space-y-5 p-4 pb-24 lg:p-8 lg:pb-24">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold lg:text-[26px]">{t("financing.title")}</h1>
          <p className="mt-1 text-sm text-muted">Ranked for your gap. {ranked.disclaimer}</p>
        </div>
        <button className="btn-outline" onClick={() => void send("Explain my financing options and which one fits best.")}>
          Ask the Copilot about these
        </button>
      </header>

      {/* Need summary */}
      <section className="grid gap-3 sm:grid-cols-3">
        <Summary label="You need about" value={money(ranked.gap_cents)} sub={`${money(dipCents)} gap + ${money(BUFFER_CENTS)} buffer`} />
        <Summary label="For about" value={`${MONTHS} months`} sub="until sales recover" />
        <Summary label="Monthly margin" value={money(ranked.monthly_margin_cents)} sub="payments above 25% = Stretch" />
      </section>

      {/* Try first */}
      {tryFirst.map((o) => (
        <section
          key={o.product_id}
          className="flex flex-col gap-3 rounded-xl border border-line bg-paper p-4 sm:flex-row sm:items-center"
        >
          <span className="badge self-start bg-ink-soft text-white">Try first</span>
          <div className="flex-1">
            <div className="font-semibold">{o.name}</div>
            <div className="text-sm text-muted">
              {[...o.why_it_fits, ...o.watch_out].join(" ") || "Costs nothing, nothing to apply for."}
            </div>
          </div>
          <button
            className="btn-outline"
            onClick={() => void send("Draft a message asking my supplier for 30-day payment terms.")}
          >
            Draft the message
          </button>
        </section>
      ))}

      {/* Loan options */}
      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
        {loans.map((o) => (
          <article
            key={o.product_id}
            className={`card flex flex-col gap-3 ${o.label === "Best fit" ? "!border-2 !border-teal" : ""}`}
          >
            <div className="flex items-start justify-between gap-2">
              <h2 className="font-semibold">{o.name}</h2>
              <span className={`badge shrink-0 ${LABEL_STYLE[o.label] ?? "bg-paper text-muted"}`}>{o.label}</span>
            </div>
            <dl className="grid grid-cols-3 gap-2 text-sm">
              <Stat label="Amount" value={o.amount_cents ? money(o.amount_cents) : "–"} />
              <Stat label="Total cost" value={money(o.total_cost_cents)} />
              <Stat label="Per month" value={o.monthly_payment_cents ? money(o.monthly_payment_cents) : "–"} />
            </dl>
            {o.why_it_fits.length > 0 && (
              <p className="text-sm"><b>{t("financing.why")}</b> {o.why_it_fits.join(" ")}</p>
            )}
            {o.watch_out.length > 0 && (
              <p className="text-sm text-ink-soft"><b>{t("financing.watch")}</b> {o.watch_out.join(" ")}</p>
            )}
            <div className="mt-auto space-y-1">
              <div
                className="h-2 overflow-hidden rounded-full bg-side"
                role="img"
                aria-label={`Payment is ${o.payment_to_margin_pct}% of monthly margin`}
              >
                <div
                  className={`h-full rounded-full ${BAR_STYLE[o.label] ?? "bg-muted"}`}
                  style={{ width: `${Math.min(100, Math.max(0, o.payment_to_margin_pct))}%` }}
                />
              </div>
              <div className="text-xs text-muted">{o.payment_to_margin_pct}% of monthly margin</div>
            </div>
            <button
              className="btn-primary"
              onClick={() => void send(`Prepare a draft loan application for ${o.name} for ${money(o.amount_cents)}.`)}
            >
              Prepare application
            </button>
          </article>
        ))}
      </section>

      <p className="text-xs text-muted">
        &ldquo;Prepare application&rdquo; only drafts it. Submitting needs your OK in the chat, and only the
        lender decides approval.
      </p>
    </div>
  );
}

function Summary({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div className="card">
      <div className="text-[13px] text-muted">{label}</div>
      <div className="mt-1 font-mono text-2xl font-semibold">{value}</div>
      <div className="text-xs text-muted">{sub}</div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-muted">{label}</dt>
      <dd className="font-mono font-semibold">{value}</dd>
    </div>
  );
}

"use client";

import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { money, type RescuePlan } from "@/lib/api";

// Draws the plan from build_rescue_plan. Every number is computed by the backend
// (the forecast re-run with the plan applied); this card only displays it.
export default function RescuePlanCard({ plan }: { plan: RescuePlan }) {
  if (!plan.needed || !plan.after) {
    return (
      <div className="card text-sm">
        No rescue plan needed: the forecast stays above the safety buffer.
      </div>
    );
  }
  const data = plan.weeks.map((w) => ({
    week: w.week_start.slice(5),
    before: w.before_cents / 100,
    after: w.after_cents / 100,
  }));
  const closes = plan.after.closes_gap;

  return (
    <div className="rounded-xl border border-brand-line bg-white p-3">
      <span className="badge bg-brand-ink text-white">Cash rescue plan</span>

      <div className="mt-3 grid grid-cols-2 gap-3">
        <Stat
          label="Lowest balance now"
          value={money(plan.before.lowest_balance_cents)}
          sub={`week of ${plan.before.lowest_week}`}
          tone="text-brand-red700"
        />
        <Stat
          label="With this plan"
          value={money(plan.after.lowest_balance_cents)}
          sub={closes ? `stays above the ${money(plan.safety_buffer_cents)} buffer` : "still below the buffer"}
          tone={closes ? "text-brand-blue" : "text-brand-amber"}
        />
      </div>

      <div className="mt-3">
        <ResponsiveContainer width="100%" height={180}>
          <LineChart data={data} margin={{ top: 5, right: 12, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="#DCE2EC" vertical={false} />
            <XAxis dataKey="week" tick={{ fontSize: 11 }} />
            <YAxis tickFormatter={(v: number) => `$${(v / 1000).toFixed(1)}k`} tick={{ fontSize: 11 }} />
            <Tooltip formatter={(v) => money(Number(v) * 100)} labelFormatter={(l) => `Week of ${l}`} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <ReferenceLine y={plan.safety_buffer_cents / 100} stroke="#F6C3BF" strokeDasharray="4 4" />
            <Line name="Now" dataKey="before" stroke="#C41E16" strokeDasharray="5 4" dot={false} />
            <Line name="With plan" dataKey="after" stroke="#1D4F9F" strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <ol className="mt-3 space-y-2 text-sm">
        {plan.steps.map((s) => (
          <li key={s.step} className="rounded-lg bg-brand-panel p-3">
            <div className="font-semibold">
              {s.step}. {s.title}
            </div>
            <div>
              {s.how} Cost: {money(s.cost_cents, 2)}. Lowest balance after this step:{" "}
              <span className="font-mono">{money(s.lowest_after_cents)}</span>.
            </div>
            <div className="text-xs text-brand-muted">Assumes: {s.assumption}</div>
          </li>
        ))}
      </ol>

      {plan.backup && (
        <p className="mt-2 text-sm">
          <b>Backup.</b> {plan.backup.when}: {plan.backup.title}. {plan.backup.how}
        </p>
      )}
      <p className="mt-2 text-xs text-brand-muted">{plan.note}</p>
    </div>
  );
}

function Stat({ label, value, sub, tone }: { label: string; value: string; sub: string; tone: string }) {
  return (
    <div className="rounded-lg bg-brand-panel p-3">
      <div className="text-xs text-brand-muted">{label}</div>
      <div className={`font-mono text-xl font-semibold ${tone}`}>{value}</div>
      <div className="text-xs text-brand-muted">{sub}</div>
    </div>
  );
}

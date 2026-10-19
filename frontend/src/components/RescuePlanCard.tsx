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
    <div className="rounded-xl border border-line bg-white p-3">
      <span className="badge bg-ink-soft text-white">Cash rescue plan</span>

      <div className="mt-3 grid grid-cols-2 gap-3">
        <Stat
          label="Lowest balance now"
          value={money(plan.before.lowest_balance_cents)}
          sub={`week of ${plan.before.lowest_week}`}
          tone="text-danger"
        />
        <Stat
          label="With this plan"
          value={money(plan.after.lowest_balance_cents)}
          sub={closes ? `stays above the ${money(plan.safety_buffer_cents)} buffer` : "still below the buffer"}
          tone={closes ? "text-teal" : "text-warn"}
        />
      </div>

      <div className="mt-3">
        <ResponsiveContainer width="100%" height={180}>
          <LineChart data={data} margin={{ top: 5, right: 12, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="#d6d6d2" vertical={false} />
            <XAxis dataKey="week" tick={{ fontSize: 11 }} />
            <YAxis tickFormatter={(v: number) => `$${(v / 1000).toFixed(1)}k`} tick={{ fontSize: 11 }} />
            <Tooltip formatter={(v) => money(Number(v) * 100)} labelFormatter={(l) => `Week of ${l}`} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <ReferenceLine y={plan.safety_buffer_cents / 100} stroke="#e3cf97" strokeDasharray="4 4" />
            <Line name="Now" dataKey="before" stroke="#a12a1d" strokeDasharray="5 4" dot={false} />
            <Line name="With plan" dataKey="after" stroke="#0f6b5a" strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <ol className="mt-3 space-y-2 text-sm">
        {plan.steps.map((s) => (
          <li key={s.step} className="rounded-lg bg-paper p-3">
            <div className="font-semibold">
              {s.step}. {s.title}
            </div>
            <div>
              {s.how} Cost: {money(s.cost_cents, 2)}. Lowest balance after this step:{" "}
              <span className="font-mono">{money(s.lowest_after_cents)}</span>.
            </div>
            <div className="text-xs text-black/50">Assumes: {s.assumption}</div>
          </li>
        ))}
      </ol>

      {plan.backup && (
        <p className="mt-2 text-sm">
          <b>Backup.</b> {plan.backup.when}: {plan.backup.title}. {plan.backup.how}
        </p>
      )}
      <p className="mt-2 text-xs text-black/50">{plan.note}</p>
    </div>
  );
}

function Stat({ label, value, sub, tone }: { label: string; value: string; sub: string; tone: string }) {
  return (
    <div className="rounded-lg bg-paper p-3">
      <div className="text-xs text-black/60">{label}</div>
      <div className={`font-mono text-xl font-semibold ${tone}`}>{value}</div>
      <div className="text-xs text-black/50">{sub}</div>
    </div>
  );
}

"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { money, type ForecastWeek } from "@/lib/api";

export default function ForecastChart({ weeks }: { weeks: ForecastWeek[] }) {
  const data = weeks.map((w) => ({
    week: w.week_start.slice(5),
    balance: w.lowest_balance_cents / 100,
    shortfall: w.shortfall,
  }));
  const firstShortfall = data.find((d) => d.shortfall);

  return (
    <ResponsiveContainer width="100%" height={260}>
      <LineChart data={data} margin={{ top: 10, right: 16, bottom: 0, left: 0 }}>
        <CartesianGrid stroke="#e5e7eb" vertical={false} />
        <XAxis dataKey="week" tick={{ fontSize: 12 }} />
        <YAxis tickFormatter={(v: number) => `$${(v / 1000).toFixed(1)}k`} tick={{ fontSize: 12 }} />
        <Tooltip
          formatter={(v) => money(Number(v) * 100)}
          labelFormatter={(l) => `Week of ${l}`}
        />
        <ReferenceLine y={0} stroke="#9ca3af" strokeDasharray="4 4" />
        {firstShortfall && (
          <ReferenceArea
            x1={firstShortfall.week}
            x2={firstShortfall.week}
            fill="#fdf3d8"
            stroke="#ecd48f"
          />
        )}
        <Line type="monotone" dataKey="balance" stroke="#0f6b5a" strokeWidth={2} dot={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}

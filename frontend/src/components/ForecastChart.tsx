"use client";

import { useState } from "react";
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { money, type ForecastWeek } from "@/lib/api";

// brand tokens (tailwind.config.ts): blue = balance, red = shortfall
const BLUE = "#1D4F9F";
const BLUE50 = "#EAF0FA";
const RED = "#E1251B";
const RED700 = "#C41E16";
const RED50 = "#FDECEA";

function shortDate(iso: string): string {
  return new Date(`${iso}T00:00:00Z`).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  });
}

function axisMoney(v: number): string {
  if (v === 0) return "$0";
  const a = Math.abs(v);
  const s = a >= 1000 ? `${(a / 1000).toFixed(a % 1000 ? 1 : 0)}k` : `${a}`;
  return `${v < 0 ? "−" : ""}$${s}`;
}

// "−$627 · Dec 9" under the highlighted point. Drawn in the chart's SVG, so it never
// covers the line or gets cut off by a tooltip box.
function Pill({ viewBox, text, fill }: {
  viewBox?: { x?: number; y?: number; width?: number; height?: number };
  text: string;
  fill: string;
}) {
  if (!viewBox) return null;
  const cx = (viewBox.x ?? 0) + (viewBox.width ?? 0) / 2;
  const top = (viewBox.y ?? 0) + (viewBox.height ?? 0) + 8;
  const w = text.length * 7 + 18;
  const h = 22;
  return (
    <g pointerEvents="none">
      <rect x={cx - w / 2} y={top} width={w} height={h} rx={5} fill={fill} />
      <text x={cx} y={top + h / 2} dy="0.35em" textAnchor="middle" fill="#fff" fontSize={12} fontWeight={700}>
        {text}
      </text>
    </g>
  );
}

export function ForecastLegend() {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-brand-sub">
      <span className="flex items-center gap-1.5">
        <span className="h-[3px] w-4 rounded bg-brand-blue" aria-hidden="true" />
        Lowest balance each week
      </span>
      <span className="flex items-center gap-1.5">
        <span className="h-3 w-3 rounded-sm border border-brand-red200 bg-brand-red50" aria-hidden="true" />
        Shortfall week
      </span>
    </div>
  );
}

// One point per week: that week's lowest balance. Hovering a week shades its column and
// labels it; shortfall weeks (below $0) in red. With no hover, the worst week is shown.
export default function ForecastChart({ weeks }: { weeks: ForecastWeek[] }) {
  const [hover, setHover] = useState<number | null>(null);

  const values = weeks.map((w) => w.lowest_balance_cents / 100);
  const lo = Math.min(0, ...values);
  const hi = Math.max(0, ...values);
  const range = hi - lo || 1000;
  // room below the lowest point for its label
  const domain: [number, number] = [
    Math.floor((lo - range * 0.3) / 500) * 500,
    Math.ceil((hi + range * 0.08) / 500) * 500,
  ];

  const worst = weeks.reduce<number | null>(
    (best, w, i) =>
      w.shortfall && (best === null || w.lowest_balance_cents < weeks[best].lowest_balance_cents) ? i : best,
    null,
  );
  const focus = hover ?? worst;

  const data = weeks.map((w, i) => ({
    label: shortDate(w.week_start),
    balance: w.lowest_balance_cents / 100,
    band: i === focus ? domain : null, // the shaded column behind the focused week
  }));
  const focused = focus === null ? null : weeks[focus];
  const tone = focused?.shortfall ? { dot: RED, pill: RED700, band: RED50 } : { dot: BLUE, pill: BLUE, band: BLUE50 };

  return (
    <div
      role="img"
      aria-label={
        worst === null
          ? "12-week cash forecast with no shortfall weeks."
          : `12-week cash forecast. Lowest balance ${money(weeks[worst].lowest_balance_cents)} in the week of ${shortDate(weeks[worst].week_start)}.`
      }
    >
      <ResponsiveContainer width="100%" height={240}>
        <ComposedChart
          data={data}
          margin={{ top: 10, right: 16, bottom: 0, left: 0 }}
          barCategoryGap="12%"
          onMouseMove={(s) => {
            if (typeof s?.activeTooltipIndex === "number") setHover(s.activeTooltipIndex);
          }}
          onMouseLeave={() => setHover(null)}
        >
          <CartesianGrid stroke="#E6EAF1" vertical={false} />
          <XAxis dataKey="label" tick={{ fontSize: 12 }} tickLine={false} axisLine={{ stroke: "#DCE2EC" }} />
          <YAxis domain={domain} tickFormatter={axisMoney} tick={{ fontSize: 12 }} tickLine={false} axisLine={false} width={52} />
          {/* hover tracking only; the label below the point replaces the tooltip box */}
          <Tooltip content={() => null} cursor={false} />
          <Bar dataKey="band" fill={tone.band} isAnimationActive={false} />
          <ReferenceLine y={0} stroke="#5B6478" strokeDasharray="4 4" />
          <Line type="linear" dataKey="balance" stroke={BLUE} strokeWidth={2.5} dot={false} activeDot={false} />
          {focused && (
            <ReferenceDot
              x={data[focus!].label}
              y={data[focus!].balance}
              r={6}
              fill={tone.dot}
              stroke="#fff"
              strokeWidth={2}
              label={
                <Pill
                  text={`${money(focused.lowest_balance_cents)} · ${shortDate(focused.week_start)}`}
                  fill={tone.pill}
                />
              }
            />
          )}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

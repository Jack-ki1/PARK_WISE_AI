"use client";

import { useId, type ReactNode } from "react";
import { Activity } from "lucide-react";
import { fmtTime, type Point } from "@/lib/data";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const SERIES = ["var(--pw-series-1)", "var(--pw-series-2)", "var(--pw-series-3)",
  "var(--pw-series-4)", "var(--pw-series-5)", "var(--pw-series-6)"];

/** Gradient fill helper: inherits the container's `color` via currentColor. */
function FadeGradient({ id, top = 0.4 }: { id: string; top?: number }) {
  return (
    <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stopColor="currentColor" stopOpacity={top} />
      <stop offset="100%" stopColor="currentColor" stopOpacity={0} />
    </linearGradient>
  );
}

type TipProps = {
  active?: boolean;
  payload?: Array<{ value?: number | string }>;
  label?: string | number;
  unit?: string;
};

/** Shared tooltip chrome (styled by .chart-tip in globals.css). */
function ChartTip({ active, payload, label, unit = "" }: TipProps) {
  if (!active || !payload?.length) return null;
  return (
    <div className="chart-tip">
      <span className="tip-label">{label}</span>
      <span className="tip-value">{payload[0]?.value}{unit}</span>
    </div>
  );
}

/** Compact area sparkline (monotoneX + gradient) for KPI cards. */
export function Sparkline({ values, tone = "violet" }: { values: number[]; tone?: string }) {
  const gid = `spark-${useId().replace(/:/g, "")}`;
  if (values.length < 2) return <div className="spark-empty">Waiting for samples</div>;
  const data = values.map((v, i) => ({ i, v }));
  return (
    <div className={`sparkline ${tone}`} role="img" aria-label="Observed values across sampled video frames">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 3, right: 0, left: 0, bottom: 0 }}>
          <defs><FadeGradient id={gid} top={0.5} /></defs>
          <Area
            type="monotone"
            dataKey="v"
            stroke="currentColor"
            strokeWidth={2}
            fill={`url(#${gid})`}
            dot={false}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Vehicle detections by sampled video timestamp. */
export function DetectionChart({ values }: { values: Point[] }) {
  const gid = `detect-${useId().replace(/:/g, "")}`;
  if (!values.length) {
    return (
      <div className="chart-empty">
        <Activity size={23} />
        <strong>No analysis samples yet</strong>
        <span>Process a permitted video to build a real detection trend.</span>
      </div>
    );
  }
  const reduced = values.length > 60 ? values.filter((_, i) => i % Math.ceil(values.length / 60) === 0) : values;
  const data = reduced.map((p) => ({ t: fmtTime(p.timestamp_seconds), v: p.vehicle_count }));
  const max = Math.max(1, ...data.map((d) => d.v));
  return (
    <div className="chart-wrap">
      <div className="line-chart" role="img" aria-label="Vehicle detections by sampled video timestamp">
        <ResponsiveContainer width="100%" height={210}>
          <AreaChart data={data} margin={{ top: 8, right: 10, left: 10, bottom: 0 }}>
            <defs><FadeGradient id={gid} top={0.32} /></defs>
            <CartesianGrid vertical={false} strokeDasharray="3 6" />
            <XAxis dataKey="t" hide />
            <YAxis hide domain={[0, Math.ceil(max * 1.15)]} />
            <Tooltip content={<ChartTip />} cursor={{ strokeDasharray: "4 4" }} />
            <Area
              type="monotone"
              dataKey="v"
              stroke="currentColor"
              strokeWidth={2.5}
              fill={`url(#${gid})`}
              dot={false}
              activeDot={{ r: 4, strokeWidth: 2 }}
              isAnimationActive={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
      <div className="chart-axis">
        <span>{data[0].t}</span>
        <span>{data[Math.floor(data.length / 2)].t}</span>
        <span>{data[data.length - 1].t}</span>
      </div>
    </div>
  );
}

/** Compact vertical bar chart (activity by day). */
export function BarChart({ data, ariaLabel, seriesIndex = 1 }: { data: { label: string; value: number; hint?: string }[]; ariaLabel: string; seriesIndex?: number }) {
  if (!data.length) {
    return (
      <div className="chart-empty">
        <Activity size={22} />
        <strong>No activity in this window</strong>
        <span>Actions appear here as soon as videos are imported or analyzed.</span>
      </div>
    );
  }
  const max = Math.max(1, ...data.map((d) => d.value));
  return (
    <div className="bar-chart" role="img" aria-label={ariaLabel}>
      {data.map((entry, index) => (
        <div className="bar-col" key={`${entry.label}-${index}`} title={entry.hint || `${entry.label}: ${entry.value}`}>
          <div className="bar-value">{entry.value || ""}</div>
          <div className="bar-track">
            <i style={{ height: `${Math.max(entry.value ? 6 : 2, (entry.value / max) * 100)}%`, background: `var(--pw-series-${seriesIndex})` }} />
          </div>
          <span className="bar-label">{entry.label}</span>
        </div>
      ))}
    </div>
  );
}

/** Pie/donut chart with legend. */
export function Donut({ slices, ariaLabel, centerLabel, centerValue }: { slices: { label: string; value: number; tone?: number }[]; ariaLabel: string; centerLabel?: string; centerValue?: string }) {
  const total = slices.reduce((sum, slice) => sum + slice.value, 0);
  if (!total) {
    return (
      <div className="chart-empty">
        <Activity size={22} />
        <strong>No measured data yet</strong>
        <span>Charts populate after the first completed analysis.</span>
      </div>
    );
  }
  const radius = 62, stroke = 24, circumference = 2 * Math.PI * radius;
  const lengths = slices.map((slice) => (slice.value / total) * circumference);
  const offsets = slices.map((_, index) => lengths.slice(0, index).reduce((sum, length) => sum + length, 0));
  return (
    <div className="donut-wrap">
      <svg viewBox="0 0 160 160" className="donut-chart" role="img" aria-label={ariaLabel}>
        <g transform="rotate(-90 80 80)">
          {slices.map((slice, index) => {
            const length = lengths[index];
            return (
              <circle
                key={slice.label}
                cx="80" cy="80" r={radius}
                fill="none"
                style={{ stroke: SERIES[(slice.tone ?? index) % SERIES.length] }}
                strokeWidth={stroke}
                strokeDasharray={`${Math.max(0, length - 2)} ${circumference - Math.max(0, length - 2)}`}
                strokeDashoffset={-offsets[index]}
              />
            );
          })}
        </g>
        {centerValue && <text x="80" y="76" textAnchor="middle" className="donut-center-value">{centerValue}</text>}
        {centerLabel && <text x="80" y="96" textAnchor="middle" className="donut-center-label">{centerLabel}</text>}
      </svg>
      <div className="donut-legend">
        {slices.map((slice, index) => (
          <div className="legend-row" key={slice.label}>
            <i style={{ background: SERIES[(slice.tone ?? index) % SERIES.length] }} />
            <span>{slice.label}</span>
            <strong>{slice.value.toLocaleString()}</strong>
            <em>{((slice.value / total) * 100).toFixed(0)}%</em>
          </div>
        ))}
      </div>
    </div>
  );
}

/** Smoothed area chart for percentage or scalar trends (occupancy by day). */
export function TrendChart({ points, unit = "%", ariaLabel }: { points: { label: string; value: number }[]; unit?: string; ariaLabel: string }) {
  const gid = `trend-${useId().replace(/:/g, "")}`;
  if (points.length < 2) {
    return (
      <div className="chart-empty">
        <Activity size={22} />
        <strong>Not enough history yet</strong>
        <span>Two or more completed analyses are needed to draw a trend.</span>
      </div>
    );
  }
  const data = points.map((p) => ({ t: p.label, v: p.value }));
  const max = Math.max(1, ...data.map((d) => d.v));
  return (
    <div className="chart-wrap">
      <div className="line-chart trend-line" role="img" aria-label={ariaLabel}>
        <ResponsiveContainer width="100%" height={200}>
          <AreaChart data={data} margin={{ top: 8, right: 10, left: 10, bottom: 0 }}>
            <defs><FadeGradient id={gid} top={0.35} /></defs>
            <CartesianGrid vertical={false} strokeDasharray="3 6" />
            <XAxis dataKey="t" hide />
            <YAxis hide domain={[0, Math.ceil(max * 1.15)]} />
            <Tooltip content={<ChartTip unit={unit} />} cursor={{ strokeDasharray: "4 4" }} />
            <Area
              type="monotone"
              dataKey="v"
              stroke="currentColor"
              strokeWidth={2.5}
              fill={`url(#${gid})`}
              dot={{ r: 3, strokeWidth: 0 }}
              activeDot={{ r: 4, strokeWidth: 2 }}
              isAnimationActive={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
      <div className="chart-axis">
        <span>{points[0].label} · {points[0].value}{unit}</span>
        <span>{points[Math.floor(points.length / 2)].label}</span>
        <span>{points[points.length - 1].label} · {points[points.length - 1].value}{unit}</span>
      </div>
    </div>
  );
}

/** Horizontal bar rows — per-actor activity breakdowns. */
export function HBarChart({ items, ariaLabel, seriesIndex = 1 }: { items: { label: string; value: number; hint?: string }[]; ariaLabel: string; seriesIndex?: number }) {
  if (!items.length) {
    return (
      <div className="chart-empty">
        <Activity size={22} />
        <strong>No user activity recorded yet</strong>
        <span>Uploads, analyses, calibrations and setting changes appear here per actor.</span>
      </div>
    );
  }
  const max = Math.max(1, ...items.map((item) => item.value));
  return (
    <div className="hbar-chart" role="img" aria-label={ariaLabel}>
      {items.map((entry) => (
        <div className="hbar-row" key={entry.label} title={entry.hint || `${entry.label}: ${entry.value} actions`}>
          <span className="hbar-name">{entry.label}</span>
          <div className="hbar-track">
            <i style={{ width: `${Math.max(4, (entry.value / max) * 100)}%`, background: `var(--pw-series-${seriesIndex})` }} />
          </div>
          <strong className="hbar-value">{entry.value}</strong>
        </div>
      ))}
    </div>
  );
}

/** 100% stacked share bar with a legend — categorical mixes (action types, origins). */
export function ShareBar({ items, ariaLabel }: { items: { label: string; value: number; tone?: number }[]; ariaLabel: string }) {
  const total = items.reduce((sum, item) => sum + item.value, 0);
  if (!total) {
    return (
      <div className="chart-empty">
        <Activity size={22} />
        <strong>No mix to break down yet</strong>
        <span>Once actions are recorded, their share appears here.</span>
      </div>
    );
  }
  const color = (index: number, tone?: number) => `var(--pw-series-${((tone ?? index) % SERIES.length) + 1})`;
  return (
    <div className="share-bar" role="img" aria-label={ariaLabel}>
      <div className="share-track">
        {items.filter((item) => item.value > 0).map((item, index) => (
          <i
            key={item.label}
            style={{ width: `${(item.value / total) * 100}%`, background: color(index, item.tone) }}
            title={`${item.label}: ${item.value} (${((item.value / total) * 100).toFixed(0)}%)`}
          />
        ))}
      </div>
      <div className="share-legend">
        {items.map((item, index) => (
          <div className="share-legend-row" key={item.label}>
            <i style={{ background: color(index, item.tone) }} />
            <span>{item.label}</span>
            <strong>{item.value.toLocaleString()}</strong>
            <em>{((item.value / total) * 100).toFixed(0)}%</em>
          </div>
        ))}
      </div>
    </div>
  );
}

export function ChartCard({ eyebrow, title, action, children, className }: { eyebrow: string; title: string; action?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`panel ${className || ""}`}>
      <div className="panel-header">
        <div>
          <div className="panel-eyebrow">{eyebrow}</div>
          <h2>{title}</h2>
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}

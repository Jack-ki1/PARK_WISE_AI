"use client";

import type { ReactNode } from "react";
import { Activity } from "lucide-react";
import { fmtTime, type Point } from "@/lib/data";

export function Sparkline({ values, tone = "violet" }: { values: number[]; tone?: string }) {
  if (values.length < 2) return <div className="spark-empty">Waiting for samples</div>;
  const min = Math.min(...values), max = Math.max(...values), spread = max - min || 1;
  const coords = values.map((v, i) => `${(i / (values.length - 1)) * 100},${28 - ((v - min) / spread) * 24}`).join(" ");
  return (
    <svg className={`sparkline ${tone}`} viewBox="0 0 100 32" preserveAspectRatio="none" role="img" aria-label="Observed values across sampled video frames">
      <polyline points={coords} fill="none" stroke="currentColor" strokeWidth="2" vectorEffect="non-scaling-stroke" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function DetectionChart({ values }: { values: Point[] }) {
  if (!values.length) {
    return <div className="chart-empty"><Activity size={23} /><strong>No analysis samples yet</strong><span>Process a permitted video to build a real detection trend.</span></div>;
  }
  const reduced = values.length > 60 ? values.filter((_, i) => i % Math.ceil(values.length / 60) === 0) : values;
  const counts = reduced.map((p) => p.vehicle_count), max = Math.max(1, ...counts);
  const width = 780, height = 220, padX = 12, padY = 18;
  const points = counts.map((v, i) => `${padX + (i / Math.max(1, counts.length - 1)) * (width - padX * 2)},${height - padY - (v / max) * (height - padY * 2)}`).join(" ");
  return (
    <div className="chart-wrap">
      <svg viewBox={`0 0 ${width} ${height}`} className="line-chart" role="img" aria-label="Vehicle detections by sampled video timestamp">
        <defs><linearGradient id="chartGradient" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stopColor="var(--pw-chart-accent)" stopOpacity=".25" /><stop offset="100%" stopColor="var(--pw-chart-accent)" stopOpacity="0" /></linearGradient></defs>
        {[0, 1, 2, 3].map((i) => <line key={i} x1={padX} x2={width - padX} y1={20 + i * 55} y2={20 + i * 55} stroke="var(--pw-chart-grid)" strokeDasharray="4 7" />)}
        <polygon points={`${padX},${height - padY} ${points} ${width - padX},${height - padY}`} fill="url(#chartGradient)" />
        <polyline points={points} fill="none" stroke="var(--pw-chart-line)" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
      </svg>
      <div className="chart-axis">
        <span>{fmtTime(reduced[0].timestamp_seconds)}</span>
        <span>{fmtTime(reduced[Math.floor(reduced.length / 2)].timestamp_seconds)}</span>
        <span>{fmtTime(reduced[reduced.length - 1].timestamp_seconds)}</span>
      </div>
    </div>
  );
}

/** Compact vertical bar chart (activity by day). */
export function BarChart({ data, ariaLabel, seriesIndex = 1 }: { data: { label: string; value: number; hint?: string }[]; ariaLabel: string; seriesIndex?: number }) {
  if (!data.length) return <div className="chart-empty"><Activity size={22} /><strong>No activity in this window</strong><span>Actions appear here as soon as videos are imported or analyzed.</span></div>;
  const max = Math.max(1, ...data.map((d) => d.value));
  return (
    <div className="bar-chart" role="img" aria-label={ariaLabel}>
      {data.map((entry) => (
        <div className="bar-col" key={entry.label} title={entry.hint || `${entry.label}: ${entry.value}`}>
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

const TONES = ["var(--pw-series-1)", "var(--pw-series-3)", "var(--pw-series-5)", "var(--pw-series-2)", "var(--pw-series-4)", "var(--pw-series-6)"];

/** Pie/donut chart with legend. */
export function Donut({ slices, ariaLabel, centerLabel, centerValue }: { slices: { label: string; value: number; tone?: number }[]; ariaLabel: string; centerLabel?: string; centerValue?: string }) {
  const total = slices.reduce((sum, slice) => sum + slice.value, 0);
  if (!total) return <div className="chart-empty"><Activity size={22} /><strong>No measured data yet</strong><span>Charts populate after the first completed analysis.</span></div>;
  const radius = 62, stroke = 24, circumference = 2 * Math.PI * radius;
  const lengths = slices.map(slice => (slice.value / total) * circumference);
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
                stroke={TONES[(slice.tone ?? index) % TONES.length]}
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
            <i style={{ background: TONES[(slice.tone ?? index) % TONES.length] }} />
            <span>{slice.label}</span>
            <strong>{slice.value.toLocaleString()}</strong>
            <em>{((slice.value / total) * 100).toFixed(0)}%</em>
          </div>
        ))}
      </div>
    </div>
  );
}

/** Smoothed area/line chart for percentage or scalar trends (occupancy by day). */
export function TrendChart({ points, unit = "%", ariaLabel }: { points: { label: string; value: number }[]; unit?: string; ariaLabel: string }) {
  if (points.length < 2) return <div className="chart-empty"><Activity size={22} /><strong>Not enough history yet</strong><span>Two or more completed days of measurements are needed for a trend.</span></div>;
  const width = 720, height = 200, padX = 14, padY = 20;
  const max = Math.max(1, ...points.map((p) => p.value));
  const coords = points.map((p, i) => {
    const x = padX + (i / (points.length - 1)) * (width - padX * 2);
    const y = height - padY - (p.value / max) * (height - padY * 2);
    return { x, y, ...p };
  });
  const line = coords.map((c) => `${c.x},${c.y}`).join(" ");
  return (
    <div className="chart-wrap">
      <svg viewBox={`0 0 ${width} ${height}`} className="line-chart" role="img" aria-label={ariaLabel}>
        <defs><linearGradient id="trendGradient" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stopColor="var(--pw-series-3)" stopOpacity=".3" /><stop offset="100%" stopColor="var(--pw-series-3)" stopOpacity="0" /></linearGradient></defs>
        {[0, 1, 2, 3].map((i) => <line key={i} x1={padX} x2={width - padX} y1={20 + i * 50} y2={20 + i * 50} stroke="var(--pw-chart-grid)" strokeDasharray="4 7" />)}
        <polygon points={`${padX},${height - padY} ${line} ${width - padX},${height - padY}`} fill="url(#trendGradient)" />
        <polyline points={line} fill="none" stroke="var(--pw-series-3)" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
        {coords.map((c) => <circle key={c.label} cx={c.x} cy={c.y} r="4" fill="var(--pw-series-3)" />)}
      </svg>
      <div className="chart-axis">
        <span>{points[0].label} · {points[0].value}{unit}</span>
        <span>{points[Math.floor(points.length / 2)].label}</span>
        <span>{points[points.length - 1].label} · {points[points.length - 1].value}{unit}</span>
      </div>
    </div>
  );
}

export function ChartCard({ eyebrow, title, action, children, className }: { eyebrow: string; title: string; action?: ReactNode; children: ReactNode; className?: string }) {
  return <section className={`panel ${className || ""}`}><div className="panel-header"><div><div className="panel-eyebrow">{eyebrow}</div><h2>{title}</h2></div>{action}</div>{children}</section>;
}

"use client";

import type { LucideIcon } from "lucide-react";

interface MetricCardProps {
  label: string;
  value: string | number;
  delta?: {
    value: string;
    tone: "up" | "down" | "flat";
  };
  hint?: string;
  icon?: LucideIcon;
}

export function MetricCard({ label, value, delta, hint, icon: Icon }: MetricCardProps) {
  return (
    <section className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4 shadow-[var(--shadow-1)] transition-colors">
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold uppercase tracking-[0.04em] text-[var(--text-subtle)]">
          {label}
        </p>
        {Icon && <Icon className="h-4 w-4 text-[var(--text-muted)]" aria-hidden="true" />}
      </div>
      <p className="mt-2 text-2xl font-semibold leading-8 tabular-nums text-[var(--text)] sm:text-3xl sm:leading-10">
        {value}
      </p>
      {(delta || hint) && (
        <p className="mt-1 flex items-center gap-1.5 text-xs text-[var(--text-muted)]">
          {delta && (
            <span
              className={
                delta.tone === "up"
                  ? "font-medium text-[var(--success-text)]"
                  : delta.tone === "down"
                  ? "font-medium text-[var(--danger-text)]"
                  : "font-medium text-[var(--text-muted)]"
              }
            >
              {delta.value}
            </span>
          )}
          {hint && <span>{hint}</span>}
        </p>
      )}
    </section>
  );
}

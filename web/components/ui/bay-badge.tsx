"use client";

import { CheckCircle2, Car, HelpCircle, AlertCircle } from "lucide-react";

interface BayBadgeProps {
  state: "free" | "occupied" | "unknown" | "stale" | string;
  name?: string;
  confidence?: number | null;
  className?: string;
}

export function BayBadge({ state, name, confidence, className = "" }: BayBadgeProps) {
  const normState = state.toLowerCase();

  const config = {
    free: {
      icon: CheckCircle2,
      label: "Free",
      bg: "bg-[var(--success-bg)]",
      text: "text-[var(--success-text)]",
      border: "border-[var(--success-fill)]/30",
    },
    occupied: {
      icon: Car,
      label: "Occupied",
      bg: "bg-[var(--accent-subtle)]",
      text: "text-[var(--accent)]",
      border: "border-[var(--accent)]/30",
    },
    unknown: {
      icon: HelpCircle,
      label: "Unknown",
      bg: "bg-[var(--surface-sunken)]",
      text: "text-[var(--text-subtle)]",
      border: "border-[var(--border)]",
    },
    stale: {
      icon: AlertCircle,
      label: "Stale",
      bg: "bg-[var(--warning-bg)]",
      text: "text-[var(--warning-text)]",
      border: "border-[var(--warning-fill)]/30",
    },
  }[normState] || {
    icon: HelpCircle,
    label: state,
    bg: "bg-[var(--surface-sunken)]",
    text: "text-[var(--text-subtle)]",
    border: "border-[var(--border)]",
  };

  const Icon = config.icon;

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium ${config.bg} ${config.text} ${config.border} ${className}`}
    >
      <Icon className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
      <span>{name ? `${name}: ${config.label}` : config.label}</span>
      {confidence != null && (
        <span className="opacity-75 tabular-nums">({Math.round(confidence * 100)}%)</span>
      )}
    </span>
  );
}

/** Formatting utilities for numbers, durations, timestamps, and confidence scores. */

export function fmtNum(value: number | null | undefined): string {
  if (value == null) return "—";
  return new Intl.NumberFormat().format(value);
}

export function fmtDuration(seconds: number | null | undefined): string {
  if (seconds == null) return "—";
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return mins ? `${mins}m ${secs}s` : `${secs}s`;
}

export function fmtTime(seconds: number): string {
  const sign = seconds < 0 ? "-" : "";
  const s = Math.abs(seconds);
  return `${sign}${Math.floor(s / 60).toString().padStart(2, "0")}:${Math.floor(s % 60).toString().padStart(2, "0")}`;
}

export function confFmt(value: number | null | undefined): string {
  if (value == null) return "—";
  return `${(value * 100).toFixed(1)}%`;
}

export function statusLabel(status: string): string {
  switch (status) {
    case "completed":
      return "Completed";
    case "processing":
      return "Processing";
    case "queued":
      return "Queued";
    case "failed":
      return "Failed";
    case "live":
      return "Live";
    case "error":
      return "Error";
    case "idle":
      return "Idle";
    default:
      return "Ready to analyze";
  }
}

export function statusClass(status: string): string {
  switch (status) {
    case "completed":
    case "live":
      return "success";
    case "failed":
    case "error":
      return "danger";
    case "processing":
    case "queued":
      return "processing";
    default:
      return "neutral";
  }
}

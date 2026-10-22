"use client";

import { useSyncExternalStore } from "react";

/* ------------------------------------------------------------------ types */

export type VideoJob = {
  id: string; original_name: string; source_type: string; source_id: string | null; source_title: string | null;
  source_page: string | null; status: string; progress_percent: number; current_frame: number; processed_frames: number;
  width: number | null; height: number | null; fps: number | null; source_frame_count: number | null;
  duration_seconds: number | null; max_vehicle_count: number | null; avg_confidence: number | null;
  error_message: string | null; model_name: string | null; created_at: string; completed_at: string | null;
  preview_url: string | null; original_url: string | null; annotated_url: string | null; configured_spaces: number;
};

export type Source = {
  id: string; title: string; creator: string; landing_page: string; description: string;
  duration_seconds: number; resolution: string; license_label: string;
};

export type Summary = {
  total_videos: number; completed_videos: number; processing_videos: number; latest_video_id: string | null;
  latest_video_name: string | null; latest_status: string | null; vehicles_in_latest_sample: number | null;
  peak_vehicles_observed: number | null; configured_spaces: number; occupied_spaces: number; free_spaces: number;
  unknown_spaces: number; occupancy_percent: number | null; latest_confidence: number | null; has_data: boolean;
};

export type Space = { id: string; video_id: string; name: string; polygon: number[][]; state: string; confidence: number | null; last_seen_seconds: number | null };
export type Point = { timestamp_seconds: number; frame_number: number; vehicle_count: number; tracked_vehicle_count: number; mean_confidence: number | null };
export type OccupancyPoint = { space_id: string; space_name: string; timestamp_seconds: number; state: string; confidence: number | null };
export type OccupancySeries = { items: OccupancyPoint[] };

export type PublicConfig = {
  model: string; confidence: number; image_size: number; frame_stride: number; device: string; multiscale: boolean;
  max_upload_mb: number; max_video_seconds: number; public_source_fetch_enabled: boolean;
  auth_required: boolean; rate_limit_per_minute: number; plan: string;
};

export type ReviewedVideo = {
  id: string; name: string; completed_at: string | null; peak_vehicles: number | null;
  avg_confidence: number | null; duration_seconds: number | null; samples: number; occupied_share_percent: number | null;
};

export type AnalyticsPayload = {
  generated_at: string;
  kpis: {
    videos_total: number; videos_completed: number; videos_processing: number; videos_failed: number;
    bays_configured: number; detections_logged: number; streams_total: number; streams_live: number;
    videos_this_month: number; analyzed_hours: number; peak_vehicles: number | null; avg_confidence: number | null;
    utilisation_percent: number | null; storage_gb: number; concurrent_jobs: number;
  };
  charts: {
    occupancy_trend: { date: string; percent: number }[];
    activity_by_day: { date: string; actions: Record<string, number>; total: number }[];
    activity_by_action: Record<string, number>;
    status_breakdown: { status: string; count: number }[];
    state_mix: { state: string; samples: number }[];
    utilisation: { label: string; value: number }[];
    top_videos: ReviewedVideo[];
  };
  reviewed_videos: ReviewedVideo[];
};

export type ActivityItem = {
  id: number; actor: string; action: string; object_type: string | null; object_id: string | null;
  detail: string | null; created_at: string | null;
};

export type StreamSpace = { name: string; polygon: number[][] };

export type StreamRow = {
  id: string; name: string; kind: string; url: string | null; video_id: string | null; video_name: string | null;
  enabled: boolean; status: string; last_error: string | null; target_fps: number; running: boolean;
  subscriber_count: number; frames_delivered: number; last_frame_at: string | null; lat: number | null;
  lon: number | null; spaces: StreamSpace[]; space_count: number; snapshot_url: string | null; created_at: string | null;
};

export type LiveFrame = {
  type: string; seq: number; jpeg?: string; stream_id?: string; ts?: string; vehicle_count?: number;
  tracked?: number; mean_confidence?: number | null; bays?: { name: string; state: string; confidence: number }[];
  occupied?: number; total?: number; events?: LiveEvent[]; inference_fps?: number; latency_ms?: number; model?: string;
  status?: string; error?: string | null; detail?: string;
};

export type LiveEvent = { type: string; ts?: string; bay?: string; from?: string; to?: string; direction?: string; track_id?: number; occupied?: number; total?: number };

export type SettingsPayload = {
  settings: Record<string, unknown>;
  schema: Record<string, { type: string; choices?: string[] }>;
  plans: Record<string, PlanInfo>;
  env: { auth_required: boolean; rate_limit_per_minute: number; max_upload_mb: number; max_video_seconds: number; env: string };
};

export type PlanInfo = { name: string; price_month_usd: number; blurb: string; limits: Record<string, number> };

export type BillingReport = {
  plan: string; plan_info: PlanInfo; month: string; videos_total: number;
  usage: Record<string, number>;
  meters: { label: string; used: number; limit: number; key: string; percent: number; exceeded: boolean }[];
};

export type UserRow = {
  id: string; username: string; display_name: string; role: string; is_active: boolean;
  has_api_key: boolean; created_at: string; last_login_at: string | null;
};

export type SystemInfo = {
  service: string; env: string;
  python_model_stack: { default_model: string; ultralytics_license: string };
  model_catalog: string[];
  security: { auth_required: boolean; rate_limit_per_minute: number; roles: string[]; upload_max_mb: number; ssrf_schemes_allowed: string[] };
  docs_url: string; activity_events: number;
};

/* -------------------------------------------------------------------- api */

export const API = (process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000").replace(/\/$/, "");
export const WS_BASE = API.replace(/^http:/, "ws:").replace(/^https:/, "wss:");

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, { ...init, cache: "no-store" });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof payload.detail === "string" ? payload.detail : `Request failed (${response.status})`);
  return payload as T;
}

/* -------------------------------------------------------------- formatters */

export function fmtNum(value: number | null | undefined) { return value == null ? "—" : new Intl.NumberFormat().format(value); }
export function fmtDuration(seconds: number | null | undefined) {
  if (seconds == null) return "—";
  const mins = Math.floor(seconds / 60); const secs = Math.floor(seconds % 60);
  return mins ? `${mins}m ${secs}s` : `${secs}s`;
}
export function fmtTime(seconds: number) {
  const sign = seconds < 0 ? "-" : ""; const s = Math.abs(seconds);
  return `${sign}${Math.floor(s / 60).toString().padStart(2, "0")}:${Math.floor(s % 60).toString().padStart(2, "0")}`;
}
export function statusLabel(status: string) {
  return status === "completed" ? "Completed" : status === "processing" ? "Processing" : status === "queued" ? "Queued"
    : status === "failed" ? "Failed" : status === "live" ? "Live" : status === "error" ? "Error" : status === "idle" ? "Idle" : "Ready to analyze";
}
export function statusClass(status: string) {
  return status === "completed" || status === "live" ? "success" : status === "failed" || status === "error" ? "danger"
    : status === "processing" || status === "queued" ? "processing" : "neutral";
}
export function confFmt(value: number | null | undefined) { return value == null ? "—" : `${(value * 100).toFixed(1)}%`; }

/* ------------------------------------------------------------------- theme */

export type Theme = "dark" | "light";
const THEME_EVENT = "parkwise-theme";
function readTheme(): Theme { return typeof document !== "undefined" && document.documentElement.dataset.theme === "light" ? "light" : "dark"; }
export function useTheme() {
  const theme = useSyncExternalStore(
    (onChange) => {
      const emit = () => onChange();
      document.addEventListener(THEME_EVENT, emit);
      window.addEventListener("storage", emit);
      return () => { document.removeEventListener(THEME_EVENT, emit); window.removeEventListener("storage", emit); };
    },
    readTheme,
    () => "dark" as Theme,
  );
  const toggleTheme = () => {
    const next: Theme = theme === "light" ? "dark" : "light";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem("parkwise-theme", next); } catch { /* storage may be unavailable */ }
    document.dispatchEvent(new Event(THEME_EVENT));
  };
  return { theme, toggleTheme };
}

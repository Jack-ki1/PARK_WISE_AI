"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ChangeEvent, FormEvent } from "react";
import type { LucideIcon } from "lucide-react";
import {
  Activity, AlertTriangle, ArrowRight, Building2, CalendarDays, Check, ChevronDown, CircleHelp,
  CloudDownload, Clock, Cpu, CreditCard, Database, Download, FileVideo, Gauge, HardDriveUpload, KeyRound,
  LayoutDashboard, Layers3, LoaderCircle, MapPin, Menu, Moon, Play, Plus, RadioTower, RefreshCw,
  Search, Send, Settings2, ShieldCheck, SlidersHorizontal, Square, Sun, Trash2, Users, Video, Webhook, Wifi, X, Zap,
} from "lucide-react";

import { BarChart, ChartCard, DetectionChart, Donut, HBarChart, ShareBar, Sparkline, TrendChart } from "@/components/charts";
import { CalibrationCanvas, EmptyTable, Fact, JobsTable, MetricCard, PanelHeader } from "@/components/ui";
import SiteMap from "@/components/sitemap";
import {
  API, api, confFmt, downloadFile, fmtDuration, fmtNum, fmtTime, getApiKey, setSessionApiKey, statusClass,
  statusLabel, streamSocketUrl, useTheme, videoSocketUrl, MAX_POLYGON_POINTS,
  type ActivityItem, type AnalyticsPayload, type BillingReport, type LiveEvent, type LiveFrame,
  type OccupancyPoint, type OccupancySeries, type Point, type PublicConfig, type ReviewedVideo,
  type SettingsPayload, type Space, type Source, type StreamRow, type Summary, type SystemInfo,
  type UserRow, type VideoJob,
} from "@/lib/data";

type PageId = "dashboard" | "live" | "settings";
type SettingsTabId = "model" | "integrations" | "users" | "billing" | "system";
type AnalysisMode = "live" | "recorded";
type NavItem = { id: PageId; label: string; icon: LucideIcon; section?: string };

const navItems: NavItem[] = [
  { id: "dashboard", label: "Dashboard", icon: LayoutDashboard, section: "WORKSPACE" },
  { id: "live", label: "Live Analysis", icon: RadioTower, section: "MONITORING" },
  { id: "settings", label: "Settings", icon: Settings2, section: "ADMINISTRATION" },
];

const settingsTabs: { id: SettingsTabId; label: string; icon: LucideIcon }[] = [
  { id: "model", label: "Model", icon: Cpu },
  { id: "integrations", label: "Integrations", icon: Webhook },
  { id: "users", label: "Users", icon: Users },
  { id: "billing", label: "Billing", icon: CreditCard },
  { id: "system", label: "System", icon: ShieldCheck },
];

const pageMeta: Record<PageId, { eyebrow: string; title: string; subtitle: string }> = {
  dashboard: {
    eyebrow: "OPERATIONS CENTER",
    title: "Dashboard",
    subtitle: "KPIs, activity breakdowns and reviewed-video annotations derived from real inference results.",
  },
  live: {
    eyebrow: "ANALYSIS WORKSPACE",
    title: "Live analysis",
    subtitle: "Review a live camera feed or a recorded clip — annotations, real-time findings, re-annotation and downloads in one place.",
  },
  settings: {
    eyebrow: "CONFIGURATION",
    title: "Settings",
    subtitle: "Model runtime, integrations, users, billing plans and system posture.",
  },
};

const MODEL_FAMILIES: { key: string; name: string; note: string }[] = [
  { key: "yolo26", name: "YOLO26", note: "Newest family (2026): NMS-free, DFL-free head with fast CPU ONNX inference and MuSGD training improvements." },
  { key: "yolo11", name: "YOLO11", note: "Proven 2024 family with mature export and tooling support; a safe comparison baseline." },
  { key: "rtdetr", name: "RT-DETR", note: "Transformer detector for accuracy-first experiments. Benchmark on your own holdout clips before switching." },
];

export default function HomePage() {
  const [activePage, setActivePage] = useState<PageId>("dashboard");
  const [settingsTab, setSettingsTab] = useState<SettingsTabId>("model");
  const [analysisMode, setAnalysisMode] = useState<AnalysisMode>("live");
  const [summary, setSummary] = useState<Summary | null>(null);
  const [videos, setVideos] = useState<VideoJob[]>([]);
  const [sources, setSources] = useState<Source[]>([]);
  const [serverConfig, setServerConfig] = useState<PublicConfig | null>(null);
  const [selectedId, setSelectedId] = useState("");
  const [spacesByVideo, setSpacesByVideo] = useState<Record<string, Space[]>>({});
  const [analyticsByVideo, setAnalyticsByVideo] = useState<Record<string, Point[]>>({});
  const [occupancyByVideo, setOccupancyByVideo] = useState<Record<string, OccupancyPoint[]>>({});
  const [pendingByVideo, setPendingByVideo] = useState<Record<string, number[][]>>({});
  const [spaceName, setSpaceName] = useState("Bay 01");
  const [uploading, setUploading] = useState(false);
  const [busySource, setBusySource] = useState("");
  const [processingId, setProcessingId] = useState("");
  const [apiStatus, setApiStatus] = useState<"checking" | "online" | "offline">("checking");
  const [message, setMessage] = useState<{ tone: "success" | "error" | "info"; text: string } | null>(null);
  const [mobileNav, setMobileNav] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const { theme, toggleTheme } = useTheme();

  // Dashboard aggregates
  const [dash, setDash] = useState<AnalyticsPayload | null>(null);
  const [activity, setActivity] = useState<ActivityItem[]>([]);
  const [reviewId, setReviewId] = useState("");
  const reviewRef = useRef<HTMLElement | null>(null);

  // Live streams
  const [streams, setStreams] = useState<StreamRow[]>([]);
  const [selectedStreamId, setSelectedStreamId] = useState("");
  const [watchId, setWatchId] = useState("");
  const [liveFrame, setLiveFrame] = useState<LiveFrame | null>(null);
  const [wsStatus, setWsStatus] = useState<"idle" | "connecting" | "live" | "error">("idle");
  const [liveEvents, setLiveEvents] = useState<LiveEvent[]>([]);
  const [streamName, setStreamName] = useState("");
  const [streamKind, setStreamKind] = useState<"url" | "video">("url");
  const [streamUrl, setStreamUrl] = useState("");
  const [streamVideoId, setStreamVideoId] = useState("");
  const [streamFps, setStreamFps] = useState("6");
  const [streamLat, setStreamLat] = useState("");
  const [streamLon, setStreamLon] = useState("");
  const [calibratingId, setCalibratingId] = useState("");
  const [snapshot, setSnapshot] = useState<{ id: string; url: string } | null>(null);
  const [streamBayName, setStreamBayName] = useState("Bay A1");
  const [streamPending, setStreamPending] = useState<number[][]>([]);
  // Live session recording: annotated JPEG frames are drawn to a canvas and
  // captured with MediaRecorder so the review can be downloaded as a clip.
  const [recording, setRecording] = useState(false);
  const recRef = useRef<{ recorder: MediaRecorder; stream: MediaStream; chunks: Blob[] } | null>(null);
  const recDrawRef = useRef<((jpeg: string) => void) | null>(null);

  // Settings
  const [settingsPayload, setSettingsPayload] = useState<SettingsPayload | null>(null);
  const [billingReport, setBillingReport] = useState<BillingReport | null>(null);
  const [users, setUsers] = useState<UserRow[]>([]);
  const [usersError, setUsersError] = useState<string | null>(null);
  const [systemInfo, setSystemInfo] = useState<SystemInfo | null>(null);
  const [modelDraft, setModelDraft] = useState({ model: "", confidence: 0.4, image_size: 640, frame_stride: 4, device: "auto", multiscale: true });
  const [modelTouched, setModelTouched] = useState(false);
  const [intDraft, setIntDraft] = useState({ webhookUrl: "", webhookSecret: "", publicSources: true, mapStyle: "", mapLat: "", mapLon: "" });
  const [intTouched, setIntTouched] = useState(false);
  const [newUser, setNewUser] = useState({ username: "", display_name: "", role: "operator" });
  const [plainKey, setPlainKey] = useState<{ key: string; note: string } | null>(null);
  const [webhookResult, setWebhookResult] = useState("");
  const [userSearch, setUserSearch] = useState("");
  const [downloadingId, setDownloadingId] = useState("");
  // Session-scoped API key for this browser tab (never localStorage).
  const [sessionKeyInput, setSessionKeyInput] = useState("");
  const [sessionKeyActive, setSessionKeyActive] = useState(false);

  // Settings forms: show server values until the operator edits them (touched flag),
  // so fresh payloads never clobber in-progress typing.
  const serverModelDraft = {
    model: String(settingsPayload?.settings.model ?? ""),
    confidence: Number(settingsPayload?.settings.confidence ?? 0.4),
    image_size: Number(settingsPayload?.settings.image_size ?? 640),
    frame_stride: Number(settingsPayload?.settings.frame_stride ?? 4),
    device: String(settingsPayload?.settings.device ?? "auto"),
    multiscale: Boolean(settingsPayload?.settings.multiscale),
  };
  const modelDraftLive = modelTouched ? modelDraft : serverModelDraft;
  const centerRaw = settingsPayload?.settings.map_center;
  const serverIntDraft = {
    webhookUrl: settingsPayload?.settings.webhook_url ? String(settingsPayload.settings.webhook_url) : "",
    // Secrets are never returned by the API; the field always starts blank.
    webhookSecret: "",
    publicSources: Boolean(settingsPayload?.settings.public_sources_enabled),
    mapStyle: settingsPayload?.settings.map_style ? String(settingsPayload.settings.map_style) : "",
    mapLat: Array.isArray(centerRaw) && typeof centerRaw[0] === "number" ? String(centerRaw[0]) : "",
    mapLon: Array.isArray(centerRaw) && typeof centerRaw[1] === "number" ? String(centerRaw[1]) : "",
  };
  const intDraftLive = intTouched ? intDraft : serverIntDraft;
  const patchModel = (patch: Partial<typeof modelDraft>) => { setModelTouched(true); setModelDraft({ ...modelDraftLive, ...patch }); };
  const patchInt = (patch: Partial<typeof intDraft>) => { setIntTouched(true); setIntDraft({ ...intDraftLive, ...patch }); };

  // One-click runtime presets: same model, measured trade-offs between
  // speed, balance and recall. The active preset is detected from the draft.
  const applyModelPreset = (preset: "speed" | "balanced" | "accuracy") => {
    if (preset === "speed") patchModel({ image_size: 416, frame_stride: 8, multiscale: false, confidence: 0.5 });
    else if (preset === "balanced") patchModel({ image_size: 640, frame_stride: 4, multiscale: true, confidence: 0.4 });
    else patchModel({ image_size: 1280, frame_stride: 2, multiscale: true, confidence: 0.35 });
  };
  const modelPreset: "" | "speed" | "balanced" | "accuracy" =
    modelDraftLive.image_size === 416 && modelDraftLive.frame_stride === 8 && !modelDraftLive.multiscale ? "speed"
      : modelDraftLive.image_size === 640 && modelDraftLive.frame_stride === 4 && modelDraftLive.multiscale && modelDraftLive.confidence <= 0.4 ? "balanced"
        : modelDraftLive.image_size >= 1280 && modelDraftLive.frame_stride <= 2 ? "accuracy"
          : "";
  // Which draft fields still differ from the values the server is running.
  const modelChanged: Record<string, boolean> = serverConfig ? {
    model: modelDraftLive.model !== serverConfig.model,
    device: modelDraftLive.device !== serverConfig.device,
    confidence: modelDraftLive.confidence !== serverConfig.confidence,
    image_size: modelDraftLive.image_size !== serverConfig.image_size,
    frame_stride: modelDraftLive.frame_stride !== serverConfig.frame_stride,
    multiscale: modelDraftLive.multiscale !== serverConfig.multiscale,
  } : {};
  const modelDirty = Object.values(modelChanged).some(Boolean);

  const selected = useMemo(() => videos.find(v => v.id === selectedId) || videos[0] || null, [videos, selectedId]);
  const activeTab = navItems.find(n => n.id === activePage)?.label || "Dashboard";
  const activeId = selected?.id ?? "";
  const selectedStatus = selected?.status;
  const spaces = spacesByVideo[activeId] ?? [];
  const analytics = analyticsByVideo[activeId] ?? [];
  const pendingPoints = pendingByVideo[activeId] ?? [];
  const updatePending = (updater: (old: number[][]) => number[][]) => setPendingByVideo(m => ({ ...m, [activeId]: updater(m[activeId] ?? []) }));
  // Backend rejects polygons with more than MAX_POLYGON_POINTS vertices, so the
  // editor refuses to draw past that instead of failing on save.
  const addPolygonPoint = (point: number[], current: number[][], apply: (next: number[][]) => void) => {
    if (current.length >= MAX_POLYGON_POINTS) {
      setMessage({ tone: "info", text: `A polygon can have at most ${MAX_POLYGON_POINTS} points.` });
      return;
    }
    apply([...current, point]);
  };

  const activeStream = streams.find(s => s.id === selectedStreamId) || streams[0] || null;
  const failedVideos = videos.filter(v => v.status === "failed");

  const refreshStreams = useCallback(
    () => api<{ items: StreamRow[] }>("/api/streams").then(data => { setStreams(data.items); }),
    [],
  );

  const refreshData = useCallback((quiet = false) => Promise.all([
    api<{ status: string }>("/api/health"),
    api<Summary>("/api/dashboard/summary"),
    api<VideoJob[]>("/api/videos"),
    api<{ items: Source[] }>("/api/public-sources"),
    api<PublicConfig>("/api/config/public"),
    api<AnalyticsPayload>("/api/dashboard/analytics"),
    api<{ items: ActivityItem[] }>("/api/activity?limit=200").catch(() => ({ items: [] as ActivityItem[] })),
    api<{ items: StreamRow[] }>("/api/streams").catch(() => ({ items: [] as StreamRow[] })),
  ]).then(([health, nextSummary, nextVideos, nextSources, nextConfig, nextDash, nextActivity, nextStreams]) => {
    setApiStatus(health.status === "ok" ? "online" : "offline");
    setSummary(nextSummary);
    setVideos(nextVideos);
    setSources(nextSources.items);
    setServerConfig(nextConfig);
    setDash(nextDash);
    setActivity(nextActivity.items);
    setStreams(nextStreams.items);
    setSelectedId(current => current && nextVideos.some(v => v.id === current) ? current : (nextSummary.latest_video_id || nextVideos[0]?.id || ""));
    if (!quiet) setMessage(current => current?.tone === "error" ? current : null);
  }, (err) => {
    // A background poll that fails is a transport blip, not a data reset: keep
    // the last known rows on screen and only flip the status chip. Repeating
    // the full "Could not reach the API" toast every 5s would bury real errors.
    setApiStatus("offline");
    if (!quiet) setMessage({ tone: "error", text: err instanceof Error ? err.message : "Could not reach the API" });
}), []);

  const refreshAdmin = useCallback(() => Promise.all([
    api<SettingsPayload>("/api/settings"),
    api<BillingReport>("/api/billing"),
    // Admin-only route: a viewer/operator gets 403 here, which must read as
    // "you may not see this list", not as "there are no accounts".
    api<{ items: UserRow[] }>("/api/users").then(
      rows => ({ rows, error: null as string | null }),
      (err: unknown) => ({ rows: { items: [] as UserRow[] }, error: err instanceof Error ? err.message : "Could not load accounts" }),
    ),
    api<SystemInfo>("/api/system/info"),
  ]).then(([settingsData, billingData, userRows, system]) => {
    setSettingsPayload(settingsData);
    setBillingReport(billingData);
    setUsers(userRows.rows.items);
    setUsersError(userRows.error);
    setSystemInfo(system);
  }).catch(() => undefined), []);

  const loadVideoDetail = useCallback((id: string) => {
    if (!id) return;
    Promise.all([
      api<Space[]>(`/api/videos/${id}/spaces`),
      api<Point[]>(`/api/videos/${id}/analytics`),
      api<OccupancySeries>(`/api/videos/${id}/occupancy`).catch(() => ({ items: [] as OccupancyPoint[] })),
    ])
      .then(([nextSpaces, nextPoints, nextOccupancy]) => {
        setSpacesByVideo(m => ({ ...m, [id]: nextSpaces }));
        setAnalyticsByVideo(m => ({ ...m, [id]: nextPoints }));
        setOccupancyByVideo(m => ({ ...m, [id]: nextOccupancy.items }));
        setPendingByVideo(m => ({ ...m, [id]: [] }));
      })
      .catch(() => {
        setSpacesByVideo(m => ({ ...m, [id]: m[id] ?? [] }));
        setAnalyticsByVideo(m => ({ ...m, [id]: m[id] ?? [] }));
        setOccupancyByVideo(m => ({ ...m, [id]: m[id] ?? [] }));
      });
  }, []);

  useEffect(() => {
    refreshData();
    // Eight GETs every 5s: pause them while the tab is in the background and
    // refresh immediately again when the operator comes back.
    const load = () => { if (!document.hidden) refreshData(true); };
    const timer = setInterval(load, 5000);
    const onVisible = () => { if (!document.hidden) refreshData(true); };
    document.addEventListener("visibilitychange", onVisible);
    return () => { clearInterval(timer); document.removeEventListener("visibilitychange", onVisible); };
  }, [refreshData]);
  useEffect(() => { if (activePage === "settings") refreshAdmin(); }, [activePage, refreshAdmin]);
  useEffect(() => {
    if (!activeId || (selectedStatus !== "processing" && selectedStatus !== "queued")) return;
    let socket: WebSocket | null = null;
    let cancelled = false;
    (async () => {
      let url: string;
      try {
        url = await videoSocketUrl(activeId);
      } catch {
        return; // Auth/ticket failure: REST polling below remains the fallback.
      }
      if (cancelled) return;
      socket = new WebSocket(url);
      socket.onmessage = event => {
        try {
          const update = JSON.parse(event.data) as { id: string; status: string; progress_percent: number; current_frame: number; processed_frames: number; error_message: string | null };
          setVideos(current => current.map(job => job.id === update.id ? { ...job, status: update.status, progress_percent: update.progress_percent, current_frame: update.current_frame, processed_frames: update.processed_frames, error_message: update.error_message } : job));
        } catch { /* Invalid messages are ignored; REST polling remains the fallback. */ }
      };
    })();
    return () => { cancelled = true; socket?.close(); };
  }, [activeId, selectedStatus]);
  useEffect(() => { if (activeId) loadVideoDetail(activeId); }, [activeId, selectedStatus, loadVideoDetail]);

  // Live frame WebSocket: connects only while Live Analysis is open and a stream is watched.
  // Auth uses a short-lived single-use ticket (never a durable API key in the URL).
  useEffect(() => {
    if (activePage !== "live" || !watchId) return;
    let socket: WebSocket | null = null;
    let cancelled = false;
    (async () => {
      let url: string;
      try {
        url = await streamSocketUrl(watchId);
      } catch (err) {
        if (!cancelled) {
          setWsStatus("error");
          setMessage({ tone: "error", text: err instanceof Error ? err.message : "Could not authorize the stream connection." });
        }
        return;
      }
      if (cancelled) return;
      setWsStatus("connecting");
      socket = new WebSocket(url);
      socket.onopen = () => setWsStatus("live");
      socket.onmessage = event => {
        try {
          const msg = JSON.parse(event.data) as Partial<LiveFrame> & { type: string };
          if (msg.type === "frame") {
            setLiveFrame({ ...msg, seq: msg.seq ?? 0 } as LiveFrame);
            if (msg.jpeg) recDrawRef.current?.(msg.jpeg);
            const events = msg.events;
            if (events && events.length) {
              const stamped = events.map(item => ({ ...item, ts: item.ts || new Date().toISOString() })).reverse();
              setLiveEvents(prev => [...stamped, ...prev].slice(0, 24));
            }
          } else if (msg.type === "status") {
            if (msg.status === "error") setWsStatus("error");
            setLiveFrame(prev => prev
              ? { ...prev, status: msg.status, error: msg.error ?? null, stale: msg.stale, source_mode: msg.source_mode }
              : { type: "status", seq: 0, status: msg.status, error: msg.error ?? null, stale: msg.stale, source_mode: msg.source_mode });
          } else if (msg.type === "error") {
            setWsStatus("error");
            setLiveFrame({ type: "error", seq: 0, status: "error", detail: msg.detail });
          }
        } catch { /* Ignore malformed frames; the next one replaces them. */ }
      };
      socket.onerror = () => setWsStatus("error");
      socket.onclose = () => setWsStatus(current => current === "error" ? "error" : "idle");
    })();
    return () => { cancelled = true; socket?.close(); };
  }, [activePage, watchId]);

  const handleUpload = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]; if (!file) return;
    setUploading(true); setMessage(null);
    try {
      const form = new FormData(); form.append("file", file);
      const uploaded = await api<VideoJob>("/api/videos/upload", { method: "POST", body: form });
      await refreshData(true); setSelectedId(uploaded.id); setActivePage("live"); setAnalysisMode("recorded");
      setMessage({ tone: "success", text: `Imported real video: ${uploaded.original_name}. Add parking-bay polygons before analysis for slot occupancy.` });
    } catch (err) { setMessage({ tone: "error", text: err instanceof Error ? err.message : "Upload failed" }); }
    finally { setUploading(false); if (fileRef.current) fileRef.current.value = ""; }
  };

  const fetchSource = async (source: Source) => {
    setBusySource(source.id); setMessage(null);
    try {
      const job = await api<VideoJob>(`/api/public-sources/${source.id}/fetch`, { method: "POST" });
      await refreshData(true); setSelectedId(job.id); setActivePage("live"); setAnalysisMode("recorded");
      setMessage({ tone: "success", text: `Fetched ${source.title} from Pexels. This is public recorded footage, not a live camera.` });
    } catch (err) { setMessage({ tone: "error", text: err instanceof Error ? err.message : "Could not fetch footage" }); }
    finally { setBusySource(""); }
  };

  const runAnalysis = async (job: VideoJob) => {
    setProcessingId(job.id); setMessage({ tone: "info", text: `Queueing analysis for ${job.original_name}…` });
    try {
      await api<VideoJob>(`/api/videos/${job.id}/process`, { method: "POST" });
      await refreshData(true); setSelectedId(job.id);
      setMessage({ tone: "success", text: "Analysis queued. Model loading may take longer on the first run while YOLO weights are downloaded." });
    } catch (err) { setMessage({ tone: "error", text: err instanceof Error ? err.message : "Could not queue analysis" }); }
    finally { setProcessingId(""); }
  };

  const saveSpace = async (event: FormEvent) => {
    event.preventDefault(); if (!selected) return;
    if (pendingPoints.length < 3) { setMessage({ tone: "error", text: "A parking-space polygon needs at least three points." }); return; }
    try {
      await api<Space>(`/api/videos/${selected.id}/spaces`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: spaceName.trim(), polygon: pendingPoints }) });
      setPendingByVideo(m => ({ ...m, [selected.id]: [] })); setSpaceName(`Bay ${String(spaces.length + 2).padStart(2, "0")}`);
      const current = await api<Space[]>(`/api/videos/${selected.id}/spaces`); setSpacesByVideo(m => ({ ...m, [selected.id]: current }));
      setMessage({ tone: "success", text: "Parking bay saved. Analyze or re-analyze the video to calculate occupancy for calibrated spaces." });
    } catch (err) { setMessage({ tone: "error", text: err instanceof Error ? err.message : "Could not save parking bay" }); }
  };

  const deleteSpace = async (space: Space) => {
    if (!selected) return;
    try {
      await api(`/api/videos/${selected.id}/spaces/${space.id}`, { method: "DELETE" });
      setSpacesByVideo(m => ({ ...m, [selected.id]: (m[selected.id] ?? []).filter(s => s.id !== space.id) }));
      setMessage({ tone: "success", text: `${space.name} deleted.` });
    } catch (err) { setMessage({ tone: "error", text: err instanceof Error ? err.message : "Could not delete parking bay" }); }
  };

  const deleteVideo = async (job: VideoJob) => {
    const label = job.source_title || job.original_name;
    if (!window.confirm(`Delete "${label}"?\n\nThis permanently removes the source video, its stored samples, bay calibration and annotated output.`)) return;
    try {
      await api(`/api/videos/${job.id}`, { method: "DELETE" });
      if (reviewId === job.id) setReviewId("");
      await refreshData(true);
      setMessage({ tone: "success", text: `Deleted ${label} and all of its stored measurements.` });
    } catch (err) { setMessage({ tone: "error", text: err instanceof Error ? err.message : "Could not delete video" }); }
  };

  const openReview = (id: string) => {
    setActivePage("dashboard");
    setReviewId(id);
    loadVideoDetail(id);
    requestAnimationFrame(() => reviewRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" }));
  };

  const focusStreamForm = () => {
    // The form only exists in live mode; retry briefly so callers that switch
    // modes in the same tick still land on it.
    const attempt = (tries: number) => {
      const element = document.getElementById("stream-form");
      if (!element) {
        if (tries > 0) setTimeout(() => attempt(tries - 1), 60);
        return;
      }
      element.scrollIntoView({ behavior: "smooth", block: "start" });
      (element.querySelector("input") as HTMLInputElement | null)?.focus();
    };
    attempt(6);
  };

  const saveSettingsPatch = async (patch: Record<string, unknown>, successText: string) => {
    try {
      const next = await api<SettingsPayload>("/api/settings", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(patch) });
      setSettingsPayload(next);
      setModelTouched(false);
      setIntTouched(false);
      setMessage({ tone: "success", text: successText });
    } catch (err) { setMessage({ tone: "error", text: err instanceof Error ? err.message : "Could not save settings" }); }
  };

  // Webhook signing secret goes through its dedicated endpoint (the settings API
  // refuses direct secret writes and never returns stored secret values).
  const webhookSecretConfigured = Boolean(settingsPayload?.settings.webhook_secret_configured);
  const saveWebhook = async () => {
    try {
      const next = await api<SettingsPayload>("/api/settings", {
        method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ webhook_url: intDraftLive.webhookUrl }),
      });
      setSettingsPayload(next);
      if (intDraftLive.webhookSecret.trim()) {
        await api("/api/integrations/webhook/secret", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action: "set", secret: intDraftLive.webhookSecret.trim() }),
        });
        patchInt({ webhookSecret: "" });
        const refreshed = await api<SettingsPayload>("/api/settings");
        setSettingsPayload(refreshed);
      }
      setIntTouched(false);
      setMessage({ tone: "success", text: "Webhook settings saved." });
    } catch (err) {
      setMessage({ tone: "error", text: err instanceof Error ? err.message : "Could not save webhook settings" });
    }
  };

  const applySessionKey = () => {
    setSessionApiKey(sessionKeyInput.trim());
    setSessionKeyActive(Boolean(sessionKeyInput.trim()));
    setSessionKeyInput("");
    setMessage(sessionKeyInput.trim()
      ? { tone: "success", text: "API key stored for this browser tab only (sessionStorage). It is cleared when the tab closes." }
      : { tone: "info", text: "Session API key cleared." });
    if (sessionKeyInput.trim()) refreshAdmin();
  };

  useEffect(() => {
    // Deferred read avoids a synchronous setState in the effect body and any
    // SSR/client hydration mismatch for the session-key indicator.
    const timer = setTimeout(() => setSessionKeyActive(Boolean(getApiKey())), 0);
    return () => clearTimeout(timer);
  }, []);

  const createStream = async (event: FormEvent) => {
    event.preventDefault();
    const body: Record<string, unknown> = {
      name: streamName.trim(),
      kind: streamKind,
      target_fps: Number(streamFps) || 6,
      lat: streamLat.trim() ? Number(streamLat) : null,
      lon: streamLon.trim() ? Number(streamLon) : null,
    };
    if (streamKind === "url") body.url = streamUrl.trim(); else body.video_id = streamVideoId;
    try {
      const created = await api<StreamRow>("/api/streams", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      await refreshStreams();
      setSelectedStreamId(created.id);
      setStreamName(""); setStreamUrl(""); setStreamLat(""); setStreamLon("");
      setMessage({ tone: "success", text: `${created.name} added. Press Watch to open the source and receive annotated frames.` });
    } catch (err) { setMessage({ tone: "error", text: err instanceof Error ? err.message : "Could not add stream" }); }
  };

  const startStream = async (stream: StreamRow) => {
    try { await api(`/api/streams/${stream.id}/start`, { method: "POST" }); await refreshStreams(); setMessage({ tone: "success", text: `${stream.name} started in the background.` }); }
    catch (err) { setMessage({ tone: "error", text: err instanceof Error ? err.message : "Could not start stream" }); }
  };
  const stopStream = async (stream: StreamRow) => {
    try { await api(`/api/streams/${stream.id}/stop`, { method: "POST" }); await refreshStreams(); setMessage({ tone: "success", text: `${stream.name} stopped.` }); }
    catch (err) { setMessage({ tone: "error", text: err instanceof Error ? err.message : "Could not stop stream" }); }
  };
  const removeStream = async (stream: StreamRow) => {
    if (!window.confirm(`Delete stream "${stream.name}"?\n\nIts calibration polygons and session history are removed.`)) return;
    try {
      await api(`/api/streams/${stream.id}`, { method: "DELETE" });
      if (watchId === stream.id) setWatchId("");
      if (selectedStreamId === stream.id) setSelectedStreamId("");
      await refreshStreams();
      setMessage({ tone: "success", text: `Deleted ${stream.name}.` });
    } catch (err) { setMessage({ tone: "error", text: err instanceof Error ? err.message : "Could not delete stream" }); }
  };
  const watchStream = (stream: StreamRow) => {
    setSelectedStreamId(stream.id);
    setWatchId(stream.id);
    setWsStatus("connecting");
    setLiveFrame(null);
    setLiveEvents([]);
  };
  const unwatchStream = () => { setWatchId(""); setLiveFrame(null); setLiveEvents([]); };

  /** Composite the incoming annotated frames into a downloadable clip. */
  const startRecording = () => {
    if (recRef.current || typeof MediaRecorder === "undefined") return;
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    recDrawRef.current = (jpeg: string) => {
      const img = new Image();
      img.onload = () => {
        if (!canvas.width) { canvas.width = img.naturalWidth; canvas.height = img.naturalHeight; }
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      };
      img.src = `data:image/jpeg;base64,${jpeg}`;
    };
    const mediaStream = canvas.captureStream(12);
    const mime = ["video/webm;codecs=vp9", "video/webm;codecs=vp8", "video/webm"]
      .find(type => typeof MediaRecorder !== "undefined" && MediaRecorder.isTypeSupported(type)) || "";
    const recorder = new MediaRecorder(mediaStream, mime ? { mimeType: mime } : undefined);
    const chunks: Blob[] = [];
    recorder.ondataavailable = event => { if (event.data.size) chunks.push(event.data); };
    recorder.onstop = () => {
      const blob = new Blob(chunks, { type: "video/webm" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `parkwise-live-${(activeStream?.name || "session").replace(/[^\w-]+/g, "-").toLowerCase()}-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, "")}.webm`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
      setMessage({ tone: "success", text: "Recorded review saved as a WebM clip (annotated frames included)." });
    };
    recorder.start(1000);
    recRef.current = { recorder, stream: mediaStream, chunks };
    setRecording(true);
    setMessage({ tone: "info", text: "Recording the annotated live view. Press “Stop & save” to finish and download the clip." });
  };

  const stopRecording = (save = true) => {
    const active = recRef.current;
    if (!active) return;
    recRef.current = null;
    recDrawRef.current = null;
    setRecording(false);
    try { active.recorder.stop(); } catch { /* already stopped */ }
    active.stream.getTracks().forEach(track => track.stop());
    if (!save) {
      active.recorder.onstop = null;
      setMessage({ tone: "info", text: "Recording discarded." });
    }
  };

  useEffect(() => () => {
    // Page unmount: release the recorder without firing a download.
    const active = recRef.current;
    if (active) {
      recRef.current = null;
      try { active.recorder.onstop = null; active.recorder.stop(); } catch { /* noop */ }
      active.stream.getTracks().forEach(track => track.stop());
    }
  }, []);

  const downloadAnnotated = async (job: VideoJob) => {
    if (!job.annotated_url) return;
    setDownloadingId(job.id);
    try {
      const base = (job.source_title || job.original_name).replace(/\.[^.]+$/, "").replace(/[^\w-]+/g, "-").toLowerCase();
      await downloadFile(job.annotated_url, `${base}-annotated.mp4`);
      setMessage({ tone: "success", text: "Annotated video downloaded." });
    } catch (err) {
      setMessage({ tone: "error", text: err instanceof Error ? err.message : "Could not download the annotated video" });
    } finally { setDownloadingId(""); }
  };

  const captureSnapshot = async (stream: StreamRow) => {
    setMessage({ tone: "info", text: "Capturing a calibration frame from the source…" });
    try {
      const result = await api<{ snapshot_url: string }>(`/api/streams/${stream.id}/snapshot`, { method: "POST" });
      setSnapshot({ id: stream.id, url: `${API}${result.snapshot_url}?t=${Date.now()}` });
      setMessage(null);
    } catch (err) { setMessage({ tone: "error", text: err instanceof Error ? err.message : "Could not capture a frame" }); }
  };
  const openStreamCalibration = async (stream: StreamRow) => {
    setSelectedStreamId(stream.id); setCalibratingId(stream.id); setStreamPending([]);
    await captureSnapshot(stream);
  };
  const putStreamSpaces = async (stream: StreamRow, next: { name: string; polygon: number[][] }[]) => {
    try {
      await api(`/api/streams/${stream.id}/spaces`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ spaces: next }) });
      await refreshStreams();
      setMessage({ tone: "success", text: `Saved ${next.length} bay polygon(s) for ${stream.name}. They apply to the next analyzed frame.` });
    } catch (err) { setMessage({ tone: "error", text: err instanceof Error ? err.message : "Could not save stream bays" }); }
  };
  const saveStreamBay = async (event: FormEvent) => {
    event.preventDefault(); if (!activeStream) return;
    if (streamPending.length < 3) { setMessage({ tone: "error", text: "A stream bay polygon needs at least three points." }); return; }
    await putStreamSpaces(activeStream, [...activeStream.spaces, { name: streamBayName.trim() || `Bay ${activeStream.spaces.length + 1}`, polygon: streamPending }]);
    setStreamPending([]);
    setStreamBayName(`Bay ${String(activeStream.spaces.length + 2).padStart(2, "0")}`);
  };

  const exportReport = () => {
    const rows = dash?.reviewed_videos ?? [];
    const header = ["video_id", "name", "completed_at", "duration_seconds", "peak_vehicles", "avg_confidence", "samples", "occupied_share_percent"];
    const lines = [
      header.join(","),
      ...rows.map(row => header.map(key => JSON.stringify((row as unknown as Record<string, string | number | null>)[key] ?? "")).join(",")),
    ];
    const url = URL.createObjectURL(new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `parkwise-report-${new Date().toISOString().slice(0, 10)}.csv`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  const testWebhook = async () => {
    setWebhookResult("Sending test event…");
    try { const result = await api<Record<string, unknown>>("/api/integrations/webhook/test", { method: "POST" }); setWebhookResult(JSON.stringify(result)); }
    catch (err) { setWebhookResult(err instanceof Error ? err.message : "Webhook test failed"); }
  };
  const changePlan = async (plan: string) => {
    try {
      const report = await api<BillingReport>("/api/billing", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ plan }) });
      setBillingReport(report);
      setMessage({ tone: "success", text: `Plan switched to ${plan}. New quota applies immediately.` });
    } catch (err) { setMessage({ tone: "error", text: err instanceof Error ? err.message : "Could not change plan" }); }
  };
  const createUser = async (event: FormEvent) => {
    event.preventDefault();
    try {
      const result = await api<{ user: UserRow; api_key: string; api_key_note: string }>("/api/users", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(newUser) });
      setPlainKey({ key: result.api_key, note: result.api_key_note });
      setNewUser({ username: "", display_name: "", role: "operator" });
      const list = await api<{ items: UserRow[] }>("/api/users"); setUsers(list.items);
      setMessage({ tone: "success", text: `User ${result.user.username} created with role ${result.user.role}.` });
    } catch (err) { setMessage({ tone: "error", text: err instanceof Error ? err.message : "Could not create user" }); }
  };
  const patchUser = async (userId: string, patch: Record<string, unknown>) => {
    try {
      await api(`/api/users/${userId}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(patch) });
      const list = await api<{ items: UserRow[] }>("/api/users"); setUsers(list.items);
    } catch (err) { setMessage({ tone: "error", text: err instanceof Error ? err.message : "Could not update user" }); }
  };
  const rotateKey = async (user: UserRow) => {
    try {
      const result = await api<{ api_key: string; api_key_note: string }>(`/api/users/${user.id}/rotate-key`, { method: "POST" });
      setPlainKey({ key: result.api_key, note: `${user.username}: ${result.api_key_note}` });
    } catch (err) { setMessage({ tone: "error", text: err instanceof Error ? err.message : "Could not rotate key" }); }
  };
  const removeUser = async (user: UserRow) => {
    if (!window.confirm(`Delete user "${user.username}"?\n\nTheir API key stops working immediately.`)) return;
    try {
      await api(`/api/users/${user.id}`, { method: "DELETE" });
      const list = await api<{ items: UserRow[] }>("/api/users"); setUsers(list.items);
      setMessage({ tone: "success", text: `Deleted ${user.username}.` });
    } catch (err) { setMessage({ tone: "error", text: err instanceof Error ? err.message : "Could not delete user" }); }
  };

  const doneSpaces = spaces.filter(s => s.state !== "unknown").length;
  const occupied = spaces.filter(s => s.state === "occupied").length;
  const free = spaces.filter(s => s.state === "free").length;
  const observed = analytics.length ? analytics[analytics.length - 1].vehicle_count : null;
  const peak = analytics.length ? Math.max(...analytics.map(p => p.vehicle_count)) : selected?.max_vehicle_count ?? null;

  const kpis = dash?.kpis ?? null;
  const charts = dash?.charts ?? null;
  const reviewJob = reviewId ? videos.find(v => v.id === reviewId) : null;
  const reviewPoints = analyticsByVideo[reviewId] ?? [];
  const reviewSpaces = spacesByVideo[reviewId] ?? [];
  const reviewLoaded = reviewId ? reviewId in spacesByVideo : false;
  const meta = pageMeta[activePage];
  const mapCenterRaw = settingsPayload?.settings.map_center;
  const mapCenter: [number, number] | null = Array.isArray(mapCenterRaw) && typeof mapCenterRaw[0] === "number" && typeof mapCenterRaw[1] === "number"
    ? [mapCenterRaw[0], mapCenterRaw[1]]
    : null;
  const locatedStreams = streams.flatMap(s => (s.lat != null && s.lon != null ? [{ id: s.id, name: s.name, lat: s.lat, lon: s.lon, status: streamRunningLabel(s) }] : []));
  const hudFrame = activeStream && watchId === activeStream.id ? liveFrame : null;

  // ---- Dashboard chart derivations (client-side cuts of activity/analytics).
  const actorActivity = (() => {
    const counts = new Map<string, number>();
    for (const item of activity) {
      const actor = item.actor || "system";
      counts.set(actor, (counts.get(actor) ?? 0) + 1);
    }
    return [...counts.entries()]
      .map(([label, value]) => ({ label, value, hint: `${label}: ${value} recorded actions` }))
      .sort((a, b) => b.value - a.value)
      .slice(0, 7);
  })();
  const actionMix = Object.entries(charts?.activity_by_action ?? {})
    .map(([action, value]) => ({ label: prettyAction(action), value, hint: `${action}: ${value}` }))
    .sort((a, b) => b.value - a.value);
  const totalActions14 = (charts?.activity_by_day ?? []).reduce((sum, day) => sum + day.total, 0);
  const confidenceBars = (dash?.reviewed_videos ?? []).slice(0, 8).reverse().map(row => ({
    label: row.completed_at ? row.completed_at.slice(5, 10) : "done",
    value: Math.round((row.avg_confidence ?? 0) * 100),
    hint: `${row.name}: ${confFmt(row.avg_confidence)} average confidence`,
  }));
  const vehicleTrendPoints = (dash?.reviewed_videos ?? []).slice(0, 12).reverse().map((row, index, all) => ({
    label: row.completed_at ? row.completed_at.slice(5, 10) : `#${all.length - index}`,
    value: row.peak_vehicles ?? 0,
  }));
  const streamHealth = (() => {
    const buckets: Record<string, number> = {};
    for (const stream of streams) {
      const key = streamRunningLabel(stream);
      buckets[key] = (buckets[key] ?? 0) + 1;
    }
    return Object.entries(buckets).map(([label, value]) => ({ label, value }));
  })();

  // ---- Live annotation overlay + stats rows.
  const bayStateByName = new Map((hudFrame?.bays ?? []).map(bay => [bay.name, bay.state]));
  const frameBayRows: { name: string; state: string; confidence: number | null }[] =
    hudFrame?.bays?.length
      ? hudFrame.bays.map(bay => ({ name: bay.name, state: bay.state, confidence: bay.confidence ?? null }))
      : (activeStream?.spaces ?? []).map(space => ({ name: space.name, state: "unknown", confidence: null }));
  // A replay-backed stream may already have a server-rendered annotated file.
  const replayAnnotatedJob = activeStream?.video_id ? videos.find(v => v.id === activeStream.video_id) ?? null : null;

  // ---- Settings derivations.
  const visibleUsers = userSearch.trim()
    ? users.filter(user =>
        user.username.toLowerCase().includes(userSearch.trim().toLowerCase()) ||
        user.display_name.toLowerCase().includes(userSearch.trim().toLowerCase()))
    : users;
  const roleSummary = (systemInfo?.security.roles ?? ["admin", "operator", "viewer"])
    .map(role => `${role} ${users.filter(user => user.role === role).length}`)
    .join(" · ");

  return (
    <main className="app-shell">
      <div className={`sidebar-backdrop ${mobileNav ? "visible" : ""}`} onClick={() => setMobileNav(false)} />
      <aside className={`sidebar ${mobileNav ? "mobile-open" : ""}`}>
        <div className="brand-row"><div className="brand-mark"><span>P</span><i /></div><div className="brand-copy"><strong>ParkWise <b>AI</b></strong><span>PARKING INTELLIGENCE</span></div><button className="icon-btn sidebar-close" onClick={() => setMobileNav(false)} aria-label="Close navigation"><X size={17} /></button></div>
        <div className="workspace-pill"><div className="workspace-avatar"><Building2 size={16} /></div><div><strong>Local workspace</strong><span>Single facility · Pilot</span></div><ChevronDown size={15} /></div>
        <nav className="main-nav" aria-label="Main navigation">
          {navItems.map((item, index) => (
            <div key={item.id}>
              {item.section && <div className={`nav-section ${index ? "spaced" : ""}`}>{item.section}</div>}
              <button data-nav={item.id} className={`nav-item ${activePage === item.id ? "active" : ""}`} onClick={() => { setActivePage(item.id); setMobileNav(false); setMessage(null); }}>
                <item.icon size={17} /><span>{item.label}</span>
                {item.id === "dashboard" && failedVideos.length > 0 && <b className="nav-count">{failedVideos.length}</b>}
                {activePage === item.id && <span className="nav-active-dot" />}
              </button>
            </div>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="edge-status"><div className="edge-status-top"><span className={`status-dot ${apiStatus === "online" ? "online" : apiStatus === "offline" ? "offline" : ""}`} /><strong>API connection</strong><span className="edge-status-value">{apiStatus === "online" ? "Connected" : apiStatus === "offline" ? "Offline" : "Checking"}</span></div><div className="edge-status-desc">{apiStatus === "online" ? "Measurements persist to the configured database." : apiStatus === "offline" ? "Start the FastAPI service to load real records." : "Checking API health…"}</div></div>
          <div className="profile-row"><div className="profile-avatar">PW</div><div className="profile-text"><strong>Operator</strong><span>Local administrator</span></div><button className="icon-btn" title="Settings" onClick={() => { setActivePage("settings"); setMobileNav(false); }}><SlidersHorizontal size={16} /></button></div>
          <div className="side-footer">PARKWISE AI <span>v2.0.0 · PILOT</span></div>
        </div>
      </aside>

      <section className="main-content">
        <header className="topbar">
          <div className="topbar-left"><button className="icon-btn mobile-menu" aria-label="Open navigation" onClick={() => setMobileNav(true)}><Menu size={19} /></button><div className="breadcrumb"><span>Workspace</span><b>/</b><strong>{activeTab}</strong></div></div>
          <div className="topbar-actions">
            <div className={`connection-chip ${apiStatus}`}><span className="status-dot" />{apiStatus === "online" ? "API connected" : apiStatus === "offline" ? "API offline" : "Connecting"}</div>
            <button className="icon-btn theme-toggle" aria-label={theme === "light" ? "Switch to dark theme" : "Switch to light theme"} title={theme === "light" ? "Switch to dark theme" : "Switch to light theme"} onClick={toggleTheme} data-theme-toggle>{theme === "light" ? <Moon size={16} /> : <Sun size={16} />}</button>
            <button className="icon-btn" aria-label="Refresh data" onClick={() => refreshData()}><RefreshCw size={16} /></button>
            <div className="topbar-date"><CalendarDays size={14} /><span>{new Date().toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}</span></div>
            <div className="operator-mini"><div className="operator-mini-avatar">PW</div><div><strong>Operator</strong><span>Administrator</span></div></div>
          </div>
        </header>

        <div className="page-content">
          <div className="page-heading">
            <div><div className="eyebrow"><span className="eyebrow-line" />{meta.eyebrow}</div><h1>{meta.title}</h1><p>{meta.subtitle}</p></div>
            <div className="heading-buttons">
              {activePage === "dashboard" && <>
                <button className="btn btn-secondary" onClick={() => fileRef.current?.click()}><HardDriveUpload size={15} /> Import video</button>
                <button className="btn btn-primary" onClick={() => { setActivePage("live"); setAnalysisMode("live"); }}><RadioTower size={16} /> Open Live Analysis</button>
              </>}
              {activePage === "live" && <>
                <button className="btn btn-secondary" onClick={() => { setAnalysisMode("recorded"); setTimeout(() => fileRef.current?.click(), 0); }}><HardDriveUpload size={15} /> Import video</button>
                <button className="btn btn-primary" onClick={() => { setAnalysisMode("live"); focusStreamForm(); }}><Plus size={16} /> Add live source</button>
              </>}
              {activePage === "settings" && <a className="btn btn-secondary" href={`${API}/docs`} target="_blank" rel="noreferrer"><ArrowRight size={15} /> API documentation</a>}
            </div>
          </div>

          {message && <div className={`notice ${message.tone}`}><span>{message.tone === "success" ? <Check size={16} /> : message.tone === "error" ? <AlertTriangle size={16} /> : <Activity size={16} />}</span><div>{message.text}</div><button className="notice-close" onClick={() => setMessage(null)} aria-label="Dismiss message"><X size={14} /></button></div>}

          {/* ---------------------------------------------------- DASHBOARD */}
          {activePage === "dashboard" && <>
            <div className="live-banner">
              <div className="banner-icon"><Activity size={18} /></div>
              <div className="banner-copy">
                <strong>{summary?.has_data ? "Measured analytics from reviewed videos" : "Your analytics workspace is ready"}</strong>
                <span>{summary?.has_data ? "Every number below comes from completed analyses of imported footage — open a reviewed video to inspect its annotations." : "No video has been analyzed yet. Import a clip or fetch a public sample to generate real measurements."}</span>
              </div>
              <span className={`banner-status ${summary?.has_data ? "ok" : "waiting"}`}><span className="status-dot" />{summary?.has_data ? "Data available" : "Awaiting first run"}</span>
            </div>

            <div className="metric-grid dash-metrics">
              <MetricCard title="Analyzed hours" value={`${(kpis?.analyzed_hours ?? 0).toFixed(1)} h`} detail={`${fmtNum(kpis?.videos_completed)} completed videos`} icon={Clock} accent="violet" mini={<Sparkline values={(charts?.activity_by_day ?? []).map(d => d.total)} />} />
              <MetricCard title="Peak vehicles observed" value={fmtNum(kpis?.peak_vehicles ?? summary?.peak_vehicles_observed)} detail="Highest detector count in a sampled frame" icon={Video} accent="blue" mini={<Sparkline values={analytics.slice(-16).map(p => p.vehicle_count)} tone="blue" />} />
              <MetricCard title="Bay utilisation" value={kpis?.utilisation_percent == null ? "—" : `${kpis.utilisation_percent}%`} detail="Occupied share of measured bay samples" icon={Gauge} accent="green" mini={<div className="mini-ring"><span>{summary?.occupancy_percent == null ? "—" : `${summary.occupancy_percent}%`}</span></div>} />
              <MetricCard title="Calibrated bays" value={fmtNum(kpis?.bays_configured)} detail={summary?.configured_spaces ? `${fmtNum(summary.occupied_spaces)} occupied · ${fmtNum(summary.free_spaces)} free latest` : "Configure polygons to measure bays"} icon={Layers3} accent="amber" mini={<Sparkline values={(charts?.occupancy_trend ?? []).map(t => t.percent)} tone="green" />} />
              <MetricCard title="Videos this month" value={fmtNum(kpis?.videos_this_month)} detail={`${fmtNum(kpis?.videos_total)} total · ${fmtNum(kpis?.videos_processing)} in progress`} icon={FileVideo} accent="violet" mini={<Sparkline values={videos.slice(0, 8).reverse().map(v => v.progress_percent)} tone="amber" />} />
              <MetricCard title="Detections logged" value={fmtNum(kpis?.detections_logged)} detail={`${kpis?.storage_gb ?? 0} GB stored · ${fmtNum(kpis?.streams_live)}/${fmtNum(kpis?.streams_total)} streams live`} icon={Database} accent="blue" mini={<Sparkline values={analytics.slice(-16).map(p => p.tracked_vehicle_count)} tone="green" />} />
            </div>

            <div className="content-grid dash-charts">
              <ChartCard eyebrow="ACTIVITY" title="Daily actions (14 days)"
                action={<span className="muted-count">{fmtNum(totalActions14)} actions</span>}>
                <BarChart data={(charts?.activity_by_day ?? []).map(day => ({
                  label: day.date.slice(5),
                  value: day.total,
                  hint: `${day.date}: ${Object.entries(day.actions).map(([action, count]) => `${action} ${count}`).join(", ") || "no actions"}`,
                }))} ariaLabel="Activity action counts per day over the last 14 days" />
              </ChartCard>
              <ChartCard eyebrow="PIPELINE" title="Video status breakdown">
                <Donut ariaLabel="Video jobs by status" centerValue={String(kpis?.videos_total ?? 0)} centerLabel="videos"
                  slices={(charts?.status_breakdown ?? []).map(item => ({ label: statusLabel(item.status), value: item.count }))} />
              </ChartCard>
              <ChartCard eyebrow="OCCUPANCY" title="Bay state samples">
                <Donut ariaLabel="Occupancy sample distribution across bay states" centerValue={kpis?.utilisation_percent == null ? "—" : `${kpis.utilisation_percent}%`} centerLabel="utilised"
                  slices={(charts?.state_mix ?? []).map(item => ({ label: item.state, value: item.samples, tone: item.state === "occupied" ? 2 : item.state === "free" ? 1 : 5 }))} />
              </ChartCard>
              <ChartCard eyebrow="USERS" title="Activity by user"
                action={<span className="muted-count">{actorActivity.length} actors</span>}>
                <HBarChart items={actorActivity} ariaLabel="Recorded actions grouped by acting user" seriesIndex={4} />
              </ChartCard>
              <ChartCard eyebrow="ACTION MIX" title="Action types share"
                action={<span className="muted-count">last 14 days</span>}>
                <ShareBar items={actionMix} ariaLabel="Share of recorded action types over the last 14 days" />
              </ChartCard>
              <ChartCard eyebrow="QUALITY" title="Confidence by analysis"
                action={<span className="muted-count">avg confidence %</span>}>
                <BarChart data={confidenceBars} ariaLabel="Average model confidence per completed analysis" seriesIndex={3} />
              </ChartCard>
              <ChartCard eyebrow="DETECTIONS" title="Vehicles per analysis"
                action={<span className="muted-count">peak per run</span>}>
                <TrendChart ariaLabel="Peak vehicles observed per completed analysis" unit="" points={vehicleTrendPoints} />
              </ChartCard>
              <ChartCard eyebrow="SOURCES" title="Stream health"
                action={<span className="muted-count">{fmtNum(streams.length)} configured</span>}>
                <Donut ariaLabel="Configured streams grouped by runtime status" centerValue={String(kpis?.streams_live ?? 0)} centerLabel="live now"
                  slices={streamHealth.map(item => ({ label: item.label, value: item.value, tone: item.label === "Live" ? 1 : item.label === "Error" || item.label === "Blocked" ? 4 : item.label === "Reconnecting" || item.label === "Starting" ? 3 : 5 }))} />
              </ChartCard>
            </div>

            <section className="panel reviewed-panel" ref={reviewRef}>
              <PanelHeader eyebrow="REVIEWED VIDEOS" title="Reviewed videos & annotations"
                action={<div className="header-actions"><span className="muted-count">{(dash?.reviewed_videos ?? []).length} reviewed</span><button className="text-action" onClick={exportReport}><Download size={14} /> Export CSV</button></div>} />
              {dash?.reviewed_videos.length
                ? <ReviewedTable rows={dash.reviewed_videos} openId={reviewId} onOpen={openReview} />
                : <EmptyTable title="No reviewed videos yet" description="Completed analyses appear here with occupancy annotations you can open, chart and export." action={() => setActivePage("live")} actionLabel="Open Live Analysis" />}

              {reviewJob && (
                <div className="review-detail">
                  <div className="review-detail-head">
                    <div>
                      <span className={`status-pill ${statusClass(reviewJob.status)}`}><span className="status-dot" />{statusLabel(reviewJob.status)}</span>
                      <h3>{reviewJob.source_title || reviewJob.original_name}</h3>
                      <p>{fmtDuration(reviewJob.duration_seconds)} · {reviewJob.width && reviewJob.height ? `${reviewJob.width} × ${reviewJob.height}` : "resolution n/a"} · {reviewJob.model_name || "model not recorded"}</p>
                    </div>
                    <div className="review-detail-actions">
                      {reviewJob.annotated_url && <a className="btn btn-primary small" href={`${API}${reviewJob.annotated_url}`} target="_blank" rel="noreferrer">Annotated video <ArrowRight size={14} /></a>}
                      <button className="btn btn-ghost small" onClick={() => setReviewId("")}>Close</button>
                    </div>
                  </div>
                  {!reviewLoaded ? (
                    <div className="list-empty"><LoaderCircle className="spin" size={22} /><strong>Loading annotations…</strong></div>
                  ) : (
                    <>
                      <div className="review-detail-grid">
                        {reviewJob.preview_url && <img className="detail-preview" src={`${API}${reviewJob.preview_url}`} alt={`Preview frame from ${reviewJob.original_name}`} />}
                        <div className="detail-facts">
                          <Fact label="Peak vehicles" value={fmtNum(reviewJob.max_vehicle_count)} />
                          <Fact label="Average confidence" value={confFmt(reviewJob.avg_confidence)} />
                          <Fact label="Stored samples" value={fmtNum(reviewPoints.length)} />
                          <Fact label="Calibrated bays" value={fmtNum(reviewSpaces.length)} />
                          <Fact label="Occupancy records" value={fmtNum((occupancyByVideo[reviewId] ?? []).length)} />
                          {reviewJob.source_page && <a className="source-credit" href={reviewJob.source_page} target="_blank" rel="noreferrer">Creator source and license ↗</a>}
                        </div>
                      </div>
                      <div className="review-charts">
                        <section className="sub-panel"><PanelHeader eyebrow="DETECTIONS" title="Vehicles by sampled timestamp" /><DetectionChart values={reviewPoints} /></section>
                        <section className="sub-panel">
                          <PanelHeader eyebrow="OCCUPANCY" title="Measured bay states" action={<span className="muted-count">{(occupancyByVideo[reviewId] ?? []).length} records</span>} />
                          {occupancyRowsFor(occupancyByVideo[reviewId] ?? []).length ? (
                            <div className="table-scroll">
                              <table className="data-table">
                                <thead><tr><th>Bay</th><th>Samples</th><th>Occupied share</th><th>Transitions</th><th>Latest</th></tr></thead>
                                <tbody>{occupancyRowsFor(occupancyByVideo[reviewId] ?? []).map(row => (
                                  <tr key={row.name}><td><strong>{row.name}</strong></td><td>{fmtNum(row.samples)}</td><td>{row.occupiedShare}%</td><td>{row.transitions}</td><td><span className={`state-tag ${row.lastState}`}>{row.lastState}</span></td></tr>
                                ))}</tbody>
                              </table>
                            </div>
                          ) : <div className="list-empty"><Layers3 size={22} /><strong>No bay occupancy history</strong><span>Calibrate polygons on this video in Live Analysis and re-analyze it.</span></div>}
                        </section>
                        <section className="sub-panel">
                          <PanelHeader eyebrow="SAMPLES" title="Latest observations" action={<span className="muted-count">latest 10</span>} />
                          {reviewPoints.length ? (
                            <div className="table-scroll">
                              <table className="data-table">
                                <thead><tr><th>Time</th><th>Frame</th><th>Vehicles</th><th>Tracked</th><th>Confidence</th></tr></thead>
                                <tbody>{reviewPoints.slice(-10).reverse().map(point => (
                                  <tr key={`${point.frame_number}-${point.timestamp_seconds}`}><td className="mono">{fmtTime(point.timestamp_seconds)}</td><td>{fmtNum(point.frame_number)}</td><td><strong>{point.vehicle_count}</strong></td><td>{point.tracked_vehicle_count}</td><td>{confFmt(point.mean_confidence)}</td></tr>
                                ))}</tbody>
                              </table>
                            </div>
                          ) : <div className="list-empty"><Activity size={22} /><strong>No stored samples</strong></div>}
                        </section>
                      </div>
                    </>
                  )}
                </div>
              )}
            </section>

            <p className="honesty-note"><ShieldCheck size={14} /> All values are derived from stored inference results. Public sample clips are recorded footage and must not be treated as real-time facility availability.</p>
          </>}

          {/* ----------------------------------------------------- LIVE ANALYSIS */}
          {activePage === "live" && <>
            <div className="mode-switch" role="tablist" aria-label="Review mode">
              <button role="tab" aria-selected={analysisMode === "live"} className={analysisMode === "live" ? "active" : ""} onClick={() => setAnalysisMode("live")}>
                <RadioTower size={15} /> Live video review
              </button>
              <button role="tab" aria-selected={analysisMode === "recorded"} className={analysisMode === "recorded" ? "active" : ""} onClick={() => { if (recording) stopRecording(); setAnalysisMode("recorded"); }}>
                <FileVideo size={15} /> Recorded video review
              </button>
            </div>

            {analysisMode === "live" && <>
              <div className="live-banner">
                <div className="banner-icon"><RadioTower size={18} /></div>
                <div className="banner-copy">
                  <strong>{streams.length ? `${streams.filter(s => s.running || s.status === "live").length} of ${streams.length} sources delivering frames` : "Attach a camera or replay source"}</strong>
                  <span>Paste a camera URL or pick a replay clip on the left — annotated frames stream on the right with green flickering boxes for free bays and red boxes for occupied ones. Findings, bay states and frame metrics sit directly below.</span>
                </div>
                <span className={`banner-status ${streams.length ? "ok" : "waiting"}`}><span className="status-dot" />{streams.length ? "Configured" : "No streams yet"}</span>
              </div>

              <div className="live-grid">
              <section className="panel streams-panel" id="stream-form">
                <PanelHeader eyebrow="CAMERA & REPLAY SOURCES" title="Streams" action={<span className="muted-count">{streams.length} configured</span>} />
                <form className="stream-form" onSubmit={createStream}>
                  <div className="field-group"><label htmlFor="stream-name">NAME</label><input id="stream-name" value={streamName} onChange={e => setStreamName(e.target.value)} maxLength={80} required placeholder="North gate camera" /></div>
                  <div className="field-group">
                    <label>SOURCE TYPE</label>
                    <div className="segmented" role="tablist" aria-label="Stream source type">
                      <button type="button" className={streamKind === "url" ? "active" : ""} onClick={() => setStreamKind("url")}>Camera URL</button>
                      <button type="button" className={streamKind === "video" ? "active" : ""} onClick={() => setStreamKind("video")}>Replay video</button>
                    </div>
                  </div>
                  {streamKind === "url" ? (
                    <div className="field-group">
                      <label htmlFor="stream-url">STREAM URL</label>
                      <input id="stream-url" value={streamUrl} onChange={e => setStreamUrl(e.target.value)} required placeholder="rtsp://192.168.1.10:554/stream" />
                      <small className="field-hint">RTSP/HTTP camera URL. Embedded credentials (user:pass@) are rejected by the API — cameras must allow anonymous LAN access or use an authenticated proxy.</small>
                    </div>
                  ) : (
                    <div className="field-group"><label htmlFor="stream-video">UPLOADED VIDEO</label><select id="stream-video" value={streamVideoId} onChange={e => setStreamVideoId(e.target.value)} required><option value="">Select a video…</option>{videos.map(job => <option key={job.id} value={job.id}>{job.source_title || job.original_name}</option>)}</select></div>
                  )}
                  <div className="stream-form-row">
                    <div className="field-group"><label htmlFor="stream-fps">TARGET FPS</label><input id="stream-fps" type="number" min={1} max={15} value={streamFps} onChange={e => setStreamFps(e.target.value)} /></div>
                    <div className="field-group"><label htmlFor="stream-lat">LATITUDE</label><input id="stream-lat" type="number" step="0.0001" value={streamLat} onChange={e => setStreamLat(e.target.value)} placeholder="41.9028" /></div>
                    <div className="field-group"><label htmlFor="stream-lon">LONGITUDE</label><input id="stream-lon" type="number" step="0.0001" value={streamLon} onChange={e => setStreamLon(e.target.value)} placeholder="12.4964" /></div>
                  </div>
                  <button className="btn btn-primary full-width" type="submit"><Plus size={15} /> Add stream</button>
                </form>

                <div className="stream-list">
                  {streams.length ? streams.map(stream => (
                    <div className={`stream-row ${activeStream?.id === stream.id ? "selected" : ""}`} key={stream.id}>
                      <div className="stream-row-head" onClick={() => setSelectedStreamId(stream.id)}>
                        <strong>{stream.name}</strong>
                        <span className={`status-pill ${streamStatusTone(stream)}`}><span className="status-dot" />{streamRunningLabel(stream)}</span>
                      </div>
                      <div className="stream-row-meta" onClick={() => setSelectedStreamId(stream.id)}>
                        {stream.kind === "url" ? (stream.url || "Camera URL") : (stream.video_name || "Replay video")} · {stream.target_fps} fps · {stream.space_count} bays{stream.frames_delivered ? ` · ${stream.frames_delivered.toLocaleString()} frames` : ""}
                      </div>
                      {stream.last_error && <div className="stream-row-error"><AlertTriangle size={13} /><span>{stream.last_error}</span></div>}
                      <div className="stream-row-actions" onClick={e => e.stopPropagation()}>
                        <button className={`icon-btn ${watchId === stream.id ? "run-icon" : ""}`} title={watchId === stream.id ? "Watching" : "Watch live frames"} onClick={() => watchStream(stream)}><Play size={14} /></button>
                        <button className="icon-btn" title="Calibrate bays on a captured frame" onClick={() => openStreamCalibration(stream)}><Layers3 size={14} /></button>
                        <button className="icon-btn" title={stream.running ? "Stop the background session" : "Start a background session"} disabled={stream.running && watchId === stream.id} onClick={() => stream.running ? stopStream(stream) : startStream(stream)}>{stream.running ? <Square size={13} /> : <Play size={14} />}</button>
                        <button className="icon-btn danger-icon" title="Delete stream" onClick={() => removeStream(stream)}><Trash2 size={14} /></button>
                      </div>
                    </div>
                  )) : (
                    <div className="list-empty"><RadioTower size={25} /><strong>No streams configured</strong><span>Add an RTSP/HTTP camera URL or pick an uploaded video as a replay source. Calibration bays and events are per stream.</span></div>
                  )}
                </div>
              </section>

              <section className="panel viewer-panel">
                <PanelHeader eyebrow="REAL-TIME ANNOTATIONS" title={activeStream ? activeStream.name : "Viewer"}
                  action={<span className={`status-pill ${wsStatus === "live" ? "success" : wsStatus === "error" ? "danger" : "neutral"}`}><span className="status-dot" />{wsStatus === "live" ? "Streaming" : wsStatus === "connecting" ? "Connecting" : wsStatus === "error" ? "Interrupted" : "Idle"}</span>} />
                {activeStream ? (
                  <>
                    <div className="viewer-frame">
                      {hudFrame?.jpeg ? (
                        <>
                          <img src={`data:image/jpeg;base64,${hudFrame.jpeg}`} alt={`Annotated frame from ${activeStream.name}`} />
                          {activeStream.spaces.length > 0 && (
                            <svg className="bay-overlay" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
                              {activeStream.spaces.map((space, index) => (
                                <polygon
                                  key={`${space.name}-${index}`}
                                  className={`bay-box ${bayStateByName.get(space.name) || "unknown"}`}
                                  points={space.polygon.map(point => `${point[0] * 100},${point[1] * 100}`).join(" ")}
                                />
                              ))}
                            </svg>
                          )}
                          <div className={`viewer-source-badge ${activeStream.kind === "video" ? "replay" : "live"}`}>
                            {activeStream.kind === "video" ? "REPLAY · RECORDED VIDEO" : "LIVE CAMERA"}
                          </div>
                          {(hudFrame.stale || (hudFrame.last_frame_age_ms != null && hudFrame.last_frame_age_ms > 10000)) && (
                            <div className="viewer-stale-banner">
                              <AlertTriangle size={13} /> Stale — last frame {hudFrame.last_frame_age_ms != null ? `${(hudFrame.last_frame_age_ms / 1000).toFixed(1)}s` : "some"} ago
                            </div>
                          )}
                          <div className="viewer-hud">
                            <span>Vehicles<strong>{hudFrame.vehicle_count ?? "—"}</strong></span>
                            <span>Bays<strong>{hudFrame.total ? `${hudFrame.occupied ?? 0}/${hudFrame.total}` : "—"}</strong></span>
                            <span>Inference<strong>{hudFrame.inference_fps ? `${hudFrame.inference_fps.toFixed(1)} fps` : "—"}</strong></span>
                            <span>Latency<strong>{hudFrame.latency_ms != null ? `${hudFrame.latency_ms} ms` : "—"}</strong></span>
                          </div>
                        </>
                      ) : (
                        <div className="viewer-placeholder">
                          <Wifi size={30} />
                          <strong>{hudFrame ? (wsStatus === "connecting" ? "Opening the source…" : wsStatus === "error" ? "Stream interrupted" : "Waiting for frames…") : "Press Watch to open this source"}</strong>
                          <span>The server connects to the camera URL or replay file, runs detection with bay tracking, and streams annotated frames here — findings, bay states and metrics follow below.</span>
                          {hudFrame?.detail ? <em>{hudFrame.detail}</em> : null}
                        </div>
                      )}
                    </div>
                    <div className="viewer-actions">
                      {watchId === activeStream.id ? (
                        <button className="btn btn-secondary small" onClick={unwatchStream}><Square size={13} /> Stop watching</button>
                      ) : (
                        <button className="btn btn-primary small" onClick={() => watchStream(activeStream)}><Play size={14} /> Watch</button>
                      )}
                      <button className="btn btn-ghost small" onClick={() => openStreamCalibration(activeStream)}><Layers3 size={14} /> Re-annotate bays</button>
                      {recording ? (
                        <button className="btn btn-secondary small record-btn recording" onClick={() => stopRecording()}><span className="rec-dot" /> Stop &amp; save</button>
                      ) : (
                        <button className="btn btn-ghost small record-btn" disabled={watchId !== activeStream.id || !hudFrame?.jpeg} onClick={startRecording} title="Record the annotated live view, then download it as a clip"><span className="rec-dot" /> Record &amp; download</button>
                      )}
                      {replayAnnotatedJob?.annotated_url && (
                        <button className="btn btn-ghost small" disabled={downloadingId === replayAnnotatedJob.id} onClick={() => downloadAnnotated(replayAnnotatedJob)}>
                          {downloadingId === replayAnnotatedJob.id ? <LoaderCircle className="spin" size={13} /> : <Download size={13} />} Annotated video
                        </button>
                      )}
                      <button className="btn btn-ghost small" disabled={!activeStream.running} onClick={() => stopStream(activeStream)}><Square size={13} /> Stop session</button>
                      <span className="viewer-model">{serverConfig?.model || "model unknown"} · {serverConfig?.device || "?"}</span>
                    </div>
                  </>
                ) : (
                  <div className="viewer-placeholder tall"><Video size={30} /><strong>No stream selected</strong><span>Add a camera URL or replay source on the left, then press Watch to stream annotated frames in real time.</span></div>
                )}
              </section>
            </div>

            {/* Findings, bay states and metrics for the current session. */}
            <div className="live-stats-row">
              <section className="panel">
                <PanelHeader eyebrow="STREAMING NOW" title="Real-time findings"
                  action={<span className="muted-count">{liveEvents.length} recent</span>} />
                <div className="events-ticker standalone">
                  {liveEvents.length ? liveEvents.slice(0, 10).map((event, index) => (
                    <div className={`event-mini ${event.type.includes("overcrowd") ? "warn" : ""}`} key={`${event.type}-${index}`}>
                      <span className="event-mini-type">{event.type.replace(/_/g, " ")}</span>
                      <span>{event.bay ? `${event.bay} · ` : ""}{event.direction || (event.occupied != null ? `${event.occupied}/${event.total} occupied` : "")}</span>
                      <small>{event.ts ? new Date(event.ts).toLocaleTimeString() : ""}</small>
                    </div>
                  )) : <div className="event-mini muted"><span>Line crossings, overcrowding and bay transitions stream here while you watch.</span></div>}
                </div>
              </section>
              <section className="panel">
                <PanelHeader eyebrow="SPACE NUMBER" title="Bay states"
                  action={<span className="muted-count">{hudFrame?.occupied ?? 0}/{hudFrame?.total ?? activeStream?.space_count ?? 0} occupied</span>} />
                {frameBayRows.length ? (
                  <div className="table-scroll">
                    <table className="data-table">
                      <thead><tr><th>Bay</th><th>State</th><th>Confidence</th></tr></thead>
                      <tbody>{frameBayRows.map((bay, index) => (
                        <tr key={`${bay.name}-${index}`}>
                          <td><strong>{bay.name}</strong></td>
                          <td><span className={`state-tag ${bay.state}`}>{bay.state}</span></td>
                          <td>{bay.confidence != null ? confFmt(bay.confidence) : "—"}</td>
                        </tr>
                      ))}</tbody>
                    </table>
                  </div>
                ) : (
                  <div className="list-empty"><Layers3 size={24} /><strong>No bays calibrated</strong><span>Press “Re-annotate bays” on the viewer to draw polygons — states appear per frame.</span></div>
                )}
              </section>
              <section className="panel">
                <PanelHeader eyebrow="LIVE METRICS" title="Frame metrics"
                  action={<span className={`status-pill ${wsStatus === "live" ? "success" : wsStatus === "error" ? "danger" : "neutral"}`}><span className="status-dot" />{wsStatus === "live" ? "Streaming" : wsStatus === "error" ? "Interrupted" : "Idle"}</span>} />
                <div className="live-metrics">
                  <div className="live-metric"><span>Vehicles</span><strong>{hudFrame?.vehicle_count ?? "—"}</strong></div>
                  <div className="live-metric"><span>Tracked</span><strong>{hudFrame?.tracked ?? "—"}</strong></div>
                  <div className="live-metric"><span>Bays occupied</span><strong>{hudFrame?.total ? `${hudFrame.occupied ?? 0}/${hudFrame.total}` : "—"}</strong></div>
                  <div className="live-metric"><span>Inference</span><strong>{hudFrame?.inference_fps ? `${hudFrame.inference_fps.toFixed(1)} fps` : "—"}</strong></div>
                  <div className="live-metric"><span>Latency</span><strong>{hudFrame?.latency_ms != null ? `${hudFrame.latency_ms} ms` : "—"}</strong></div>
                  <div className="live-metric"><span>Confidence</span><strong>{confFmt(hudFrame?.mean_confidence ?? null)}</strong></div>
                  <div className="live-metric wide"><span>Model</span><strong>{hudFrame?.model || serverConfig?.model || "—"}</strong></div>
                  <div className="live-metric wide"><span>Source</span><strong>{activeStream ? (activeStream.kind === "video" ? "Replay clip" : "Live camera") : "—"}</strong></div>
                </div>
              </section>
            </div>

            {activeStream && calibratingId === activeStream.id && (
              <section className="panel stream-calib-panel">
                <PanelHeader eyebrow="LIVE CALIBRATION" title={`Calibrate bays · ${activeStream.name}`}
                  action={<div className="header-actions"><button className="btn btn-secondary small" onClick={() => captureSnapshot(activeStream)}><RefreshCw size={14} /> Capture frame</button><button className="icon-btn" title="Close calibration" onClick={() => setCalibratingId("")}><X size={15} /></button></div>} />
                <p className="panel-intro">Click at least three points around the inside of each bay on a captured frame, then save. Bay states are computed on every streamed frame from vehicle-centre matches inside these polygons.</p>
                <div className="calibration-layout">
                  <section className="panel calibration-image-panel">
                    <PanelHeader eyebrow="CLICK TO DRAW" title="Stream polygon editor" action={<span className="coordinate-chip">{streamPending.length} points</span>} />
                    {snapshot && snapshot.id === activeStream.id ? (
                      <div className="canvas-wrap">
                        <CalibrationCanvas imageSrc={snapshot.url} spaces={activeStream.spaces} pending={streamPending} onAddPoint={point => addPolygonPoint(point, streamPending, next => setStreamPending(next))} />
                        <div className="canvas-guide"><span><i className="legend-dot red-dot" />Occupied</span><span><i className="legend-dot green-dot" />Free</span><span><i className="legend-dot grey-dot" />Unknown</span></div>
                      </div>
                    ) : (
                      <div className="calibration-empty"><Layers3 size={28} /><strong>No calibration frame captured</strong><span>Press “Capture frame” to grab a still image directly from the camera URL or replay file.</span></div>
                    )}
                    <div className="draw-controls">
                      <form onSubmit={saveStreamBay} className="space-form">
                        <div className="field-group"><label htmlFor="stream-bay-name">BAY LABEL</label><input id="stream-bay-name" value={streamBayName} onChange={e => setStreamBayName(e.target.value)} maxLength={80} required placeholder="e.g. A-01" /></div>
                        <div className="draw-actions">
                          <button type="button" className="btn btn-ghost small" onClick={() => setStreamPending(old => old.slice(0, -1))} disabled={!streamPending.length}>Undo point</button>
                          <button type="button" className="btn btn-ghost small" onClick={() => setStreamPending([])} disabled={!streamPending.length}>Clear</button>
                          <button type="submit" className="btn btn-primary small" disabled={streamPending.length < 3}><Plus size={14} /> Save bay</button>
                        </div>
                      </form>
                      <p>Saved bays apply to the next streamed frame. Live occupancy needs no re-analysis — new polygons take effect immediately.</p>
                    </div>
                  </section>
                  <section className="panel calibrated-list-panel">
                    <PanelHeader eyebrow="STREAM GEOMETRY" title="Configured bays" action={<span className="muted-count">{activeStream.space_count} total</span>} />
                    {activeStream.space_count ? (
                      <div className="space-list">
                        {activeStream.spaces.map((bay, index) => (
                          <div className="space-row" key={`${bay.name}-${index}`}>
                            <span className="space-state-dot unknown" />
                            <div className="space-row-main"><strong>{bay.name}</strong><span>{bay.polygon.length} polygon points · live</span></div>
                            <span className="state-tag unknown">live</span>
                            <button className="icon-btn danger-icon" title={`Remove ${bay.name}`} onClick={() => putStreamSpaces(activeStream, activeStream.spaces.filter((_, i) => i !== index))}><Trash2 size={14} /></button>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="list-empty"><Layers3 size={25} /><strong>No bays on this stream</strong><span>Draw polygons on a captured frame to enable per-bay occupancy in live frames.</span></div>
                    )}
                    <div className="calibration-caveat"><AlertTriangle size={15} /><span>Bay states are estimates from detector quality and camera angle. “Free” is not a guaranteed space.</span></div>
                  </section>
                </div>
              </section>
            )}
            </>}

            {analysisMode === "recorded" && <>
            <div className="page-subheading" id="import-anchor">
              <div className="eyebrow"><span className="eyebrow-line" />INDEPENDENT VIDEO ANALYSIS</div>
              <h2>Uploaded & public footage</h2>
              <p>Work with recorded clips separately from live streams: import your own footage or fetch a public sample, then run inference and review results.</p>
            </div>

            <div className="lab-grid">
              <section className="panel upload-panel">
                <PanelHeader eyebrow="LOCAL FOOTAGE" title="Import a video" />
                <div className="upload-drop" onClick={() => fileRef.current?.click()} role="button" tabIndex={0} onKeyDown={e => { if (e.key === "Enter" || e.key === " ") fileRef.current?.click(); }}>
                  <div className="upload-icon">{uploading ? <LoaderCircle className="spin" size={23} /> : <HardDriveUpload size={24} />}</div>
                  <strong>{uploading ? "Uploading and inspecting…" : "Choose a parking video"}</strong>
                  <span>MP4, MOV, M4V, AVI, MKV or WebM · up to server limit</span>
                  <span className="upload-browse">Browse files <ArrowRight size={13} /></span>
                </div>
                <div className="upload-privacy"><ShieldCheck size={15} /><span>Files are processed by this server and stored in its data directory. Do not upload footage you do not have permission to process.</span></div>
              </section>
              <section className="panel sources-panel">
                <PanelHeader eyebrow="PUBLIC SAMPLE FOOTAGE" title="Fetch real parking clips" />
                <p className="panel-intro">These are actual creator-published Pexels video files, not generated imagery or live cameras. Fetching downloads the selected MP4 to your server for analysis.</p>
                <div className="source-list">
                  {sources.map(source => (
                    <div className="source-item" key={source.id}>
                      <div className="source-thumb"><Video size={20} /><span>MP4</span></div>
                      <div className="source-details"><strong>{source.title}</strong><span>By {source.creator} · {source.resolution} · {fmtDuration(source.duration_seconds)}</span><a href={source.landing_page} target="_blank" rel="noreferrer">Source & licensing details ↗</a></div>
                      <button className="btn btn-secondary small source-fetch" onClick={() => fetchSource(source)} disabled={!!busySource || serverConfig?.public_source_fetch_enabled === false}>{busySource === source.id ? <LoaderCircle className="spin" size={15} /> : <CloudDownload size={15} />} Fetch</button>
                    </div>
                  ))}
                </div>
                <p className="small-note">If a source fails to fetch, download it from the linked Pexels page and upload it manually. Public source fetching can be disabled in Settings → Integrations.</p>
              </section>
            </div>

            <section className="panel">
              <PanelHeader eyebrow="SOURCE LIBRARY" title="Imported video jobs" action={<span className="muted-count">{videos.length} records</span>} />
              <JobsTable videos={videos} onSelect={job => setSelectedId(job.id)} onAnalyze={runAnalysis} onDelete={deleteVideo} processingId={processingId} onImport={() => fileRef.current?.click()} />
              <div className="table-note"><CircleHelp size={14} /> Importing a video inspects its real duration, dimensions, and first frame; inference starts only after you press Analyze.</div>
            </section>

            {selected && (
              <section className="panel selected-detail-panel">
                <PanelHeader eyebrow="SELECTED SOURCE" title={selected.source_title || selected.original_name}
                  action={<span className={`status-pill ${statusClass(selected.status)}`}><span className="status-dot" />{statusLabel(selected.status)}{selected.status === "processing" ? ` ${selected.progress_percent.toFixed(0)}%` : ""}</span>} />
                <div className="selected-detail-grid">
                  {selected.preview_url ? (
                    <div className="video-preview"><img src={`${API}${selected.preview_url}`} alt={`Preview frame from ${selected.original_name}`} /><span className="preview-watermark">{selected.source_type === "public" ? "PUBLIC RECORDED FOOTAGE" : "UPLOADED SOURCE"}</span></div>
                  ) : (
                    <div className="empty-visual"><div className="empty-visual-icon"><Video size={28} /></div><strong>No preview frame yet</strong><span>Preview appears after import inspects the file.</span></div>
                  )}
                  <div className="detail-facts">
                    <Fact label="Source" value={selected.source_type === "public" ? "Public recorded footage" : "Operator upload"} />
                    <Fact label="Video duration" value={fmtDuration(selected.duration_seconds)} />
                    <Fact label="Resolution" value={selected.width && selected.height ? `${selected.width} × ${selected.height}` : "Unavailable"} />
                    <Fact label="Frame rate" value={selected.fps ? `${selected.fps.toFixed(2)} FPS` : "Unavailable"} />
                    <Fact label="Model" value={selected.model_name || "Not run yet"} />
                    <Fact label="Average confidence" value={confFmt(selected.avg_confidence)} />
                    <Fact label="Observed peak" value={selected.status === "completed" ? fmtNum(peak) : "—"} />
                    <Fact label="Configured bays" value={fmtNum(selected.configured_spaces)} />
                    {selected.error_message && <div className="error-detail"><AlertTriangle size={15} /><span>{selected.error_message}</span></div>}
                    <div className="detail-actions-row">
                      {selected.status !== "processing" && selected.status !== "queued" && (
                        <button className="btn btn-primary small" onClick={() => runAnalysis(selected)} disabled={!!processingId}>{processingId === selected.id ? <LoaderCircle className="spin" size={15} /> : <Play size={15} />} {selected.status === "completed" ? "Re-analyze" : "Analyze"}</button>
                      )}
                      {selected.annotated_url && (
                        <button className="btn btn-secondary small" onClick={() => downloadAnnotated(selected)} disabled={downloadingId === selected.id}>
                          {downloadingId === selected.id ? <LoaderCircle className="spin" size={15} /> : <Download size={15} />} Download annotated
                        </button>
                      )}
                      <button className="btn btn-ghost small" onClick={() => document.getElementById("video-calibration")?.scrollIntoView({ behavior: "smooth" })}><Layers3 size={14} /> Re-annotate bays</button>
                    </div>
                  </div>
                </div>
                {(selected.status === "processing" || selected.status === "queued") ? (
                  <div className="progress-block">
                    <div><span>Analysis progress</span><strong>{selected.progress_percent.toFixed(1)}%</strong></div>
                    <div className="progress-track"><i style={{ width: `${Math.max(2, selected.progress_percent)}%` }} /></div>
                    <small>Frame {fmtNum(selected.current_frame)} · processed samples {fmtNum(selected.processed_frames)}</small>
                  </div>
                ) : (
                  <div className="detail-chart">
                    <PanelHeader eyebrow="DETECTION TREND" title="Vehicles by sampled timestamp" action={<span className="muted-count">{analytics.length} observations · latest {observed ?? "—"}</span>} />
                    <DetectionChart values={analytics} />
                  </div>
                )}
              </section>
            )}

            <div className="page-subheading" id="video-calibration">
              <div className="eyebrow"><span className="eyebrow-line" />BAY CALIBRATION (VIDEO)</div>
              <h2>Map bays on the selected clip</h2>
              <p>Click at least three points around each bay on the preview, save a label, then run analysis to measure per-space occupancy.</p>
            </div>

            <div className="calibration-toolbar">
              <div className="field-group"><label htmlFor="calibration-video">SOURCE VIDEO</label><select id="calibration-video" value={selected?.id || ""} onChange={e => setSelectedId(e.target.value)}><option value="">Select a video…</option>{videos.map(job => <option key={job.id} value={job.id}>{job.source_title || job.original_name}</option>)}</select></div>
              {selected && <span className={`status-pill ${statusClass(selected.status)}`}>{statusLabel(selected.status)}</span>}
            </div>
            <div className="calibration-layout">
              <section className="panel calibration-image-panel">
                <PanelHeader eyebrow="CLICK TO DRAW" title="Bay polygon editor" action={<span className="coordinate-chip">{pendingPoints.length} points</span>} />
                {selected?.preview_url ? (
                  <div className="canvas-wrap">
                    <CalibrationCanvas imageSrc={`${API}${selected.preview_url}`} spaces={spaces} pending={pendingPoints} onAddPoint={p => addPolygonPoint(p, pendingPoints, next => updatePending(() => next))} />
                    <div className="canvas-guide"><span><i className="legend-dot red-dot" />Occupied</span><span><i className="legend-dot green-dot" />Free</span><span><i className="legend-dot grey-dot" />Unknown</span></div>
                  </div>
                ) : (
                  <div className="calibration-empty"><Layers3 size={28} /><strong>Select or import a video</strong><span>A real preview frame appears here after a source is imported.</span><button className="btn btn-secondary small" onClick={() => fileRef.current?.click()}>Import video</button></div>
                )}
                <div className="draw-controls">
                  <form onSubmit={saveSpace} className="space-form">
                    <div className="field-group"><label htmlFor="space-name">BAY LABEL</label><input id="space-name" value={spaceName} onChange={e => setSpaceName(e.target.value)} maxLength={80} required placeholder="e.g. A-01" /></div>
                    <div className="draw-actions">
                      <button type="button" className="btn btn-ghost small" onClick={() => updatePending(old => old.slice(0, -1))} disabled={!pendingPoints.length}>Undo point</button>
                      <button type="button" className="btn btn-ghost small" onClick={() => updatePending(() => [])} disabled={!pendingPoints.length}>Clear</button>
                      <button type="submit" className="btn btn-primary small" disabled={!selected || pendingPoints.length < 3 || selected.status === "processing" || selected.status === "queued"}><Plus size={14} /> Save bay</button>
                    </div>
                  </form>
                  <p>Normalized coordinates are stored relative to the source frame. Draw polygons inside the bay lines, avoiding adjacent spaces.</p>
                </div>
              </section>
              <section className="panel calibrated-list-panel">
                <PanelHeader eyebrow="CONFIGURED GEOMETRY" title="Parking bays" action={<span className="muted-count">{spaces.length} total</span>} />
                {spaces.length ? (
                  <>
                    <div className="space-counts"><div><span>Occupied</span><strong className="red-text">{occupied}</strong></div><div><span>Free</span><strong className="green-text">{free}</strong></div><div><span>Unknown</span><strong>{spaces.length - doneSpaces}</strong></div></div>
                    <div className="space-list">
                      {spaces.map(space => (
                        <div className="space-row" key={space.id}>
                          <span className={`space-state-dot ${space.state}`} />
                          <div className="space-row-main"><strong>{space.name}</strong><span>{space.polygon.length} polygon points · {space.state}</span></div>
                          <span className={`state-tag ${space.state}`}>{space.state}</span>
                          <button className="icon-btn danger-icon" onClick={() => deleteSpace(space)} disabled={selected?.status === "processing" || selected?.status === "queued"} title={`Delete ${space.name}`}><Trash2 size={14} /></button>
                        </div>
                      ))}
                    </div>
                    <button className="btn btn-primary full-width" onClick={() => selected && runAnalysis(selected)} disabled={!selected || selected.status === "processing" || selected.status === "queued" || !spaces.length || !!processingId}><Play size={15} /> Analyze with these bays</button>
                  </>
                ) : (
                  <div className="list-empty"><Layers3 size={25} /><strong>No bays calibrated</strong><span>Draw and save bay boundaries on the real preview to enable per-space occupancy estimates.</span></div>
                )}
                <div className="calibration-caveat"><AlertTriangle size={15} /><span>Automatic bay state depends on camera angle and detector quality. “Free” is a model estimate, not a guaranteed space.</span></div>
              </section>
            </div>
            </>}

          </>}

          {/* --------------------------------------------- SETTINGS */}
          {activePage === "settings" && <>
            <div className="settings-tabs" role="tablist" aria-label="Settings sections">
              {settingsTabs.map(tab => (
                <button key={tab.id} role="tab" aria-selected={settingsTab === tab.id} className={`settings-tab ${settingsTab === tab.id ? "active" : ""}`} onClick={() => setSettingsTab(tab.id)}>
                  <tab.icon size={15} /><span>{tab.label}</span>
                </button>
              ))}
            </div>


            {settingsTab === "model" && <>
              <div className="settings-grid-2">
                <section className="panel">
                  <PanelHeader eyebrow="INFERENCE RUNTIME" title="Model configuration"
                    action={modelDirty ? <span className="status-pill warning"><span className="status-dot" />Unsaved changes</span> : <span className="muted-count">applies to next run</span>} />
                  <div className="preset-row">
                    <span className="preset-label">RUNTIME PRESETS</span>
                    <div className="chip-row">
                      <button className={`chip ${modelPreset === "speed" ? "active" : ""}`} onClick={() => applyModelPreset("speed")}><Zap size={13} /> Speed · 416px / every 8th frame</button>
                      <button className={`chip ${modelPreset === "balanced" ? "active" : ""}`} onClick={() => applyModelPreset("balanced")}>Balanced · 640px / every 4th frame</button>
                      <button className={`chip ${modelPreset === "accuracy" ? "active" : ""}`} onClick={() => applyModelPreset("accuracy")}>Accuracy · 1280px / every 2nd frame</button>
                    </div>
                  </div>
                  <p className="small-note">Presets adjust image size, frame stride, multi-scale fallback and confidence together. The active preset is highlighted when the draft matches it exactly.</p>
                  <div className="form-grid">
                    <div className="field-group"><label htmlFor="set-model">MODEL</label>
                      <select id="set-model" value={modelDraftLive.model} onChange={e => patchModel({ model: e.target.value })}>
                        {(settingsPayload?.schema.model?.choices ?? []).map(choice => <option key={choice} value={choice}>{choice}</option>)}
                      </select>
                    </div>
                    <div className="field-group"><label htmlFor="set-device">DEVICE</label>
                      <select id="set-device" value={modelDraftLive.device} onChange={e => patchModel({ device: e.target.value })}>
                        {(settingsPayload?.schema.device?.choices ?? ["auto", "cpu", "cuda", "mps"]).map(choice => <option key={choice} value={choice}>{choice}</option>)}
                      </select>
                    </div>
                    <div className="field-group"><label htmlFor="set-confidence">CONFIDENCE · {modelDraftLive.confidence.toFixed(2)}</label>
                      <input id="set-confidence" type="range" min={0.05} max={0.95} step={0.05} value={modelDraftLive.confidence} onChange={e => patchModel({ confidence: Number(e.target.value) })} />
                      <span className="range-scale"><small>0.05 permissive</small><small>0.50 typical</small><small>0.95 strict</small></span>
                    </div>
                    <div className="field-group"><label htmlFor="set-size">IMAGE SIZE (PX)</label><input id="set-size" type="number" min={320} max={2560} step={32} value={modelDraftLive.image_size} onChange={e => patchModel({ image_size: Number(e.target.value) })} /></div>
                    <div className="field-group"><label htmlFor="set-stride">FRAME STRIDE</label><input id="set-stride" type="number" min={1} max={30} value={modelDraftLive.frame_stride} onChange={e => patchModel({ frame_stride: Number(e.target.value) })} /></div>
                    <div className="field-group checkbox-group"><label htmlFor="set-multiscale"><input id="set-multiscale" type="checkbox" checked={modelDraftLive.multiscale} onChange={e => patchModel({ multiscale: e.target.checked })} /> Multi-scale fallback</label></div>
                  </div>
                  <div className={`config-row ${modelChanged.image_size ? "changed" : ""}`}><span>Image size</span><strong>{serverConfig ? `${serverConfig.image_size}px` : "Unavailable"}</strong></div>
                  <div className={`config-row ${modelChanged.confidence ? "changed" : ""}`}><span>Confidence threshold</span><strong>{serverConfig ? serverConfig.confidence.toFixed(2) : "Unavailable"}</strong></div>
                  <div className={`config-row ${modelChanged.frame_stride ? "changed" : ""}`}><span>Frame stride</span><strong>{serverConfig ? `Every ${serverConfig.frame_stride} frames` : "Unavailable"}</strong></div>
                  <div className={`config-row ${modelChanged.device ? "changed" : ""}`}><span>Inference device</span><strong>{serverConfig?.device || "Unavailable"}</strong></div>
                  <div className={`config-row ${modelChanged.multiscale ? "changed" : ""}`}><span>Multi-scale fallback</span><strong>{serverConfig ? (serverConfig.multiscale ? "Enabled" : "Disabled") : "Unavailable"}</strong></div>
                  <div className="config-row"><span>Maximum source size</span><strong>{serverConfig ? `${serverConfig.max_upload_mb} MB` : "Unavailable"}</strong></div>
                  <div className="draw-actions">
                    <button className="btn btn-primary" onClick={() => saveSettingsPatch(
                      { model: modelDraftLive.model, confidence: modelDraftLive.confidence, image_size: modelDraftLive.image_size, frame_stride: modelDraftLive.frame_stride, device: modelDraftLive.device, multiscale: modelDraftLive.multiscale },
                      "Model settings saved. The next analysis run and every new live session use these values.",
                    )}><Check size={15} /> Save model settings</button>
                    <a className="doc-link" href={`${API}/docs`} target="_blank" rel="noreferrer">Open API documentation <ArrowRight size={14} /></a>
                  </div>
                </section>

                <section className="panel">
                  <PanelHeader eyebrow="MODEL CATALOG" title="Checkpoints available" action={<span className="muted-count">{(settingsPayload?.schema.model?.choices ?? []).length} options</span>} />
                  {MODEL_FAMILIES.map(family => {
                    const options = (settingsPayload?.schema.model?.choices ?? []).filter(choice => choice.startsWith(family.key));
                    if (!options.length) return null;
                    return (
                      <div className="model-family" key={family.key}>
                        <div className="model-family-head"><strong>{family.name}</strong><span>{options.length} variants</span></div>
                        <p>{family.note}</p>
                        <div className="chip-row">{options.map(option => <button className={`chip ${modelDraftLive.model === option ? "active" : ""}`} key={option} onClick={() => patchModel({ model: option })}>{option}</button>)}</div>
                      </div>
                    );
                  })}
                  <div className="system-callout"><ShieldCheck size={16} /><span>Ultralytics weights (YOLO26/YOLO11/RT-DETR) are AGPL-3.0; some proprietary commercial distributions require an Enterprise license — review the official terms before deployment. PKLot and CNPark-EXT are research datasets useful for benchmarking bay geometry, not a replacement for your own camera footage.</span></div>
                </section>
              </div>

              <section className="panel model-note-panel">
                <PanelHeader eyebrow="MODEL SELECTION" title="Detection model notes" />
                <div className="model-note-columns">
                  <div><strong>Default: YOLO26 small (yolo26s.pt)</strong><p>Balanced starting point for aerial and ground-level footage at 1280px with multi-scale fallback. Confirm vehicle recall for your camera and bay geometry before operational use.</p></div>
                  <div><strong>Alternatives</strong><p>YOLO11 or RT-DETR can be configured for comparisons. Benchmark accuracy, FPS, memory, and export support on the same labelled holdout clips; do not assume two models improve reliability without measured evidence.</p></div>
                  <div><strong>Commercial deployment</strong><p>Review all dependency, weights, and dataset terms. Ultralytics licensing can require an Enterprise license for some proprietary commercial distributions.</p></div>
                </div>
              </section>
            </>}

            {settingsTab === "integrations" && <>
              <div className="settings-grid-2">
                <section className="panel">
                  <PanelHeader eyebrow="EVENT DELIVERY" title="Webhooks"
                    action={<span className={`status-pill ${settingsPayload?.settings.webhook_url ? "success" : "neutral"}`}><span className="status-dot" />{settingsPayload?.settings.webhook_url ? "Configured" : "Not configured"}</span>} />
                  <div className="field-group"><label htmlFor="hook-url">ENDPOINT URL</label><input id="hook-url" type="url" placeholder="https://example.com/hooks/parkwise" value={intDraftLive.webhookUrl} onChange={e => patchInt({ webhookUrl: e.target.value })} /></div>
                  <div className="field-group">
                    <label htmlFor="hook-secret">SIGNING SECRET</label>
                    <input id="hook-secret" type="password" placeholder={webhookSecretConfigured ? "configured · enter a new value to replace" : "optional · HMAC-SHA256"} value={intDraftLive.webhookSecret} onChange={e => patchInt({ webhookSecret: e.target.value })} autoComplete="new-password" />
                    <small className="field-hint">
                      {webhookSecretConfigured
                        ? "A signing secret is configured. The value is never displayed; typing a new value replaces it."
                        : "No signing secret configured yet."}
                    </small>
                  </div>
                  <div className="hook-events">
                    <span className="hook-events-label">EVENTS</span>
                    <div className="chip-row">
                      <span className="chip">video.completed</span>
                      <span className="chip">video.failed</span>
                      <span className="chip">stream.overcrowding</span>
                    </div>
                  </div>
                  <p className="small-note">Headers: X-Parkwise-Event and X-Parkwise-Signature (hex HMAC-SHA256 of the body). Redirects are not followed.</p>
                  <div className="draw-actions">
                    <button className="btn btn-primary small" onClick={saveWebhook}><Check size={14} /> Save webhook</button>
                    <button className="btn btn-secondary small" onClick={testWebhook} disabled={webhookResult === "Sending test event…"}>{webhookResult === "Sending test event…" ? <LoaderCircle className="spin" size={14} /> : <Send size={14} />} Send test event</button>
                  </div>
                  {webhookResult && <div className="key-callout mono"><code>{webhookResult}</code></div>}
                </section>

                <section className="panel">
                  <PanelHeader eyebrow="PUBLIC FOOTAGE & MAP" title="Source & basemap settings"
                    action={<span className="muted-count"><CloudDownload size={13} /> {sources.length} sources</span>} />
                  <div className="field-group checkbox-group">
                    <label htmlFor="int-sources"><input id="int-sources" type="checkbox" checked={intDraftLive.publicSources} onChange={e => patchInt({ publicSources: e.target.checked })} /> Enable public source fetching (Pexels samples)</label>
                  </div>
                  <div className="stream-form-row">
                    <div className="field-group"><label htmlFor="int-lat">MAP CENTRE LAT</label><input id="int-lat" type="number" step="0.0001" value={intDraftLive.mapLat} onChange={e => patchInt({ mapLat: e.target.value })} placeholder="41.9028" /></div>
                    <div className="field-group"><label htmlFor="int-lon">MAP CENTRE LON</label><input id="int-lon" type="number" step="0.0001" value={intDraftLive.mapLon} onChange={e => patchInt({ mapLon: e.target.value })} placeholder="12.4964" /></div>
                  </div>
                  <div className="field-group"><label htmlFor="int-style">MAP STYLE URL (MAPLIBRE STYLE SPEC)</label><input id="int-style" type="url" placeholder="https://demotiles.maplibre.org/style.json" value={intDraftLive.mapStyle} onChange={e => patchInt({ mapStyle: e.target.value })} /></div>
                  <div className="draw-actions">
                    <button className="btn btn-primary small" onClick={() => saveSettingsPatch(
                      {
                        public_sources_enabled: intDraftLive.publicSources,
                        map_style: intDraftLive.mapStyle,
                        map_center: intDraftLive.mapLat && intDraftLive.mapLon ? [Number(intDraftLive.mapLat), Number(intDraftLive.mapLon)] : null,
                      },
                      "Integration settings saved.",
                    )}><Check size={14} /> Save integrations</button>
                  </div>
                  <p className="small-note">Map centre is stored as [latitude, longitude]. The default basemap is MapLibre demotiles — open source, no API key required.</p>
                </section>
              </div>

              <section className="panel">
                <PanelHeader eyebrow="SITE MAP" title="Configured stream locations"
                  action={<span className="muted-count"><MapPin size={13} /> {locatedStreams.length} located</span>} />
                <SiteMap sites={locatedStreams} center={mapCenter} styleUrl={intDraftLive.mapStyle || null} />
                {locatedStreams.length > 0 && (
                  <div className="chip-row map-stream-chips">{locatedStreams.map(stream => <span className="chip" key={stream.id}><MapPin size={12} /> {stream.name}</span>)}</div>
                )}
                {locatedStreams.length === 0 && <p className="small-note">Add latitude and longitude to a stream in Live Analysis to place it on the map. Streams without coordinates simply are not pinned.</p>}
              </section>
            </>}

            {settingsTab === "users" && <>
              <section className="panel">
                <PanelHeader eyebrow="THIS BROWSER SESSION" title="API key access"
                  action={<span className={`status-pill ${sessionKeyActive ? "success" : "neutral"}`}><span className="status-dot" />{sessionKeyActive ? "Key active for this tab" : "No session key"}</span>} />
                <p className="small-note">When the deployment runs with <code>PARKWISE_AUTH_REQUIRED=true</code> (or you want to act as a specific user), paste an API key below. It is kept in <b>sessionStorage only</b> — it disappears when this tab closes and is never sent anywhere except this API.</p>
                <div className="draw-actions">
                  <div className="field-group grow-field"><label htmlFor="session-key">API KEY (pk_…)</label>
                    <input id="session-key" type="password" autoComplete="off" placeholder={sessionKeyActive ? "•••••••• — a key is active" : "pk_…"} value={sessionKeyInput} onChange={e => setSessionKeyInput(e.target.value)} />
                  </div>
                  <button className="btn btn-primary small" onClick={applySessionKey} disabled={!sessionKeyInput.trim() && !sessionKeyActive}><KeyRound size={14} /> {sessionKeyActive ? "Replace / clear" : "Use key"}</button>
                  {sessionKeyActive && <button className="btn btn-ghost small" onClick={() => { setSessionApiKey(""); setSessionKeyActive(false); setMessage({ tone: "info", text: "Session API key cleared." }); }}>Clear</button>}
                </div>
              </section>
              <section className="panel">
                <PanelHeader eyebrow="ACCESS CONTROL" title="Users & API keys"
                  action={<span className="muted-count">{users.length} accounts · {roleSummary}</span>} />
                {plainKey && (
                  <div className="key-callout">
                    <KeyRound size={17} />
                    <div><strong>{plainKey.note}</strong><code>{plainKey.key}</code></div>
                    <button className="notice-close" onClick={() => setPlainKey(null)} aria-label="Dismiss key"><X size={14} /></button>
                  </div>
                )}
                <form className="stream-form inline-form" onSubmit={createUser}>
                  <div className="field-group"><label htmlFor="user-name">USERNAME</label><input id="user-name" value={newUser.username} onChange={e => setNewUser(u => ({ ...u, username: e.target.value }))} required placeholder="operator2" /></div>
                  <div className="field-group"><label htmlFor="user-display">DISPLAY NAME</label><input id="user-display" value={newUser.display_name} onChange={e => setNewUser(u => ({ ...u, display_name: e.target.value }))} required placeholder="Second operator" /></div>
                  <div className="field-group"><label htmlFor="user-role">ROLE</label>
                    <select id="user-role" value={newUser.role} onChange={e => setNewUser(u => ({ ...u, role: e.target.value }))}>
                      {(systemInfo?.security.roles ?? ["admin", "operator", "viewer"]).map(role => <option key={role} value={role}>{role}</option>)}
                    </select>
                  </div>
                  <button className="btn btn-primary" type="submit"><Plus size={15} /> Create user</button>
                </form>
                {!usersError && users.length > 0 && (
                  <div className="users-toolbar">
                    <div className="field-group grow-field"><label htmlFor="user-search">SEARCH ACCOUNTS</label>
                      <span className="input-with-icon"><Search size={14} /><input id="user-search" placeholder="Search username or display name…" value={userSearch} onChange={e => setUserSearch(e.target.value)} /></span>
                    </div>
                    <span className="muted-count"><Users size={13} /> {visibleUsers.length} of {users.length} shown</span>
                  </div>
                )}
                {usersError ? (
                  <div className="list-empty"><ShieldCheck size={24} /><strong>Accounts are not visible to this session</strong><span>{usersError}</span></div>
                ) : visibleUsers.length ? (
                  <div className="table-scroll">
                    <table className="data-table">
                      <thead><tr><th>Username</th><th>Display name</th><th>Role</th><th>Status</th><th>API key</th><th>Created</th><th>Last seen</th><th>Actions</th></tr></thead>
                      <tbody>{visibleUsers.map(user => (
                        <tr key={user.id}>
                          <td><strong>{user.username}</strong></td>
                          <td>{user.display_name}</td>
                          <td>
                            <select className="inline-select" value={user.role} onChange={e => patchUser(user.id, { role: e.target.value })}>
                              {(systemInfo?.security.roles ?? ["admin", "operator", "viewer"]).map(role => <option key={role} value={role}>{role}</option>)}
                            </select>
                          </td>
                          <td><button className={`status-pill ${user.is_active ? "success" : "neutral"}`} onClick={() => patchUser(user.id, { is_active: !user.is_active })} title="Toggle active"><span className="status-dot" />{user.is_active ? "Active" : "Disabled"}</button></td>
                          <td>{user.has_api_key ? "Issued" : "—"}</td>
                          <td>{new Date(user.created_at).toLocaleDateString()}</td>
                          <td>{user.last_login_at ? new Date(user.last_login_at).toLocaleDateString() : "Never"}</td>
                          <td>
                            <div className="table-actions">
                              <button className="icon-btn" title="Rotate API key" onClick={() => rotateKey(user)}><KeyRound size={14} /></button>
                              <button className="icon-btn danger-icon" title="Delete user" onClick={() => removeUser(user)}><Trash2 size={14} /></button>
                            </div>
                          </td>
                        </tr>
                      ))}</tbody>
                    </table>
                  </div>
                ) : (
                  <div className="list-empty"><Search size={24} /><strong>No accounts match “{userSearch}”</strong><span>Clear the search to see all {users.length} accounts.</span></div>
                )}
                <div className="table-note"><ShieldCheck size={14} /> Keys authenticate as <b>Authorization: Bearer pk_…</b> or <b>X-API-Key</b> on REST calls. Frame WebSockets use short-lived single-use tickets (never <b>?key=</b>). Role enforcement applies whenever a key is presented; with PARKWISE_AUTH_REQUIRED=true every request needs one. The last active admin cannot be removed.</div>
              </section>
            </>}

            {settingsTab === "billing" && <>
              <div className="system-callout"><ShieldCheck size={16} /><span><b>Local plan simulation.</b> {billingReport?.billing_note || "Plan limits are enforced locally for this self-hosted pilot. No payment processor is connected and no charges are made — listed prices are illustrative only."}</span></div>
              <div className="plans-grid">
                {settingsPayload && Object.entries(settingsPayload.plans).map(([key, plan]) => (
                  <div className={`plan-card ${billingReport?.plan === key ? "active" : ""}`} key={key}>
                    <div className="plan-top"><strong>{plan.name}</strong>{billingReport?.plan === key && <span className="status-pill success"><span className="status-dot" />Current</span>}</div>
                    <div className="plan-price">{plan.price_month_usd ? `$${plan.price_month_usd}` : "$0"}<span>/mo</span></div>
                    <p>{plan.blurb}</p>
                    <ul>{Object.entries(plan.limits).map(([limit, value]) => <li key={limit}><span>{limit.replace(/_/g, " ")}</span><strong>{typeof value === "number" ? value.toLocaleString() : String(value)}</strong></li>)}</ul>
                    <button className={`btn ${billingReport?.plan === key ? "btn-ghost" : "btn-primary"} small full-width`} disabled={billingReport?.plan === key || !billingReport} onClick={() => changePlan(key)}>
                      {billingReport?.plan === key ? "Current plan" : "Switch plan"}
                    </button>
                  </div>
                ))}
              </div>
              <section className="panel">
                <PanelHeader eyebrow="USAGE" title={`Quota usage · ${billingReport?.month || "this month"}`}
                  action={<span className="muted-count">{billingReport?.videos_total ?? 0} videos total</span>} />
                <div className="usage-facts">
                  <div className="usage-fact"><span>Plan</span><strong>{billingReport?.plan_info?.name || billingReport?.plan || "—"}</strong></div>
                  <div className="usage-fact"><span>Period</span><strong>{billingReport?.month || "—"}</strong></div>
                  <div className="usage-fact"><span>Videos</span><strong>{billingReport?.videos_total ?? 0}</strong></div>
                  <div className="usage-fact"><span>Billing mode</span><strong>{billingReport?.billing_mode || "local simulation"}</strong></div>
                  {Object.entries(billingReport?.usage ?? {}).slice(0, 4).map(([key, value]) => (
                    <div className="usage-fact" key={key}><span>{key.replace(/_/g, " ")}</span><strong>{value.toLocaleString()}</strong></div>
                  ))}
                </div>
                {billingReport?.meters.length ? billingReport.meters.map(meter => (
                  <div className="meter" key={meter.key}>
                    <div className="meter-head"><span>{meter.label}</span><strong>{meter.used} / {meter.limit}</strong></div>
                    <div className={`meter-track ${meter.exceeded ? "over" : meter.percent >= 80 ? "warn" : ""}`}><i style={{ width: `${Math.min(100, meter.percent)}%` }} /></div>
                    <small>{meter.exceeded ? "Limit reached — uploads or streams are blocked until you upgrade or remove data." : meter.percent >= 80 ? `Warning — ${meter.percent}% of the plan allowance used` : `${meter.percent}% of the plan allowance used`}</small>
                  </div>
                )) : <div className="list-empty"><CreditCard size={24} /><strong>No usage data</strong></div>}
                <p className="honesty-note"><ShieldCheck size={14} /> Quotas are enforced server-side when a meter reaches its limit (HTTP 402 with a clear message). Storage includes original videos, previews and annotated outputs.</p>
              </section>
            </>}

            {settingsTab === "system" && <>
              <div className="system-grid">
                <section className="panel">
                  <PanelHeader eyebrow="CONNECTIVITY" title="Service status" />
                  <div className="system-service">
                    <div className={`service-icon ${apiStatus}`}><Wifi size={19} /></div>
                    <div><strong>FastAPI application</strong><span>{apiStatus === "online" ? "Health endpoint is responding." : apiStatus === "offline" ? "Cannot reach API at configured URL." : "Checking connection…"}</span></div>
                    <span className={`status-pill ${apiStatus === "online" ? "success" : apiStatus === "offline" ? "danger" : "neutral"}`}>{apiStatus}</span>
                  </div>
                  <div className="system-service">
                    <div className="service-icon"><Database size={19} /></div>
                    <div><strong>Persistence</strong><span>SQLAlchemy database; default SQLite path from server configuration.</span></div>
                    <span className="status-pill neutral">Configured</span>
                  </div>
                  <div className="system-service">
                    <div className="service-icon"><HardDriveUpload size={19} /></div>
                    <div><strong>Media storage</strong><span>Server filesystem stores original, preview, annotated and stream snapshot artifacts.</span></div>
                    <span className="status-pill neutral">Local</span>
                  </div>
                  <div className="system-service">
                    <div className="service-icon"><Cpu size={19} /></div>
                    <div><strong>Inference runtime</strong><span>{serverConfig?.model || systemInfo?.python_model_stack.default_model || "—"} · {serverConfig?.device || "auto"} · confidence {serverConfig ? serverConfig.confidence.toFixed(2) : "—"} · stride {serverConfig?.frame_stride ?? "—"}</span></div>
                    <span className={`status-pill ${serverConfig ? "success" : "neutral"}`}>{serverConfig ? "Loaded" : "Unknown"}</span>
                  </div>
                  <button className="btn btn-secondary" onClick={() => { refreshData(); refreshAdmin(); }}><RefreshCw size={15} /> Re-check services</button>
                </section>

                <section className="panel">
                  <PanelHeader eyebrow="SECURITY POSTURE" title="Access & limits" />
                  <div className="config-row"><span>API-key auth</span><strong>{systemInfo?.security.auth_required ? "Required" : "Optional (PARKWISE_AUTH_REQUIRED=false)"}</strong></div>
                  <div className="config-row"><span>Rate limit</span><strong>{systemInfo?.security.rate_limit_per_minute ?? "—"} requests / minute</strong></div>
                  <div className="config-row"><span>Upload cap</span><strong>{systemInfo?.security.upload_max_mb ?? "—"} MB</strong></div>
                  <div className="config-row"><span>Stream URL schemes</span><strong>{(systemInfo?.security.ssrf_schemes_allowed ?? []).join(", ")}</strong></div>
                  <div className="chip-row">{(systemInfo?.security.roles ?? []).map(role => <span className="chip" key={role}>{role}</span>)}</div>
                  <div className="system-callout"><Zap size={16} /><span>SSRF guard: private LAN camera addresses are allowed for real CCTV; loopback, link-local, cloud metadata endpoints, <code>.internal</code> hosts and file/ftp schemes are rejected.</span></div>
                  <a className="doc-link" href={`${API}/docs`} target="_blank" rel="noreferrer">Open API documentation <ArrowRight size={14} /></a>
                </section>
              </div>

              <section className="panel">
                <PanelHeader eyebrow="BUILD INVENTORY" title="About this deployment" />
                <div className="config-row"><span>Service</span><strong>{systemInfo?.service || "parkwise-ai-api"}</strong></div>
                <div className="config-row"><span>Environment</span><strong>{systemInfo?.env || settingsPayload?.env.env || "—"}</strong></div>
                <div className="config-row"><span>Default model</span><strong>{systemInfo?.python_model_stack.default_model || "—"}</strong></div>
                <div className="config-row"><span>Ultralytics licensing</span><strong>{systemInfo?.python_model_stack.ultralytics_license || "—"}</strong></div>
                <div className="config-row"><span>Model catalog</span><strong>{(systemInfo?.model_catalog ?? []).length} checkpoints</strong></div>
                <div className="config-row"><span>Active plan</span><strong>{billingReport?.plan || String(settingsPayload?.settings.plan ?? "starter")}</strong></div>
                <div className="config-row"><span>Max upload size</span><strong>{serverConfig ? `${serverConfig.max_upload_mb} MB` : "—"}</strong></div>
                <div className="config-row"><span>Public source fetch</span><strong>{settingsPayload?.settings.public_sources_enabled === false ? "Disabled" : "Enabled"}</strong></div>
                <div className="config-row"><span>Webhook endpoint</span><strong>{settingsPayload?.settings.webhook_url ? String(settingsPayload.settings.webhook_url) : "Not configured"}</strong></div>
                <div className="config-row"><span>Activity events</span><strong>{fmtNum(systemInfo?.activity_events)}</strong></div>
                <p className="honesty-note"><ShieldCheck size={14} /> ParkWise AI performs real inference over imported footage and configured camera sources. Nothing in this panel is simulated.</p>
              </section>
            </>}
          </>}

          <footer className="page-footer">
            <span>© {new Date().getFullYear()} ParkWise AI · Video-based parking intelligence</span>
            <div><span><span className={`status-dot ${apiStatus === "online" ? "online" : "offline"}`} /> {apiStatus === "online" ? "API connected" : "API disconnected"}</span><a href={`${API}/docs`} target="_blank" rel="noreferrer">Developer API <ArrowRight size={12} /></a></div>
          </footer>
          <input ref={fileRef} type="file" accept="video/mp4,video/quicktime,video/x-msvideo,video/webm,video/x-matroska,.m4v" hidden onChange={handleUpload} />
        </div>
      </section>
    </main>
  );
}

function prettyAction(action: string) {
  const known: Record<string, string> = {
    "analysis.completed": "Analysis completed",
    "analysis.requested": "Analysis requested",
    "billing.plan_changed": "Plan changed",
    "settings.updated": "Settings updated",
    "space.created": "Bay created",
    "stream.calibrated": "Stream calibrated",
    "stream.created": "Stream added",
    "stream.deleted": "Stream removed",
    "stream.ws_ticket_created": "Stream tickets",
    "user.created": "User created",
    "user.deleted": "User removed",
    "video.deleted": "Video removed",
    "video.imported": "Video imported",
    "video.uploaded": "Video uploaded",
    video_imported: "Imported",
    video_processed: "Processed",
    video_failed: "Failed",
    source_fetched: "Fetched source",
    stream_created: "Stream added",
    spaces_saved: "Bays saved",
    model_updated: "Model change",
    user_login: "Sign-ins",
  };
  return known[action] ?? action.replace(/[._]/g, " ").replace(/^\w/, c => c.toUpperCase());
}

function streamRunningLabel(stream: StreamRow) {
  const isReplay = stream.kind === "video" || stream.source_mode === "replay";
  if (stream.running || stream.status === "live") return isReplay ? "Replay" : "Live";
  if (stream.status === "reconnecting") return "Reconnecting";
  if (stream.status === "error") return "Error";
  if (stream.status === "starting") return "Starting";
  if (stream.last_error) return "Blocked";
  return "Idle";
}

function streamStatusTone(stream: StreamRow): string {
  const label = streamRunningLabel(stream);
  if (label === "Live") return "success";
  if (label === "Replay") return "info";
  if (label === "Error" || label === "Blocked") return "danger";
  if (label === "Reconnecting" || label === "Starting") return "warning";
  return "neutral";
}

function occupancyRowsFor(points: OccupancyPoint[]) {
  const grouped = new Map<string, { name: string; states: OccupancyPoint[] }>();
  for (const point of points) {
    const entry = grouped.get(point.space_id) ?? { name: point.space_name, states: [] };
    entry.states.push(point);
    grouped.set(point.space_id, entry);
  }
  return [...grouped.values()].map(({ name, states }) => {
    const occupiedCount = states.filter(s => s.state === "occupied").length;
    const transitions = states.reduce((count, point, index) => (index > 0 && states[index - 1].state !== point.state ? count + 1 : count), 0);
    return {
      name,
      samples: states.length,
      occupiedShare: Math.round((occupiedCount / Math.max(1, states.length)) * 100),
      lastState: states[states.length - 1].state,
      transitions,
    };
  });
}

function ReviewedTable({ rows, openId, onOpen }: { rows: ReviewedVideo[]; openId: string; onOpen: (id: string) => void }) {
  return (
    <div className="table-scroll">
      <table className="data-table">
        <thead><tr><th>Video</th><th>Completed</th><th>Duration</th><th>Peak</th><th>Confidence</th><th>Samples</th><th>Occupied share</th><th>Annotations</th></tr></thead>
        <tbody>{rows.map(row => (
          <tr key={row.id} className={openId === row.id ? "row-active" : ""}>
            <td><strong>{row.name}</strong></td>
            <td>{row.completed_at ? new Date(row.completed_at).toLocaleString() : "—"}</td>
            <td>{fmtDuration(row.duration_seconds)}</td>
            <td>{fmtNum(row.peak_vehicles)}</td>
            <td>{confFmt(row.avg_confidence)}</td>
            <td>{fmtNum(row.samples)}</td>
            <td>{row.occupied_share_percent == null ? "—" : `${row.occupied_share_percent}%`}</td>
            <td><div className="table-actions"><button className="icon-btn" title="View annotations" onClick={() => onOpen(row.id)}><ArrowRight size={15} /></button></div></td>
          </tr>
        ))}</tbody>
      </table>
    </div>
  );
}

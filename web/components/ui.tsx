"use client";

import { useCallback, useEffect, useRef } from "react";
import type { MouseEvent, ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { ArrowRight, Database, FileVideo, LoaderCircle, Play, Trash2 } from "lucide-react";
import { fmtDuration, fmtNum, statusClass, statusLabel, type VideoJob } from "@/lib/data";

export function MetricCard({ title, value, detail, icon: Icon, accent, mini }: { title: string; value: string; detail: string; icon: LucideIcon; accent: string; mini: ReactNode }) {
  return (
    <div className={`metric-card ${accent}`}>
      <div className="metric-top"><span>{title}</span><div className="metric-icon"><Icon size={17} /></div></div>
      <div className="metric-value">{value}</div>
      <div className="metric-bottom"><span>{detail}</span><div className="metric-mini">{mini}</div></div>
    </div>
  );
}

export function PanelHeader({ eyebrow, title, action }: { eyebrow: string; title: string; action?: ReactNode }) {
  return <div className="panel-header"><div><div className="panel-eyebrow">{eyebrow}</div><h2>{title}</h2></div>{action}</div>;
}

export function Fact({ label, value }: { label: string; value: string }) {
  return <div className="fact-item"><span>{label}</span><strong>{value}</strong></div>;
}

export function EmptyTable({ title, description, action, actionLabel }: { title: string; description: string; action: () => void; actionLabel: string }) {
  return (
    <div className="empty-state">
      <div className="empty-state-icon"><Database size={22} /></div>
      <strong>{title}</strong>
      <span>{description}</span>
      <button className="btn btn-secondary small" onClick={action}>{actionLabel} <ArrowRight size={13} /></button>
    </div>
  );
}

export function JobsTable({ videos, onSelect, onAnalyze, onDelete, processingId, onImport }: {
  videos: VideoJob[];
  onSelect: (job: VideoJob) => void;
  onAnalyze: (job: VideoJob) => void;
  onDelete: (job: VideoJob) => void;
  processingId: string;
  onImport?: () => void;
}) {
  if (!videos.length) {
    return (
      <EmptyTable
        title="No imported videos"
        description="Import your own permitted parking footage or fetch a public Pexels clip to start creating real measurements."
        action={onImport || (() => undefined)}
        actionLabel="Import video"
      />
    );
  }
  return (
    <div className="table-scroll">
      <table className="data-table">
        <thead>
          <tr><th>Source</th><th>Type</th><th>Resolution</th><th>Duration</th><th>Status</th><th>Observed peak</th><th>Actions</th></tr>
        </thead>
        <tbody>
          {videos.map((job) => (
            <tr key={job.id}>
              <td>
                <button className="source-table-cell" onClick={() => onSelect(job)}>
                  <span className="source-table-icon"><FileVideo size={16} /></span>
                  <span><strong>{job.source_title || job.original_name}</strong><small>{new Date(job.created_at).toLocaleString()}</small></span>
                </button>
              </td>
              <td><span className="type-chip">{job.source_type === "public" ? "Public clip" : "Upload"}</span></td>
              <td>{job.width && job.height ? `${job.width} × ${job.height}` : "—"}</td>
              <td>{fmtDuration(job.duration_seconds)}</td>
              <td>
                <span className={`status-pill ${statusClass(job.status)}`}><span className="status-dot" />{statusLabel(job.status)}{job.status === "processing" ? ` ${job.progress_percent.toFixed(0)}%` : ""}</span>
                {job.status === "processing" && <div className="mini-progress"><i style={{ width: `${job.progress_percent}%` }} /></div>}
              </td>
              <td>{job.status === "completed" ? fmtNum(job.max_vehicle_count) : "—"}</td>
              <td>
                <div className="table-actions">
                  <button className="icon-btn" title="Inspect video" onClick={() => onSelect(job)}><ArrowRight size={15} /></button>
                  {job.status !== "processing" && job.status !== "queued" && (
                    <button className="icon-btn run-icon" title="Run or rerun inference" disabled={!!processingId} onClick={() => onAnalyze(job)}>
                      {processingId === job.id ? <LoaderCircle className="spin" size={15} /> : <Play size={15} />}
                    </button>
                  )}
                  <button className="icon-btn danger-icon" title="Delete video and its stored measurements" disabled={job.status === "processing" || job.status === "queued"} onClick={() => onDelete(job)}><Trash2 size={15} /></button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Click-to-draw polygon editor over a preview frame (used for videos and live snapshots). */
export function CalibrationCanvas({ imageSrc, spaces, pending, onAddPoint }: { imageSrc: string; spaces: { name: string; polygon: number[][]; state?: string }[]; pending: number[][]; onAddPoint: (point: number[]) => void }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const imgRef = useRef<HTMLImageElement | null>(null);
  const paint = useCallback(() => {
    const canvas = canvasRef.current, image = imgRef.current;
    if (!canvas || !image) return;
    const ctx = canvas.getContext("2d"); if (!ctx) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height); ctx.drawImage(image, 0, 0, canvas.width, canvas.height);
    for (const space of spaces) {
      const coords = space.polygon.map(([x, y]) => [x * canvas.width, y * canvas.height] as const);
      if (!coords.length) continue;
      ctx.beginPath(); ctx.moveTo(coords[0][0], coords[0][1]); coords.slice(1).forEach(([x, y]) => ctx.lineTo(x, y)); ctx.closePath();
      ctx.fillStyle = space.state === "occupied" ? "rgba(239,68,68,.19)" : space.state === "free" ? "rgba(34,197,94,.16)" : "rgba(148,163,184,.14)";
      ctx.strokeStyle = space.state === "occupied" ? "#f87171" : space.state === "free" ? "#4ade80" : "#cbd5e1"; ctx.lineWidth = Math.max(2, canvas.width / 900); ctx.fill(); ctx.stroke();
      ctx.font = `bold ${Math.max(14, canvas.width / 80)}px sans-serif`; ctx.fillStyle = "white"; ctx.fillText(space.name, coords[0][0] + 4, coords[0][1] - 5);
    }
    if (pending.length) {
      ctx.beginPath(); ctx.moveTo(pending[0][0] * canvas.width, pending[0][1] * canvas.height);
      pending.slice(1).forEach(([x, y]) => ctx.lineTo(x * canvas.width, y * canvas.height));
      ctx.strokeStyle = "#a78bfa"; ctx.lineWidth = Math.max(3, canvas.width / 600); ctx.stroke();
      pending.forEach(([x, y], i) => {
        ctx.beginPath(); ctx.arc(x * canvas.width, y * canvas.height, Math.max(5, canvas.width / 150), 0, Math.PI * 2); ctx.fillStyle = "#a78bfa"; ctx.fill();
        ctx.fillStyle = "#fff"; ctx.font = `bold ${Math.max(12, canvas.width / 100)}px sans-serif`; ctx.fillText(String(i + 1), x * canvas.width + 6, y * canvas.height - 4);
      });
    }
  }, [spaces, pending]);
  const paintRef = useRef(paint);
  useEffect(() => { paintRef.current = paint; }, [paint]);
  useEffect(() => { paint(); }, [paint]);
  useEffect(() => {
    const image = new Image();
    image.onload = () => { imgRef.current = image; const canvas = canvasRef.current; if (!canvas) return; canvas.width = image.naturalWidth; canvas.height = image.naturalHeight; paintRef.current(); };
    image.src = imageSrc;
  }, [imageSrc]);
  const handleClick = (event: MouseEvent<HTMLCanvasElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    const x = Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width));
    const y = Math.min(1, Math.max(0, (event.clientY - rect.top) / rect.height));
    onAddPoint([Number(x.toFixed(5)), Number(y.toFixed(5))]);
  };
  return <canvas className="calibration-canvas" ref={canvasRef} onClick={handleClick} aria-label="Click around a parking bay to draw its polygon" />;
}

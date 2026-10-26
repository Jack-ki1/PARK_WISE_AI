import type { Metadata } from "next";
import Link from "next/link";
import {
  Activity, ArrowRight, Cpu, Gauge, HardDriveUpload, Layers3, LayoutDashboard,
  RadioTower, ShieldCheck, Webhook,
} from "lucide-react";

export const metadata: Metadata = {
  title: "ParkWise AI — Video-based parking intelligence",
  description:
    "ParkWise AI runs vehicle detection, tracking and per-bay occupancy over footage you upload or cameras you connect, and turns the stored measurements into a live analytics dashboard.",
  openGraph: {
    title: "ParkWise AI — Video-based parking intelligence",
    description:
      "Real YOLO inference over parking footage: annotated videos, calibrated bay occupancy, live camera streams and an analytics dashboard. No fabricated KPIs.",
    type: "website",
  },
};

const FEATURES = [
  {
    icon: Cpu,
    title: "Detection & tracking",
    body: "YOLO26/YOLO11 vehicle detection with ByteTrack identities on every sampled frame, plus an annotated H.264 MP4 you can download and review frame by frame.",
  },
  {
    icon: Layers3,
    title: "Calibrated bay occupancy",
    body: "Draw polygons over each parking bay on a real frame from the source. Occupancy is then measured per bay — occupied, free or unknown — and stored for every sample.",
  },
  {
    icon: RadioTower,
    title: "Live analysis",
    body: "Point a stream at an RTSP/HTTP camera URL or replay an uploaded clip. Annotated frames arrive over a ticketed WebSocket with flickering bay boxes, live metrics, re-annotation and clip recording.",
  },
  {
    icon: LayoutDashboard,
    title: "Analytics dashboard",
    body: "KPIs, activity breakdowns, confidence and occupancy trends, stream health, reviewed-video tables and CSV export — every value computed from stored inference results.",
  },
  {
    icon: ShieldCheck,
    title: "Keyed access control",
    body: "API keys with admin/operator/viewer roles, rate-limited mutations, ticket-only WebSocket auth, an SSRF guard for camera URLs and a fail-closed production startup check.",
  },
  {
    icon: Webhook,
    title: "Integrations & API",
    body: "A documented FastAPI surface with OpenAPI docs, signed webhooks for video and overcrowding events, and fetchable public sample footage for quick evaluation.",
  },
] as const;

const STEPS = [
  {
    icon: HardDriveUpload,
    title: "Bring footage",
    body: "Upload a permitted parking video or fetch one of the linked public Pexels samples. Import inspects real duration, resolution and a preview frame.",
  },
  {
    icon: Layers3,
    title: "Calibrate & analyze",
    body: "Draw bay polygons on a real frame, then run inference. Progress streams to the dashboard while results — samples, transitions and an annotated MP4 — are stored.",
  },
  {
    icon: Gauge,
    title: "Review & operate",
    body: "Inspect charts, occupancy history and annotated output; connect cameras for live analysis; export CSV or trigger follow-ups through the API and webhooks.",
  },
] as const;

const STACK = [
  "FastAPI", "SQLAlchemy", "Ultralytics YOLO", "ByteTrack", "OpenCV", "Next.js 16",
  "TypeScript", "Tailwind CSS v4", "Recharts", "MapLibre", "WebSockets", "Docker",
];

export default function HomePage() {
  return (
    <main className="landing">
      <header className="landing-nav">
        <div className="landing-brand">
          <div className="brand-mark"><span>P</span><i /></div>
          <div className="brand-copy"><strong>ParkWise <b>AI</b></strong><span>PARKING INTELLIGENCE</span></div>
        </div>
        <nav className="landing-nav-actions">
          <a className="btn btn-ghost" href="#features">Features</a>
          <a className="btn btn-ghost" href="#how">How it works</a>
          <Link className="btn btn-primary" href="/dashboard">Open dashboard <ArrowRight size={15} /></Link>
        </nav>
      </header>

      <section className="landing-hero">
        <div className="landing-hero-copy">
          <div className="eyebrow"><span className="eyebrow-line" />VIDEO-BASED PARKING INTELLIGENCE</div>
          <h1>Measure parking from real footage — <em>not guesswork.</em></h1>
          <p>
            ParkWise AI runs vehicle detection, multi-object tracking and per-bay occupancy over videos
            you upload or cameras you connect, then turns the stored measurements into an analytics
            dashboard. A fresh install starts empty on purpose: every number appears only after a real
            inference run.
          </p>
          <div className="landing-actions">
            <Link className="btn btn-primary" href="/dashboard">Open the dashboard <ArrowRight size={16} /></Link>
            <a className="btn btn-secondary" href="#showcase">See the interface</a>
          </div>
          <div className="landing-facts">
            <div className="landing-fact"><strong>Real inference</strong><span>YOLO + ByteTrack over your footage</span></div>
            <div className="landing-fact"><strong>Per-bay states</strong><span>occupied · free · unknown, measured</span></div>
            <div className="landing-fact"><strong>Live capable</strong><span>cameras & replay over WebSocket</span></div>
          </div>
        </div>
        <div className="landing-hero-art" aria-hidden="true">
          <div className="landing-art-frame"><Activity size={26} /><span>frame 0142 · 17 vehicles · conf 0.71</span></div>
          <div className="landing-art-bay free">A-01 free</div>
          <div className="landing-art-bay occupied">A-02 occupied</div>
          <div className="landing-art-bay free">A-03 free</div>
        </div>
      </section>

      <section className="landing-showcase" id="showcase">
        <figure className="landing-shot">
          {/* eslint-disable-next-line @next/next/no-img-element -- static showcase art, not runtime media */}
          <img src="/showcase/dashboard-light.png" alt="ParkWise AI dashboard showing KPI cards, activity charts and reviewed videos" />
          <figcaption>Bright operations dashboard — KPIs, activity breakdowns and reviewed-video annotations.</figcaption>
        </figure>
        <figure className="landing-shot">
          {/* eslint-disable-next-line @next/next/no-img-element -- static showcase art, not runtime media */}
          <img src="/showcase/live-analysis.png" alt="Live Analysis workspace with source form, annotated viewer and live metrics" />
          <figcaption>Live Analysis — camera and replay sources on the left, annotated frames and live metrics on the right.</figcaption>
        </figure>
      </section>

      <section className="landing-section" id="features">
        <div className="landing-section-head">
          <div className="eyebrow"><span className="eyebrow-line" />WHAT IT DOES</div>
          <h2>From raw footage to operational answers</h2>
        </div>
        <div className="landing-grid">
          {FEATURES.map(({ icon: Icon, title, body }) => (
            <article className="landing-card" key={title}>
              <div className="landing-card-icon"><Icon size={19} /></div>
              <strong>{title}</strong>
              <p>{body}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="landing-section" id="how">
        <div className="landing-section-head">
          <div className="eyebrow"><span className="eyebrow-line" />HOW IT WORKS</div>
          <h2>Three steps to measured occupancy</h2>
        </div>
        <div className="landing-steps">
          {STEPS.map(({ icon: Icon, title, body }, index) => (
            <article className="landing-step" key={title}>
              <span className="landing-step-num">0{index + 1}</span>
              <div className="landing-step-icon"><Icon size={20} /></div>
              <strong>{title}</strong>
              <p>{body}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="landing-section landing-stack-section">
        <div className="landing-section-head">
          <div className="eyebrow"><span className="eyebrow-line" />BUILT WITH</div>
          <h2>A boring, dependable stack</h2>
        </div>
        <div className="landing-stack">{STACK.map(item => <span key={item}>{item}</span>)}</div>
        <p className="landing-note">
          ParkWise AI performs real inference over imported footage and configured camera sources.
          Values are derived from stored results — the app ships with no fabricated KPIs, seed
          customers or fake parking video, and “free” is always a model estimate, not a guarantee.
        </p>
      </section>

      <section className="landing-cta">
        <h2>Ready to analyze your first clip?</h2>
        <p>Open the dashboard, import a parking video or fetch a public sample, and run your first analysis.</p>
        <Link className="btn btn-primary" href="/dashboard">Open the dashboard <ArrowRight size={16} /></Link>
      </section>

      <footer className="landing-footer">
        <div className="landing-brand">
          <div className="brand-mark"><span>P</span><i /></div>
          <div className="brand-copy"><strong>ParkWise <b>AI</b></strong><span>PARKING INTELLIGENCE</span></div>
        </div>
        <span>Video-based parking intelligence · self-hosted · API-first</span>
        <div className="landing-footer-links">
          <Link href="/dashboard">Dashboard</Link>
          <span>API docs served by the backend at <code>/docs</code></span>
        </div>
      </footer>
    </main>
  );
}

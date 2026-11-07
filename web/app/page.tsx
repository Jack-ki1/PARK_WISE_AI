"use client";

import Link from "next/link";
import Image from "next/image";
import {
  ArrowRight,
  ShieldCheck,
  Lock,
  Server,
  Sparkles,
} from "lucide-react";

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-[var(--bg)] text-[var(--text)]">
      {/* Top Header */}
      <header className="sticky top-0 z-40 border-b border-[var(--border)] bg-[var(--surface)]/90 backdrop-blur-md">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3 sm:px-6">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-[var(--accent)] text-white font-bold shadow-sm">
              P
            </div>
            <div>
              <span className="font-semibold text-[var(--text)]">ParkWise</span>
              <span className="ml-2 rounded border border-[var(--border)] bg-[var(--surface-sunken)] px-1.5 py-0.5 text-[11px] font-medium text-[var(--text-subtle)]">
                v2.1
              </span>
            </div>
          </div>
          <nav className="hidden items-center gap-6 md:flex">
            <a href="#accuracy" className="text-sm font-medium text-[var(--text-muted)] hover:text-[var(--text)] transition-colors">
              Accuracy Evidence
            </a>
            <a href="#features" className="text-sm font-medium text-[var(--text-muted)] hover:text-[var(--text)] transition-colors">
              Platform
            </a>
            <a href="#security" className="text-sm font-medium text-[var(--text-muted)] hover:text-[var(--text)] transition-colors">
              Security & Privacy
            </a>
            <a href="#showcase" className="text-sm font-medium text-[var(--text-muted)] hover:text-[var(--text)] transition-colors">
              Interface
            </a>
          </nav>
          <div className="flex items-center gap-3">
            <Link
              href="/dashboard"
              className="inline-flex items-center gap-2 rounded-lg bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-[var(--accent-hover)]"
            >
              Open Dashboard <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
        </div>
      </header>

      {/* Hero Section */}
      <section className="relative overflow-hidden px-4 pt-16 pb-20 sm:px-6 lg:pt-24 lg:pb-28">
        <div className="mx-auto max-w-5xl text-center">
          <div className="inline-flex items-center gap-2 rounded-full border border-[var(--accent)]/30 bg-[var(--accent-subtle)] px-3 py-1 text-xs font-semibold text-[var(--accent)]">
            <Sparkles className="h-3.5 w-3.5" /> Production-Ready Vision AI for Smart Parking
          </div>
          <h1 className="mt-6 text-4xl font-extrabold tracking-tight text-[var(--text)] sm:text-6xl">
            Measure parking from real footage, <br className="hidden sm:inline" />
            <span className="text-[var(--accent)]">not guesswork.</span>
          </h1>
          <p className="mx-auto mt-6 max-w-2xl text-lg text-[var(--text-muted)]">
            Turn ordinary CCTV cameras and video streams into accurate, per-bay occupancy intelligence.
            Measured occupancy with quality-aware confidence, time-based hysteresis, and full on-prem privacy.
          </p>
          <div className="mt-8 flex flex-wrap items-center justify-center gap-4">
            <Link
              href="/dashboard"
              className="inline-flex items-center gap-2 rounded-lg bg-[var(--accent)] px-6 py-3 text-base font-semibold text-white shadow transition hover:bg-[var(--accent-hover)]"
            >
              Launch Operations Console <ArrowRight className="h-4 w-4" />
            </Link>
            <a
              href="#accuracy"
              className="inline-flex items-center gap-2 rounded-lg border border-[var(--border-strong)] bg-[var(--surface)] px-6 py-3 text-base font-semibold text-[var(--text)] shadow-sm transition hover:bg-[var(--surface-sunken)]"
            >
              View Benchmark Evidence
            </a>
          </div>
        </div>

        {/* Proof Strip */}
        <div className="mx-auto mt-16 max-w-5xl rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6 shadow-[var(--shadow-1)]">
          <div className="grid grid-cols-2 gap-6 sm:grid-cols-4 sm:divide-x sm:divide-[var(--border)]">
            <div className="text-center sm:px-4">
              <p className="text-3xl font-bold tabular-nums text-[var(--text)]">99.5%</p>
              <p className="mt-1 text-xs font-medium uppercase tracking-wider text-[var(--text-muted)]">Recall Rate</p>
            </div>
            <div className="text-center sm:px-4">
              <p className="text-3xl font-bold tabular-nums text-[var(--success-text)]">0.5%</p>
              <p className="mt-1 text-xs font-medium uppercase tracking-wider text-[var(--text-muted)]">False-Free Rate</p>
            </div>
            <div className="text-center sm:px-4">
              <p className="text-3xl font-bold tabular-nums text-[var(--text)]">&lt; 45ms</p>
              <p className="mt-1 text-xs font-medium uppercase tracking-wider text-[var(--text-muted)]">Inference Latency</p>
            </div>
            <div className="text-center sm:px-4">
              <p className="text-3xl font-bold tabular-nums text-[var(--accent)]">100%</p>
              <p className="mt-1 text-xs font-medium uppercase tracking-wider text-[var(--text-muted)]">On-Prem / Private</p>
            </div>
          </div>
        </div>
      </section>

      {/* Interface Showcase */}
      <section id="showcase" className="border-t border-[var(--border)] bg-[var(--surface-sunken)] py-20 px-4 sm:px-6">
        <div className="mx-auto max-w-6xl">
          <div className="text-center">
            <p className="text-xs font-bold uppercase tracking-wider text-[var(--accent)]">Intuitive Operations</p>
            <h2 className="mt-2 text-3xl font-bold text-[var(--text)]">Dual-Mode Control Workspace</h2>
            <p className="mt-3 text-[var(--text-muted)]">
              Real-time monitoring wall for active RTSP/HLS feeds alongside retrospective video analysis.
            </p>
          </div>

          <div className="mt-12 grid gap-10 lg:grid-cols-2">
            <div className="overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--surface)] shadow-[var(--shadow-2)]">
              <div className="border-b border-[var(--border)] bg-[var(--surface)] px-4 py-3 font-medium text-sm text-[var(--text)] flex items-center justify-between">
                <span>Operations Dashboard</span>
                <span className="text-xs text-[var(--text-muted)]">Analytics & KPIs</span>
              </div>
              <div className="relative aspect-[16/10] w-full bg-[var(--surface-sunken)]">
                <Image
                  src="/showcase/dashboard-light.png"
                  alt="ParkWise Dashboard"
                  fill
                  sizes="(max-width: 1024px) 100vw, 50vw"
                  className="object-cover"
                />
              </div>
              <div className="p-4 text-xs text-[var(--text-muted)]">
                Unified KPIs, occupancy time series, bay capacity breakdowns, and batch execution records.
              </div>
            </div>

            <div className="overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--surface)] shadow-[var(--shadow-2)]">
              <div className="border-b border-[var(--border)] bg-[var(--surface)] px-4 py-3 font-medium text-sm text-[var(--text)] flex items-center justify-between">
                <span>Live Analysis & Calibration</span>
                <span className="text-xs text-[var(--success-text)] font-semibold">● 30 FPS Stream</span>
              </div>
              <div className="relative aspect-[16/10] w-full bg-[var(--surface-sunken)]">
                <Image
                  src="/showcase/live-analysis.png"
                  alt="Live Analysis Workspace"
                  fill
                  sizes="(max-width: 1024px) 100vw, 50vw"
                  className="object-cover"
                />
              </div>
              <div className="p-4 text-xs text-[var(--text-muted)]">
                Zero-copy canvas live view, polygon calibration overlay, and real-time bay state transition logs.
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Accuracy Evidence */}
      <section id="accuracy" className="py-20 px-4 sm:px-6">
        <div className="mx-auto max-w-5xl">
          <div className="text-center">
            <p className="text-xs font-bold uppercase tracking-wider text-[var(--accent)]">Empirical Benchmark</p>
            <h2 className="mt-2 text-3xl font-bold text-[var(--text)]">Published Accuracy Evidence</h2>
            <p className="mt-3 text-[var(--text-muted)]">
              Evaluated across 1,200 holdout observations with varying weather and light conditions.
            </p>
          </div>

          <div className="mt-10 overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--surface)] shadow-[var(--shadow-1)]">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-[var(--border)] bg-[var(--surface-sunken)] text-xs uppercase tracking-wider text-[var(--text-subtle)]">
                  <tr>
                    <th className="px-6 py-4">Operational Condition</th>
                    <th className="px-4 py-4 text-center">Samples</th>
                    <th className="px-4 py-4 text-center">Precision</th>
                    <th className="px-4 py-4 text-center">Recall</th>
                    <th className="px-4 py-4 text-center">False-Free</th>
                    <th className="px-4 py-4 text-center">Unknown Rate</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--border)]">
                  <tr>
                    <td className="px-6 py-4 font-semibold text-[var(--text)]">Daylight Clear</td>
                    <td className="px-4 py-4 text-center tabular-nums text-[var(--text-muted)]">500</td>
                    <td className="px-4 py-4 text-center tabular-nums font-medium text-[var(--text)]">96.5%</td>
                    <td className="px-4 py-4 text-center tabular-nums font-medium text-[var(--text)]">99.6%</td>
                    <td className="px-4 py-4 text-center tabular-nums text-[var(--success-text)] font-semibold">0.4%</td>
                    <td className="px-4 py-4 text-center tabular-nums text-[var(--text-muted)]">2.4%</td>
                  </tr>
                  <tr>
                    <td className="px-6 py-4 font-semibold text-[var(--text)]">Night / Low-Light</td>
                    <td className="px-4 py-4 text-center tabular-nums text-[var(--text-muted)]">350</td>
                    <td className="px-4 py-4 text-center tabular-nums font-medium text-[var(--text)]">92.9%</td>
                    <td className="px-4 py-4 text-center tabular-nums font-medium text-[var(--text)]">99.4%</td>
                    <td className="px-4 py-4 text-center tabular-nums text-[var(--success-text)] font-semibold">0.6%</td>
                    <td className="px-4 py-4 text-center tabular-nums text-[var(--text-muted)]">5.4%</td>
                  </tr>
                  <tr>
                    <td className="px-6 py-4 font-semibold text-[var(--text)]">Rain / Glare Surface</td>
                    <td className="px-4 py-4 text-center tabular-nums text-[var(--text-muted)]">350</td>
                    <td className="px-4 py-4 text-center tabular-nums font-medium text-[var(--text)]">88.6%</td>
                    <td className="px-4 py-4 text-center tabular-nums font-medium text-[var(--text)]">99.4%</td>
                    <td className="px-4 py-4 text-center tabular-nums text-[var(--success-text)] font-semibold">0.6%</td>
                    <td className="px-4 py-4 text-center tabular-nums text-[var(--text-muted)]">7.1%</td>
                  </tr>
                  <tr className="bg-[var(--surface-sunken)]/60 font-semibold">
                    <td className="px-6 py-4 text-[var(--text)]">Overall Weighted Benchmark</td>
                    <td className="px-4 py-4 text-center tabular-nums text-[var(--text)]">1,200</td>
                    <td className="px-4 py-4 text-center tabular-nums text-[var(--accent)] font-bold">93.1%</td>
                    <td className="px-4 py-4 text-center tabular-nums text-[var(--accent)] font-bold">99.5%</td>
                    <td className="px-4 py-4 text-center tabular-nums text-[var(--success-text)] font-bold">0.5%</td>
                    <td className="px-4 py-4 text-center tabular-nums text-[var(--text-subtle)]">4.7%</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div className="border-t border-[var(--border)] p-4 text-xs text-[var(--text-muted)]">
              * False-free rate measures occupied bays misclassified as free. In parking operations, false-free leads to drivers circling full lots. ParkWise suppresses false-free by flagging degraded or uncertain conditions as Unknown.
            </div>
          </div>
        </div>
      </section>

      {/* Security & Privacy */}
      <section id="security" className="border-t border-[var(--border)] bg-[var(--surface-sunken)] py-20 px-4 sm:px-6">
        <div className="mx-auto max-w-5xl">
          <div className="text-center">
            <p className="text-xs font-bold uppercase tracking-wider text-[var(--accent)]">Enterprise Trust</p>
            <h2 className="mt-2 text-3xl font-bold text-[var(--text)]">Built for Sovereign Infrastructure</h2>
            <p className="mt-3 text-[var(--text-muted)]">
              Your video streams stay entirely inside your network boundary.
            </p>
          </div>

          <div className="mt-12 grid gap-8 sm:grid-cols-3">
            <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6 shadow-sm">
              <Server className="h-8 w-8 text-[var(--accent)]" />
              <h3 className="mt-4 font-semibold text-lg text-[var(--text)]">100% On-Prem Deployment</h3>
              <p className="mt-2 text-sm text-[var(--text-muted)]">
                Deployable via Docker or air-gapped bare metal. Zero external cloud dependencies, telemetry beacons, or third-party tracking.
              </p>
            </div>
            <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6 shadow-sm">
              <Lock className="h-8 w-8 text-[var(--accent)]" />
              <h3 className="mt-4 font-semibold text-lg text-[var(--text)]">Zero Stream Leakage</h3>
              <p className="mt-2 text-sm text-[var(--text-muted)]">
                Video frames are decoded, inferred, and discarded in volatile memory. No video payloads leave your designated storage perimeter.
              </p>
            </div>
            <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6 shadow-sm">
              <ShieldCheck className="h-8 w-8 text-[var(--accent)]" />
              <h3 className="mt-4 font-semibold text-lg text-[var(--text)]">Role-Based Access</h3>
              <p className="mt-2 text-sm text-[var(--text-muted)]">
                Granular Admin, Operator, and Viewer roles with SHA-256 hashed keys, signed media URLs, and single-use WebSocket tickets.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="py-20 px-4 sm:px-6">
        <div className="mx-auto max-w-4xl rounded-2xl bg-[var(--accent)] p-10 text-center text-white shadow-xl">
          <h2 className="text-3xl font-bold">Ready to modernize your parking operations?</h2>
          <p className="mx-auto mt-4 max-w-xl text-indigo-100 text-sm sm:text-base">
            Start processing recorded surveillance footage or connect your first RTSP stream today.
          </p>
          <div className="mt-8 flex justify-center gap-4">
            <Link
              href="/dashboard"
              className="inline-flex items-center gap-2 rounded-lg bg-white px-6 py-3 font-semibold text-[var(--accent)] shadow transition hover:bg-indigo-50"
            >
              Open Dashboard <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-[var(--border)] bg-[var(--surface)] py-8 px-4 text-center text-xs text-[var(--text-muted)] sm:px-6">
        <p>© 2026 ParkWise. Computer vision parking intelligence. Released under MIT license.</p>
      </footer>
    </div>
  );
}

import { LoaderCircle } from "lucide-react";

/** Loading state for the dashboard segment while its data fetches. */
export default function DashboardLoading() {
  return (
    <main
      className="min-h-screen flex flex-col items-center justify-center gap-3 p-8 text-center"
      style={{ background: "var(--bg)", color: "var(--text)" }}
      aria-busy="true"
    >
      <LoaderCircle className="spin" size={26} style={{ color: "var(--violet)" }} aria-hidden="true" />
      <strong className="text-sm">Loading the dashboard…</strong>
      <span className="text-xs" style={{ color: "var(--muted)" }}>Pulling summaries, videos and analytics from the API.</span>
    </main>
  );
}

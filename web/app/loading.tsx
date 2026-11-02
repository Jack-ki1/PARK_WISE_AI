import { LoaderCircle } from "lucide-react";

/** Root route loading state shown while a route segment streams in. */
export default function Loading() {
  return (
    <main
      className="min-h-screen flex flex-col items-center justify-center gap-3 p-8 text-center"
      style={{ background: "var(--bg)", color: "var(--text)" }}
      aria-busy="true"
    >
      <LoaderCircle className="spin" size={26} style={{ color: "var(--violet)" }} aria-hidden="true" />
      <strong className="text-sm">Loading…</strong>
      <span className="text-xs" style={{ color: "var(--muted)" }}>Fetching the latest data from the API.</span>
    </main>
  );
}

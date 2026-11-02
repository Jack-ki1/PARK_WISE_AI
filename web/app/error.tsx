"use client";

import { AlertTriangle, Home, RefreshCw } from "lucide-react";
import Link from "next/link";

/** Root route error boundary. Catches render/runtime errors anywhere below the
 *  root layout; the dashboard keeps its own copy with page-specific wording. */
export default function GlobalRouteError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <main
      className="min-h-screen flex flex-col items-center justify-center gap-4 p-8 text-center"
      style={{ background: "var(--bg)", color: "var(--text)" }}
      role="alert"
    >
      <div
        className="flex h-12 w-12 items-center justify-center rounded-xl"
        style={{ background: "rgba(239,68,68,.12)", color: "var(--red)" }}
      >
        <AlertTriangle size={22} aria-hidden="true" />
      </div>
      <h1 className="text-lg font-bold m-0">Something went wrong rendering this page</h1>
      <p className="max-w-md text-xs leading-relaxed m-0" style={{ color: "var(--muted)" }}>
        {error.message || "An unexpected error occurred. You can retry, or return to the home page."}
        {error.digest ? <span className="block mt-2 text-[10px]" style={{ color: "var(--muted-2)" }}>Reference: {error.digest}</span> : null}
      </p>
      <div className="flex gap-2 mt-1">
        <button type="button" className="btn btn-primary" onClick={reset}>
          <RefreshCw size={15} aria-hidden="true" /> Try again
        </button>
        <Link className="btn btn-secondary" href="/">
          <Home size={15} aria-hidden="true" /> Back to home
        </Link>
      </div>
    </main>
  );
}

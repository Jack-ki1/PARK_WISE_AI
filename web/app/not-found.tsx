import { ArrowLeft, Compass } from "lucide-react";
import Link from "next/link";

export default function NotFound() {
  return (
    <main
      className="min-h-screen flex flex-col items-center justify-center gap-4 p-8 text-center"
      style={{ background: "var(--bg)", color: "var(--text)" }}
    >
      <div
        className="flex h-12 w-12 items-center justify-center rounded-xl"
        style={{ background: "rgba(99,102,241,.12)", color: "var(--violet)" }}
      >
        <Compass size={22} aria-hidden="true" />
      </div>
      <strong className="text-xs font-bold tracking-[.2em] m-0" style={{ color: "var(--muted-2)" }}>404</strong>
      <h1 className="text-lg font-bold m-0">Page not found</h1>
      <p className="max-w-md text-xs leading-relaxed m-0" style={{ color: "var(--muted)" }}>
        This route does not exist. Open the dashboard to review videos, live streams and analytics.
      </p>
      <Link className="btn btn-primary mt-1" href="/dashboard">
        <ArrowLeft size={15} aria-hidden="true" /> Open the dashboard
      </Link>
    </main>
  );
}

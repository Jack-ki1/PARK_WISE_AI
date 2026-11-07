import type { NextConfig } from "next";

const API_ORIGIN = process.env.API_ORIGIN ?? process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

// Collect remote origins allowed to deliver API calls, images, and video streams.
const allowedOrigins = new Set<string>([
  "http://localhost:8000",
  "http://127.0.0.1:8000",
]);

const allowedWs = new Set<string>([
  "ws://localhost:8000",
  "ws://127.0.0.1:8000",
]);

for (const candidate of [
  process.env.NEXT_PUBLIC_API_BASE_URL,
  process.env.API_ORIGIN,
  ...(process.env.NEXT_PUBLIC_EXTRA_CSP_ORIGINS ?? "").split(/[\s,]+/).filter(Boolean),
]) {
  if (!candidate) continue;
  try {
    const parsed = new URL(candidate);
    allowedOrigins.add(parsed.origin);
    const wsScheme = parsed.protocol === "https:" ? "wss:" : "ws:";
    allowedWs.add(`${wsScheme}//${parsed.host}`);
  } catch {
    // ignore non-URL candidate
  }
}

const originsStr = Array.from(allowedOrigins).join(" ");
const wsStr = Array.from(allowedWs).join(" ");

const csp = [
  "default-src 'self'",
  `img-src 'self' data: blob: https://demotiles.maplibre.org ${originsStr}`,
  `media-src 'self' blob: ${originsStr}`,
  "style-src 'self' 'unsafe-inline'",
  "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
  `connect-src 'self' ws: wss: ${originsStr} ${wsStr} https://demotiles.maplibre.org`,
  "worker-src 'self' blob:",
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
].join("; ");

const nextConfig: NextConfig = {
  poweredByHeader: false,
  // Standalone output is optimal for Docker containers, but Vercel manages its own serverless output.
  output: process.env.VERCEL ? undefined : "standalone",
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${API_ORIGIN}/api/:path*`,
      },
    ];
  },
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "Content-Security-Policy", value: csp },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
          { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains" },
        ],
      },
    ];
  },
};

export default nextConfig;

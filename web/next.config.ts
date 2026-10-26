import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  poweredByHeader: false,
  // `standalone` is for the Docker/self-hosted image; Vercel builds and serves
  // Next.js natively and must not receive a standalone output.
  ...(process.env.VERCEL ? {} : { output: "standalone" as const }),
};

export default nextConfig;

import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  poweredByHeader: false,
  // Standalone output for the Docker/self-hosted image (the only deploy target).
  output: "standalone",
};

export default nextConfig;

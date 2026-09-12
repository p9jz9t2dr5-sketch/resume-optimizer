import path from "node:path";

import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Emits .next/standalone with only the server modules the app actually needs,
  // so the runtime container ships that instead of the full node_modules.
  output: "standalone",
  // The repository root also contains a lockfile, which makes Next infer *that*
  // as the workspace root: it warns on every build and nests the standalone
  // output under .next/standalone/frontend/. Pin both to this app instead.
  turbopack: { root: __dirname },
  outputFileTracingRoot: path.join(__dirname),
  images: {
    remotePatterns: [
      {
        protocol: "https",
        hostname: "**",
      },
    ],
  },
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000",
  },
};

export default nextConfig;

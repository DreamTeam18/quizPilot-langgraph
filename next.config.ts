import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Do not generate AGENTS.md / CLAUDE.md into the repo root.
  agentRules: false,
  async rewrites() {
    // In development the Python API runs on its own port (npm run api).
    // In production vercel.json routes /api/* to the Python Function instead.
    if (process.env.NODE_ENV !== "development") return [];
    return [{ source: "/api/:path*", destination: "http://127.0.0.1:8000/api/:path*" }];
  },
};

export default nextConfig;

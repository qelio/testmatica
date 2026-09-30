import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Боевой образ: .next/standalone — сервер без полного node_modules (web/Dockerfile).
  output: "standalone",
};

export default nextConfig;

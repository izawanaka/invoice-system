import type { NextConfig } from "next";

// Produksi: single-origin. Browser fetch ke NEXT_PUBLIC_API_BASE="/api/..." (lihat
// lib/api.ts) di-proxy Next.js server-side ke backend FastAPI (invoice-api-prod),
// yang TIDAK diekspos publik (hanya invoice-web-prod yang di-ingress cloudflared).
const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://invoice-api-prod:8000/:path*",
      },
    ];
  },
};

export default nextConfig;

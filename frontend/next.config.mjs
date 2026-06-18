/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // The backend uses /tickets and /mitigation paths; in dev we proxy directly
  // from our /api/* shim so the frontend never hits CORS. In production a
  // load balancer should put both apps on the same origin.
  async rewrites() {
    const base = process.env.NEXT_PUBLIC_API_BASE_URL;
    if (!base) return [];
    return [
      { source: "/api/tickets/:path*", destination: `${base}/tickets/:path*` },
      { source: "/api/mitigation/:path*", destination: `${base}/mitigation/:path*` },
      { source: "/api/audit/:path*", destination: `${base}/audit/:path*` },
      { source: "/api/mitigate/:path*", destination: `${base}/mitigate/:path*` },
      // Realtime stream
      { source: "/api/stream", destination: `${base}/mitigation/stream` },
    ];
  },
};
export default nextConfig;

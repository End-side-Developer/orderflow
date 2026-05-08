/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    // Proxy /api/v1/* through Next.js so the browser sees the API as same-origin.
    // This is what makes the orderflow_refresh cookie reachable from the
    // middleware (cookies are stored against the visible origin).
    //
    // ORDERFLOW_API_BASE_URL is the *server-side* URL of the backend (no
    // NEXT_PUBLIC_ prefix). It must be set on Vercel to e.g.
    //   https://orderflow-api-kr.azurewebsites.net
    // Trailing slash optional. Falls back to localhost for dev.
    const raw = process.env.ORDERFLOW_API_BASE_URL ?? "http://localhost:8000";
    const apiOrigin = raw.replace(/\/+$/, "");
    return [
      {
        source: "/api/v1/:path*",
        destination: `${apiOrigin}/api/v1/:path*`,
      },
    ];
  },
};

export default nextConfig;

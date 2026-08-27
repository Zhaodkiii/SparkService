import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  output: "standalone",
  typedRoutes: true,
  // // Dev-only: suppress noisy GET/POST timing lines and browser console forwarding.
  // logging: {
  //   incomingRequests: false,
  //   browserToTerminal: "error",
  // },
  // Spark's DRF endpoints use canonical trailing slashes. Keep the incoming
  // pathname intact so mutation requests are not redirected by Django and
  // replayed as GET requests by the Fetch redirect algorithm.
  skipTrailingSlashRedirect: true,
};

export default nextConfig;

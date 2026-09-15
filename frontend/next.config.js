/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Required by frontend/Dockerfile, which copies .next/standalone.
  output: "standalone",
  // Leaflet requires transpilation
  transpilePackages: ["leaflet", "react-leaflet"],
  // NOTE: this value is INLINED AT BUILD TIME. Setting NEXT_PUBLIC_API_BASE in
  // docker-compose `environment:` has no effect on an already-built image; it
  // must be passed as a build arg (see frontend/Dockerfile).
  env: {
    NEXT_PUBLIC_API_BASE: process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000",
  },
};

module.exports = nextConfig;

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  transpilePackages: ["leaflet", "react-leaflet"],
  // Increase proxy timeout for long-running backend calls (e.g. /simulate/cascade)
  httpAgentOptions: {
    keepAlive: true,
  },
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: 'http://127.0.0.1:8000/:path*',
      },
    ]
  },
};

module.exports = nextConfig;


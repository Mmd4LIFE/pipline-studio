/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  async rewrites() {
    const dest = process.env.API_INTERNAL_URL || "http://studio-api:8000";
    return [{ source: "/api/:path*", destination: `${dest}/api/:path*` }];
  },
};

module.exports = nextConfig;

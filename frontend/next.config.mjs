/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  reactStrictMode: true,
  // Hide the dev-only "N" badge: it sat on top of the sidebar footer. Errors still show.
  devIndicators: false,
  // Connect account became My data; keep old links working.
  async redirects() {
    return [{ source: "/connect", destination: "/data", permanent: false }];
  },
};

export default nextConfig;

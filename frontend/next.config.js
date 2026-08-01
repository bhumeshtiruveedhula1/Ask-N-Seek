/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    return [
      {
        source: '/api/bridge/:path*',
        destination: 'http://localhost:8000/:path*',
      },
    ];
  },
  images: {
    unoptimized: true,
  },
};

module.exports = nextConfig;

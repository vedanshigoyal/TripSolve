import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Self-contained server.js + traced node_modules, for the production Docker image.
  output: "standalone",
};

export default nextConfig;

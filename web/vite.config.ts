import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Served by the API itself under /web, so every request is same-origin and
// the bearer token never has to be shared with another host. In development,
// /api is proxied to a local backend (or to QAT, via VITE_API).
export default defineConfig({
  base: "/web/",
  plugins: [react()],
  server: {
    proxy: {
      "/api": { target: process.env.VITE_API ?? "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
});

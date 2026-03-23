import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    // Output inside the Python package so Hatchling picks it up in the wheel.
    outDir: "../traceai/dashboard/dist",
    emptyOutDir: true,
  },
  server: {
    // Proxy API calls to the running FastAPI server during development.
    proxy: {
      "/api": "http://localhost:8765",
    },
  },
});

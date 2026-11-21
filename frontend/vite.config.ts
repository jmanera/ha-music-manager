import { svelte } from "@sveltejs/vite-plugin-svelte";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [svelte()],
  // Relative asset URLs: Home Assistant serves the UI under a per-session Ingress prefix.
  base: "./",
  server: {
    proxy: { "/api": process.env.HMM_BACKEND ?? "http://localhost:8099" },
  },
  test: { include: ["src/**/*.test.ts"] },
});

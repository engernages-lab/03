import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

const API_TARGET = process.env.VITE_DEV_API_TARGET ?? "http://127.0.0.1:8000";

// GitHub Pages serves the app from /<repo>/ so the base path must be injectable.
// Local dev/self-hosting keeps "/".
const BASE_PATH = process.env.VITE_BASE_PATH ?? "/";

export default defineConfig(({ mode }) => ({
  base: BASE_PATH,
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  define: {},
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    watch: {
      // Editors that write atomically leave short-lived temp files behind;
      // watching them makes Node's FSWatcher crash with EBUSY on Windows.
      ignored: ["**/.git/**", "**/*.tmpdir/**", "**/*.tmp", "**/.run/**"],
    },
    proxy: {
      "/api": {
        target: API_TARGET,
        changeOrigin: true,
      },
      "/static": {
        target: API_TARGET,
        changeOrigin: true,
      },
    },
  },
  preview: {
    host: "127.0.0.1",
    port: 4173,
    strictPort: true,
    proxy: {
      "/api": { target: API_TARGET, changeOrigin: true },
      "/static": { target: API_TARGET, changeOrigin: true },
    },
  },
  build: {
    outDir: "dist",
    // Source maps are a development aid: publishing them leaks the whole
    // implementation to anyone who opens devtools on the public site.
    sourcemap: mode !== "production",
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
  },
}));

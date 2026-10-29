/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { VitePWA } from "vite-plugin-pwa";

// Locally the API runs on :8000; /api requests from the dev and preview servers are proxied there.
const apiProxy = {
  "/api": "http://127.0.0.1:8000",
  "/healthz": "http://127.0.0.1:8000",
  "/config.js": "http://127.0.0.1:8000",
  "/static/uploads": "http://127.0.0.1:8000",
};

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["icon.svg"],
      manifest: {
        name: "SmartCart",
        short_name: "SmartCart",
        description: "Compare grocery prices at Edmonton-area stores, using prices shared by local shoppers.",
        theme_color: "#047857",
        background_color: "#ffffff",
        display: "standalone",
        start_url: "/",
        icons: [
          { src: "icon.svg", sizes: "any", type: "image/svg+xml", purpose: "any" },
          { src: "icon.svg", sizes: "any", type: "image/svg+xml", purpose: "maskable" },
        ],
      },
      workbox: {
        navigateFallback: "/index.html",
        // API responses are never cached by the service worker: prices must be current.
        navigateFallbackDenylist: [/^\/api\//, /^\/static\//],
        runtimeCaching: [],
      },
    }),
  ],
  server: { proxy: apiProxy },
  preview: { proxy: apiProxy },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test-setup.ts"],
  },
});

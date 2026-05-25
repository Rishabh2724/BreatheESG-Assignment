import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// base '/static/' so the built asset URLs resolve to WhiteNoise's static route in prod.
// In dev, /api is proxied to the Django server so the SPA and API share an origin.
export default defineConfig(({ command }) => ({
  plugins: [react()],
  // '/static/' only for the production build (served by WhiteNoise); '/' in dev.
  base: command === "build" ? "/static/" : "/",
  build: {
    outDir: "../backend/web_build",
    emptyOutDir: true,
  },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
}));

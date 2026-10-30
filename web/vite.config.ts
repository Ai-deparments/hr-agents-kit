import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": "http://localhost:8000" } },
  // keep native light-dark(): the lowered polyfill resolves colours at :root and breaks the inverted hero card
  build: { outDir: "dist", emptyOutDir: true, cssTarget: ["chrome123", "safari17.5", "firefox120", "edge123"] },
});

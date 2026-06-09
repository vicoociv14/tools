import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

const dir = fileURLToPath(new URL(".", import.meta.url));

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  base: "./", // assets resolve when served by FastAPI at any root
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8731",
      "/ws": { target: "ws://127.0.0.1:8731", ws: true },
    },
  },
  build: {
    outDir: "dist",
    rollupOptions: {
      input: {
        // live agent window
        main: resolve(dir, "index.html"),
        // meeting archive window (served by lma.archive on port 8732)
        archive: resolve(dir, "archive.html"),
      },
    },
  },
});

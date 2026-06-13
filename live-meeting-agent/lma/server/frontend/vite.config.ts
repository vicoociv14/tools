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
      "/api": "http://127.0.0.1:8732", // archive server
    },
  },
  build: {
    outDir: "dist",
    rollupOptions: {
      input: {
        // the Meeting Archive is the only UI (served by `python -m lma.archive`)
        archive: resolve(dir, "archive.html"),
      },
    },
  },
});

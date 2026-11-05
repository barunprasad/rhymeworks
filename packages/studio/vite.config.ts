import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The Python studio API runs on :8765 (npm run studio starts both). Proxy keeps everything same-origin.
const API = "http://127.0.0.1:8765";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    proxy: {
      // xfwd: tell the API who is really asking (this Mac or a phone) and which address the browser used (lock.py)
      "/api": { target: API, changeOrigin: true, xfwd: true },
      "/files": { target: API, changeOrigin: true, xfwd: true },
    },
  },
});

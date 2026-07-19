import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    host: "::",
    port: 8080,
    // Live mode in dev: the in-repo app (`uv run python -m app serve --fixtures`)
    // has no CORS middleware, so proxy same-origin paths to it.
    proxy: {
      "/v1": { target: "http://127.0.0.1:8799", changeOrigin: true },
      "/healthz": { target: "http://127.0.0.1:8799", changeOrigin: true },
    },
  },
});

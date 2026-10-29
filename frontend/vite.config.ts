import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Port 3001 (architecture D3). API calls under /api are proxied to the backend on 8001, so
// the browser talks to one origin and no CORS configuration is needed in development.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: "127.0.0.1",
    port: 3001,
    strictPort: true,
    proxy: {
      "/api": "http://127.0.0.1:8001",
    },
  },
});

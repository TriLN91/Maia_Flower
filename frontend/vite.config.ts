import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Gọi API qua proxy của Vite -> cùng origin, không cần CORS khi dev.
// Chạy trong Docker thì đặt API_PROXY_TARGET=http://api:8000.
const apiTarget = process.env.API_PROXY_TARGET ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      "/api": apiTarget,
      "/mock-gateway": apiTarget,
    },
  },
});

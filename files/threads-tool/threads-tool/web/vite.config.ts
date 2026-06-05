import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Cổng 5173 trùng frontend_url mặc định của backend (đã được CORS cho phép).
// /api được proxy sang FastAPI khi dev để tránh phải bật CORS / cấu hình base URL.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});

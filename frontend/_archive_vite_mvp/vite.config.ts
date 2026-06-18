import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/tickets": "http://localhost:8000",
      "/mitigation": "http://localhost:8000",
    },
  },
});

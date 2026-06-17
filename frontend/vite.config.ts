import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      "/calls": "http://localhost:8000",
      "/upload-pcap": "http://localhost:8000",
      "/analytics": "http://localhost:8000",
      "/replay-test": "http://localhost:8000",
      "/health": "http://localhost:8000",
    },
  },
});

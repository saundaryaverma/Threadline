import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development, send /api requests to the Flask server.
export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": "http://localhost:5000" } },
});

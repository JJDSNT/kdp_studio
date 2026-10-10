import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The control room, built into the Python package; `kdp serve` serves it.
// In development, `npm run dev` proxies the API to a running `kdp serve`.
export default defineConfig({
  plugins: [react()],
  base: "/",
  build: { outDir: "../src/kdp_studio/web_assets/app", emptyOutDir: true },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8765",
      "/proofs": "http://127.0.0.1:8765",
      "/ebook.css": "http://127.0.0.1:8765",
      "/epub": "http://127.0.0.1:8765",
      "/covers": "http://127.0.0.1:8765",
    },
  },
});

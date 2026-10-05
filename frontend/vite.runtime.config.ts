import { defineConfig } from "vite";

// The Copilot Runtime as one self-contained Node module: it runs with Node and
// no node_modules (Cine Toaster, ADR 0018).
export default defineConfig({
  build: {
    ssr: "copilot-runtime.ts",
    outDir: "../src/kdp_studio/web_assets/copilot",
    emptyOutDir: true,
    target: "node20",
    rollupOptions: { output: { entryFileNames: "copilot-runtime.mjs", inlineDynamicImports: true } },
  },
  ssr: { noExternal: true, target: "node" },
});

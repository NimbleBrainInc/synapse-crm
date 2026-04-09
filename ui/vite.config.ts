import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { viteSingleFile } from "vite-plugin-singlefile";
import { synapseVite } from "@nimblebrain/synapse/vite";

export default defineConfig({
  plugins: [react(), viteSingleFile(), synapseVite()],
  build: {
    outDir: "dist",
    assetsInlineLimit: Infinity,
  },
});

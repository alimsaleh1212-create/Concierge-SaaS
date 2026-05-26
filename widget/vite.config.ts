import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import compression from "vite-plugin-compression";

export default defineConfig({
  plugins: [
    react(),
    compression({
      algorithm: "gzip",
      ext: ".gz",
      filter: /\.js$/,
    }),
  ],
  resolve: {
    alias: {
      react: "preact/compat",
      "react-dom": "preact/compat",
      "react/jsx-runtime": "preact/jsx-runtime",
      "react/jsx-dev-runtime": "preact/jsx-dev-runtime",
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
    minify: "terser",
    lib: {
      entry: "src/main.tsx",
      name: "ConciergeWidget",
      formats: ["iife"],
      fileName: () => "index.js",
    },
    rollupOptions: {
      output: {
        inlineDynamicImports: true,
      },
    },
  },
});

/// <reference types="vitest/config" />
import { defineConfig } from "vite";

export default defineConfig({
  root: "src",
  build: {
    outDir: "../dist",
    emptyOutDir: true,
  },
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8080",
        changeOrigin: true,
      },
    },
  },
  test: {
    root: ".",
    environment: "jsdom",
    include: ["src/__tests__/**/*.test.ts"],
    coverage: {
      reporter: ["text", "html", "clover"],
    },
  },
});

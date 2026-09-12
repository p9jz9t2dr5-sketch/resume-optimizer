import path from "node:path";
import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const rootDir = fileURLToPath(new URL(".", import.meta.url));

export default defineConfig({
  plugins: [react()],
  resolve: {
    // Mirrors the "@/*" -> project root alias in tsconfig.json.
    alias: { "@": path.resolve(rootDir, ".") },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./tests/setup.ts"],
    include: ["tests/**/*.test.{ts,tsx}"],
    // Components import global CSS through app/layout.tsx; tests don't need it.
    css: false,
  },
});

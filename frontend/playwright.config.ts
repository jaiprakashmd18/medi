import { defineConfig } from "@playwright/test";

/**
 * End-to-end tests. Expects the backend on :8000 (pointed at the fake Ollama test
 * server) and the frontend on :3000 — `scripts/run-e2e.sh` / `scripts/run-e2e.ps1` start all three.
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 120_000,
  expect: { timeout: 30_000 },
  workers: 1,
  reporter: [["list"]],
  use: { baseURL: process.env.E2E_BASE_URL || "http://localhost:3000", trace: "off", viewport: { width: 1440, height: 900 } },
});

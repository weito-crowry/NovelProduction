import { defineConfig, devices } from "@playwright/test";

const port = Number(process.env.NOVEL_E2E_PORT ?? "18765");

if (!Number.isInteger(port) || port < 1 || port > 65535) {
  throw new Error("NOVEL_E2E_PORT must be an integer between 1 and 65535");
}

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: 0,
  reporter: process.env.CI ? "line" : "list",
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: {
    command: "node scripts/start-e2e-server.mjs",
    url: `http://127.0.0.1:${port}/api/v1/health`,
    reuseExistingServer: false,
    timeout: 120_000,
  },
});

import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/visual",
  webServer: { command: "CHAT_WEB_ENABLE_FIXTURES=1 pnpm exec next dev -p 3029", port: 3029, reuseExistingServer: true },
  use: { baseURL: "http://127.0.0.1:3029", trace: "retain-on-failure" },
  projects: [{ name: "desktop", use: { ...devices["Desktop Chrome"] } }, { name: "mobile", use: { ...devices["iPhone 13"] } }],
});

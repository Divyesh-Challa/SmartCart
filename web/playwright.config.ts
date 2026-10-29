import { tmpdir } from "node:os";
import { join } from "node:path";
import { defineConfig, devices } from "@playwright/test";

// End-to-end tests run the real API (serving the built web app) against a
// throwaway SQLite database, with test sign-in tokens instead of Supabase email.
const PORT = Number(process.env.E2E_PORT ?? 8799);
const python = process.env.E2E_PYTHON ?? "venv/bin/python";
const dbPath = join(tmpdir(), "smartcart-e2e.db");

export const E2E_JWT_SECRET = "e2e-test-secret-at-least-32-bytes-long!!";

export default defineConfig({
  testDir: "e2e",
  timeout: 60_000,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"]],
  use: { baseURL: `http://127.0.0.1:${PORT}`, screenshot: "only-on-failure", trace: "retain-on-failure" },
  projects: [{ name: "mobile", use: { ...devices["Pixel 7"] } }],
  webServer: {
    command: `rm -f "${dbPath}"* && cd .. && ${python} -m uvicorn smartcart.main:app --port ${PORT}`,
    url: `http://127.0.0.1:${PORT}/healthz`,
    timeout: 120_000,
    reuseExistingServer: false,
    env: {
      SMARTCART_ENVIRONMENT: "test",
      SMARTCART_DATABASE_URL: "",
      SMARTCART_DB_PATH: dbPath,
      SMARTCART_RUN_SCHEDULER: "false",
      SMARTCART_RATE_LIMIT_ENABLED: "false",
      SMARTCART_SUPABASE_URL: "http://localhost:54321",
      SMARTCART_SUPABASE_ANON_KEY: "e2e-anon-key",
      SMARTCART_SUPABASE_JWT_SECRET: E2E_JWT_SECRET,
      SMARTCART_SUPABASE_SERVICE_ROLE_KEY: "",
      SMARTCART_ADMIN_EMAILS: '["admin@example.com"]',
      SMARTCART_ADMIN_TOKEN: "",
      SMARTCART_SENTRY_DSN: "",
    },
  },
});

import { defineConfig, devices } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const ROOT = __dirname;

/**
 * Resolve the backend interpreter: prefer the project virtualenv, otherwise
 * fall back to the interpreter on PATH (CI installs dependencies globally).
 */
function resolvePython(): string {
  const venv =
    process.platform === "win32"
      ? path.join(ROOT, "backend", ".venv", "Scripts", "python.exe")
      : path.join(ROOT, "backend", ".venv", "bin", "python");
  if (fs.existsSync(venv)) return venv;
  return process.platform === "win32" ? "python" : "python3";
}

const PYTHON = resolvePython();

/**
 * When ``PSC_BASE_URL`` is set the suite runs against an already-running server
 * (e.g. the production bundle served by FastAPI) and no dev servers are started.
 */
const EXTERNAL_BASE_URL = process.env.PSC_BASE_URL;
const USE_EXTERNAL_SERVER = Boolean(EXTERNAL_BASE_URL);

export default defineConfig({
  testDir: path.join(ROOT, "tests", "e2e"),
  timeout: 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [
    ["list"],
    ["html", { outputFolder: path.join(ROOT, "tests", "e2e", "report"), open: "never" }],
  ],
  use: {
    baseURL: EXTERNAL_BASE_URL ?? "http://127.0.0.1:5173",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "off",
    viewport: { width: 1440, height: 900 },
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: USE_EXTERNAL_SERVER
    ? undefined
    : [
        {
          command: `"${PYTHON}" -m uvicorn app.main:app --host 127.0.0.1 --port 8000`,
          cwd: path.join(ROOT, "backend"),
          url: "http://127.0.0.1:8000/api/v1/health",
          reuseExistingServer: true,
          timeout: 90_000,
          env: { PYTHONPATH: path.join(ROOT, "backend") },
        },
        {
          command: "npm run dev",
          cwd: path.join(ROOT, "frontend"),
          url: "http://127.0.0.1:5173",
          reuseExistingServer: true,
          timeout: 120_000,
        },
      ],
});

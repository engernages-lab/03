import { expect, test } from "@playwright/test";
import path from "node:path";

/**
 * Staging smoke test (V1.1-C.2).
 *
 * Only runs when a deployed backend is provided:
 *   PSC_STAGING_URL=https://<service>.up.railway.app npx playwright test staging-smoke
 *
 * It deliberately talks to the REAL remote API - no mocks, no fixtures served
 * from the local backend - so a green run means the deployed service actually
 * received an upload, ran Basic Pitch and returned a score.
 */

const STAGING = process.env.PSC_STAGING_URL?.replace(/\/$/, "");
const FIXTURE = path.resolve(__dirname, "..", "fixtures", "melody.wav");
// The staging API is behind the access gate (V1.1-C.2.2); every request carries
// the shared credential. Without it the suite would only prove that 401 works.
const GATE_TOKEN = process.env.POCKETSCORE_ACCESS_GATE_TOKEN ?? "";
const authHeaders = GATE_TOKEN ? { Authorization: `Bearer ${GATE_TOKEN}` } : {};

test.describe("staging smoke", () => {
  test.skip(!STAGING, "PSC_STAGING_URL not set - no deployed backend to test");

  test("health and readiness answer over HTTPS", async ({ request }) => {
    const health = await request.get(`${STAGING}/health`);
    expect(health.status()).toBe(200);
    const body = await health.json();
    expect(body.status).toBe("ok");

    const ready = await request.get(`${STAGING}/ready`);
    expect([200, 503]).toContain(ready.status());
    const detail = await ready.json();
    expect(detail.checks.model).toBeTruthy();
  });

  test("upload -> transcribe -> notation returns real notes", async ({ request }) => {
    const upload = await request.post(`${STAGING}/api/v1/audio/upload`, {
      headers: authHeaders,
      multipart: {
        file: {
          name: "melody.wav",
          mimeType: "audio/wav",
          buffer: require("fs").readFileSync(FIXTURE),
        },
      },
    });
    expect(upload.status(), await upload.text()).toBe(201);
    const asset = await upload.json();

    const created = await request.post(`${STAGING}/api/v1/transcription/jobs`, {
      headers: authHeaders,
      data: { asset_id: asset.asset_id },
    });
    expect(created.status()).toBeLessThan(300);
    const job = await created.json();

    const run = await request.post(`${STAGING}/api/v1/transcription/jobs/${job.job_id}/run`, {
      headers: authHeaders,
    });
    expect([200, 503, 504]).toContain(run.status());
    test.skip(run.status() === 503, "staging inference pool busy - retry later");
    const done = await run.json();
    expect(done.status).toBe("completed");
    expect(done.events_produced).toBeGreaterThan(0);

    const both = await request.get(`${STAGING}/api/v1/notation/${done.document_id}/both`, {
      headers: authHeaders,
    });
    expect(both.status()).toBe(200);
    const notation = await both.json();
    expect(notation.grid.stats.notes).toBeGreaterThan(0);
    expect(notation.jianpu.stats.notes).toBeGreaterThan(0);
  });

  test("rejects an unsupported extension over the wire", async ({ request }) => {
    const response = await request.post(`${STAGING}/api/v1/audio/upload`, {
      headers: authHeaders,
      multipart: {
        file: { name: "evil.exe", mimeType: "application/octet-stream", buffer: Buffer.from("MZ") },
      },
    });
    expect(response.status()).toBe(415);
    const body = await response.json();
    expect(body.error.code).toBe("UNSUPPORTED_MEDIA_TYPE");
  });
});

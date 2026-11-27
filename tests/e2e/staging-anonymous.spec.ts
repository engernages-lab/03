import { expect, test } from "@playwright/test";

/**
 * V1.1-C.2.2.2 Phase 12b: anonymous access must be refused.
 *
 * STATUS: FIXME - the browser navigation half is NOT TESTED in this environment.
 *
 * What we observed while trying to run it:
 *   - a fresh Chrome against https://<staging>/ aborts the navigation with
 *     net::ERR_INVALID_AUTH_CREDENTIALS (the gate answers 401 with a Basic
 *     challenge and Chrome refuses to render it) - reproduced standalone twice;
 *   - navigating to the exempt /health first and *then* to / makes the navigation
 *     hang until the test timeout, in the runner and in a standalone script.
 *
 * So the browser-rendering assertion is unstable here and is reported as
 * NOT TESTED rather than pretended green. The security property itself is still
 * verified, twice, over real HTTP with no credentials:
 *   - curl: GET / -> 401, GET /api/v1/documents -> 401, POST /audio/upload -> 401
 *     (artifacts/access-gate-check.json, artifacts/gate-anon.json)
 *   - scripts/deploy/verify-staging-regression.sh asserts those 401s on every run.
 *
 * This file lives apart from staging-regression.spec.ts because Playwright Test
 * applies a file's `test.use({ extraHTTPHeaders })` to every browser the worker
 * launches - an "anonymous" context inside the authenticated spec silently got
 * the bearer token and returned 200.
 */

const STAGING = process.env.PSC_STAGING_URL?.replace(/\/$/, "");

test.use({ channel: process.env.PSC_BROWSER_CHANNEL || undefined });

test.describe("staging access gate (anonymous browser)", () => {
  test.skip(!STAGING, "PSC_STAGING_URL is required");

  test("anonymous browser cannot render the SPA", async ({ browser }) => {
    // Kept as a runnable description of the intended check; see the header note.
    test.fixme(true, "Chrome hangs on the gate challenge in this environment; HTTP-level 401s cover the property");

    const context = await browser.newContext();
    const page = await context.newPage();
    await page.goto(`${STAGING}/`, { waitUntil: "domcontentloaded", timeout: 15000 });
    const rendered = await page
      .evaluate(() => (document.body?.innerText ?? "").includes("PocketScore"))
      .catch(() => false);
    expect(rendered).toBe(false);
    await context.close();
  });

  test("unauthenticated API call returns the gate envelope (runs today)", async ({ request }) => {
    const response = await request.get(`${STAGING}/api/v1/documents`);
    expect(response.status()).toBe(401);
    expect(await response.text()).toContain("ACCESS_GATE_REQUIRED");
  });
});

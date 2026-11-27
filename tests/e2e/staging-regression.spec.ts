import { expect, test } from "@playwright/test";

/**
 * V1.1-C.2.2.2 Phase 12: real browser regression against the Railway staging URL.
 *
 * The staging API sits behind the access gate, so the test context injects the
 * shared bearer token as an extra HTTP header. It is read from the environment
 * and is never baked into the bundle or written to the artefacts.
 */

const STAGING = process.env.PSC_STAGING_URL?.replace(/\/$/, "");
const TOKEN = process.env.POCKETSCORE_ACCESS_GATE_TOKEN ?? "";

// Use the system browser when the Playwright bundle is unavailable: the point is
// a real browser against the real staging URL, not which binary renders it.
// `channel` must be top-level (it changes the worker), so it lives here.
test.use({ channel: process.env.PSC_BROWSER_CHANNEL || undefined });

test.describe("staging regression (real browser)", () => {
  test.skip(!STAGING || !TOKEN, "PSC_STAGING_URL and POCKETSCORE_ACCESS_GATE_TOKEN are required");

  // Use the system browser when the Playwright bundle is unavailable: the point
  // is a real browser against the real staging URL, not which binary renders it.
  test.use({
    extraHTTPHeaders: { Authorization: `Bearer ${TOKEN}` },
  });

  test("SPA loads, assets resolve, client routes render", async ({ page }) => {
    const consoleErrors: string[] = [];
    const failedRequests: string[] = [];
    const assetResponses: { url: string; status: number }[] = [];

    page.on("console", (message) => {
      if (message.type() === "error") consoleErrors.push(message.text());
    });
    page.on("requestfailed", (request) => failedRequests.push(`${request.url()} ${request.failure()?.errorText ?? ""}`));
    page.on("response", (response) => {
      if (response.url().includes("/assets/")) {
        assetResponses.push({ url: response.url(), status: response.status() });
      }
    });

    const response = await page.goto(`${STAGING}/`, { waitUntil: "networkidle" });
    expect(response?.status()).toBe(200);
    expect(response?.headers()["content-type"] ?? "").toContain("text/html");

    // The React root must actually mount, not just return HTML.
    await expect(page.locator("body")).toBeVisible();
    await page.waitForFunction(() => Boolean(document.querySelector("#root, body > div")));

    // Client-side navigation to real routes.
    for (const route of ["/dashboard", "/scores", "/settings"]) {
      await page.goto(`${STAGING}${route}`, { waitUntil: "networkidle" });
      const html = await page.content();
      expect(html.length, `route ${route} rendered nothing`).toBeGreaterThan(500);
      expect(page.url()).toContain(route);
    }

    // Deep link + reload (what a refresh does).
    await page.goto(`${STAGING}/scores`, { waitUntil: "networkidle" });
    await page.reload({ waitUntil: "networkidle" });
    expect(await page.title()).toBeTruthy();

    const badAssets = assetResponses.filter((entry) => entry.status >= 400);
    expect(badAssets, `failed assets: ${JSON.stringify(badAssets)}`).toHaveLength(0);
    expect(assetResponses.length, "no JS/CSS asset was loaded at all").toBeGreaterThan(0);

    const hardErrors = consoleErrors.filter((text) => !/favicon|ResizeObserver/i.test(text));
    expect(hardErrors, `console errors: ${hardErrors.join(" | ")}`).toHaveLength(0);
    expect(failedRequests).toHaveLength(0);

    // Evidence for the report (no token, no secrets).
    const summary = {
      staging: STAGING,
      final_url: page.url(),
      title: await page.title(),
      asset_count: assetResponses.length,
      assets: assetResponses.slice(0, 10),
      console_errors: hardErrors,
      failed_requests: failedRequests,
    };
    console.log("BROWSER_SUMMARY " + JSON.stringify(summary));
  });

});

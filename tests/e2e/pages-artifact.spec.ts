import { expect, test } from "@playwright/test";
import path from "node:path";

/**
 * Smoke test for the GitHub Pages artefact.
 *
 * Runs only when PSC_STATIC_URL points at a static server hosting the build
 * under its real sub-path (e.g. http://127.0.0.1:8080/03/). This proves the
 * artefact itself boots - asset paths, router basename and the honest
 * "static preview, no API attached" state - before Pages is switched on.
 */
const STATIC_URL = process.env.PSC_STATIC_URL;

test.describe("pages artefact", () => {
  test.skip(!STATIC_URL, "set PSC_STATIC_URL to run the static artefact check");

  test("静态产物可以启动并如实说明没有后端", async ({ page }) => {
    // Only bundle requests matter here: /api 404s are expected without a backend.
    const assetFailures: string[] = [];
    page.on("response", (response) => {
      if (response.url().includes("/03/assets/") && response.status() >= 400) {
        assetFailures.push(`${response.status()} ${response.url()}`);
      }
    });

    const response = await page.goto(STATIC_URL!, { waitUntil: "networkidle" });
    expect(response?.status()).toBe(200);

    // Shell renders
    await expect(page.getByText("PocketScore").first()).toBeVisible();
    await expect(page.getByRole("link", { name: /音乐资料库/ })).toBeVisible();

    // Router basename works: client-side navigation stays inside the sub-path
    await page.getByRole("link", { name: /音乐资料库/ }).click();
    await expect(page).toHaveURL(/\/03\/music-library$/);
    expect(new URL(page.url()).pathname.startsWith("/03/")).toBe(true);

    // No API attached -> the dashboard explains it instead of failing silently
    await page.getByRole("link", { name: /工作台/ }).click();
    await expect(page.getByText(/静态预览页|无法连接后端 API/)).toBeVisible({ timeout: 20_000 });

    expect(assetFailures).toEqual([]);

    // Evidence for the report: what a visitor sees before an API is attached.
    await page.screenshot({
      path: path.resolve(__dirname, "..", "..", "docs", "screenshots", "09-pages-static-preview.png"),
      fullPage: false,
    });
  });
});

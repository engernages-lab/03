/**
 * Captures screenshots of every major screen for the development reports.
 * Usage (servers must be running):
 *   npx playwright test tests/e2e/../screenshots.spec.ts --project=chromium
 */
import { test } from "@playwright/test";
import path from "node:path";

const OUT = path.resolve(__dirname, "..", "..", "docs", "screenshots");
const FIXTURES = path.resolve(__dirname, "..", "fixtures");

test("capture workstation screens", async ({ page }) => {
  await page.setViewportSize({ width: 1600, height: 1000 });

  await page.goto("/dashboard");
  await page.waitForTimeout(1200);
  await page.screenshot({ path: path.join(OUT, "01-dashboard.png"), fullPage: true });

  // import the WAV + MIDI so the library and score screens have real data
  await page.goto("/music-library");
  const wavInput = page.locator('input[type="file"][accept*=".wav"]').first();
  await wavInput.setInputFiles(path.join(FIXTURES, "tone.wav"));
  await page.waitForTimeout(2500);
  await page.screenshot({ path: path.join(OUT, "02-music-library.png"), fullPage: true });

  await page.goto("/scores");
  const midiInput = page.locator('input[type="file"][accept*=".mid"]').first();
  await midiInput.setInputFiles(path.join(FIXTURES, "sample.mid"));
  await page.waitForURL(/\/scores\/[0-9a-zA-Z]+$/);
  await page.waitForTimeout(2000);
  await page.screenshot({ path: path.join(OUT, "03-score-editor.png"), fullPage: true });

  await page.getByRole("button", { name: "数字谱", exact: true }).click();
  await page.waitForTimeout(600);
  await page.screenshot({ path: path.join(OUT, "04-jianpu.png"), fullPage: false });

  await page.goto("/music-player");
  await page.waitForTimeout(800);
  await page.screenshot({ path: path.join(OUT, "05-player.png"), fullPage: true });

  await page.goto("/keyboard");
  await page.waitForTimeout(800);
  await page.screenshot({ path: path.join(OUT, "06-keyboard.png"), fullPage: true });

  await page.goto("/transcription");
  await page.waitForTimeout(800);
  await page.screenshot({ path: path.join(OUT, "07-transcription.png"), fullPage: true });

  await page.goto("/music-sources");
  await page.waitForTimeout(800);
  await page.screenshot({ path: path.join(OUT, "08-sources.png"), fullPage: true });
});

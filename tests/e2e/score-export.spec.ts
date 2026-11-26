import { expect, test } from "@playwright/test";
import path from "node:path";

/**
 * A.10-S acceptance: exported images must be real PNGs at the requested 9:16
 * size, produced from the MusicDocument (not a screenshot of the viewport).
 *
 * The sandboxed browser cannot persist a download, so the suite inspects the
 * bytes the renderer produced (exposed as window.__pocketscoreExport) instead
 * of the OS save dialog.
 */

const FIXTURES = path.resolve(__dirname, "..", "fixtures");
const MIDI = path.join(FIXTURES, "sample.mid");

interface ExportProbe {
  name: string;
  head: number[];
  size: number;
  text?: string;
}

async function readExport(page: import("@playwright/test").Page): Promise<ExportProbe> {
  return page.evaluate(async () => {
    const payload = (window as unknown as { __pocketscoreExport?: { name: string; blob: Blob } })
      .__pocketscoreExport;
    if (!payload) throw new Error("no export payload on window");
    const buffer = new Uint8Array(await payload.blob.arrayBuffer());
    const head = Array.from(buffer.slice(0, 32));
    // latin1 view lets the test read ZIP entry names without a parser
    let text: string | undefined;
    if (buffer[0] === 0x50 && buffer[1] === 0x4b) {
      text = Array.from(buffer.slice(0, Math.min(buffer.length, 4096)))
        .map((byte) => String.fromCharCode(byte))
        .join("");
    }
    return { name: payload.name, head, size: buffer.length, text };
  });
}

function pngSize(head: number[]): { width: number; height: number } {
  const view = new DataView(new Uint8Array(head).buffer);
  return { width: view.getUint32(16), height: view.getUint32(20) };
}

async function openEditor(page: import("@playwright/test").Page) {
  await page.goto("/scores");
  const midiInput = page.locator('input[type="file"][accept*=".mid"]').first();
  await midiInput.setInputFiles(MIDI);
  await page.waitForURL(/\/scores\/[0-9a-zA-Z]+$/, { timeout: 30_000 });
  await expect(page.getByText("双谱对照")).toBeVisible();
}

test.describe.configure({ mode: "serial" });

test("导出 9:16 高清谱面图片（PNG + ZIP）", async ({ page }) => {
  await openEditor(page);

  await page.getByTestId("export-image-button").click();
  const dialog = page.getByTestId("export-dialog");
  await expect(dialog).toBeVisible();

  // ---- grid only, single page, default 1080x1920 -------------------------
  await page.getByTestId("export-mode-grid").click();
  await page.getByTestId("export-size").selectOption("hd");
  await page.getByTestId("export-scope").selectOption("current");
  await page.getByTestId("export-confirm").click();
  await expect(page.getByTestId("export-download")).toBeVisible({ timeout: 30_000 });

  const png = await readExport(page);
  expect(png.head.slice(1, 4)).toEqual([0x50, 0x4e, 0x47]); // "PNG"
  const size = pngSize(png.head);
  expect(size.width).toBe(1080);
  expect(size.height).toBe(1920);
  expect(png.name).toMatch(/^PocketScore_.*\.png$/);
  expect(png.size).toBeGreaterThan(5_000);

  // ---- full score, all pages -> multi page ZIP ---------------------------
  await page.getByTestId("export-scope").selectOption("all");
  await page.getByTestId("export-mode-full").click();
  // V1.1-B: the page count lives in the export summary card
  const hint = page.getByTestId("export-summary");
  await expect(hint).toBeVisible();
  const text = (await hint.textContent()) ?? "";
  const pageCount = Number(/共\s*(\d+)\s*页/.exec(text)?.[1] ?? "0");
  expect(pageCount).toBeGreaterThan(0);

  await page.getByTestId("export-confirm").click();
  await expect(page.getByTestId("export-download")).toBeVisible({ timeout: 60_000 });

  const artifact = await readExport(page);
  if (pageCount > 1) {
    expect(artifact.head.slice(0, 2)).toEqual([0x50, 0x4b]); // "PK"
    expect(artifact.name).toMatch(/ScoreImages\.zip$/);
    expect(artifact.text).toContain("PocketScore_");
    expect(artifact.text).toContain(".png");
  } else {
    expect(artifact.head.slice(1, 4)).toEqual([0x50, 0x4e, 0x47]);
  }
});

test("三种尺寸与主题都渲染出正确像素", async ({ page }) => {
  await openEditor(page);
  await page.getByTestId("export-image-button").click();
  await expect(page.getByTestId("export-dialog")).toBeVisible();

  const cases = [
    { theme: "classic", size: "hd", width: 1080, height: 1920 },
    { theme: "dark", size: "uhd", width: 1440, height: 2560 },
    { theme: "soft", size: "4k", width: 2160, height: 3840 },
  ];

  for (const item of cases) {
    await page.getByTestId("export-mode-jianpu").click();
    await page.getByTestId("export-theme").selectOption(item.theme);
    await page.getByTestId("export-size").selectOption(item.size);
    await page.getByTestId("export-scope").selectOption("current");
    await page.getByTestId("export-confirm").click();
    await expect(page.getByTestId("export-download")).toBeVisible({ timeout: 60_000 });

    const artifact = await readExport(page);
    const { width, height } = pngSize(artifact.head);
    expect(width, `${item.theme} width`).toBe(item.width);
    expect(height, `${item.theme} height`).toBe(item.height);
  }
});

test("预览、水印开关与信息开关都生效", async ({ page }) => {
  await openEditor(page);
  await page.getByTestId("export-image-button").click();
  const dialog = page.getByTestId("export-dialog");
  await expect(dialog).toBeVisible();

  await page.getByRole("button", { name: "生成预览" }).click();
  await expect(page.getByTestId("export-preview")).toBeVisible({ timeout: 30_000 });

  await page.getByTestId("export-show-watermark").uncheck();
  await page.getByTestId("export-show-info").uncheck();
  await expect(page.getByTestId("export-summary")).toContainText(/共 \d+ 页/);

  await page.getByTestId("export-mode-keyboard").click();
  await page.getByTestId("export-scope").selectOption("current");
  await page.getByTestId("export-confirm").click();
  await expect(page.getByTestId("export-download")).toBeVisible({ timeout: 30_000 });
  const artifact = await readExport(page);
  expect(artifact.head.slice(1, 4)).toEqual([0x50, 0x4e, 0x47]);
});

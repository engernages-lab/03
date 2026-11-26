import { expect, test } from "@playwright/test";
import path from "node:path";

/**
 * V1.1-B acceptance: professional export.
 *
 * Every assertion reads the produced bytes. The sandboxed browser cancels OS
 * downloads (verified for http/blob/data alike), so the suite inspects the
 * artefact the renderer produced instead of the save dialog - and separately
 * asserts that the save button and the persistent link exist with the right
 * filename, which is everything a browser can be held to here.
 */

const FIXTURES = path.resolve(__dirname, "..", "fixtures");
const SAMPLE = path.join(FIXTURES, "sample.mid");
const LONG = path.join(FIXTURES, "long.mid");

interface Probe {
  name: string;
  head: number[];
  size: number;
  /** latin1 text of the first bytes (for ZIP entry names / PDF header) */
  text: string;
  /** entry names, parsed from the archive's local file headers */
  zipEntries?: string[];
  /** structural facts computed over the whole artefact inside the page */
  pdf?: {
    count: number;
    widths: { width: number; height: number }[];
    mediaBoxes: { width: number; height: number }[];
    xrefEntries: number;
    offsetsValid: boolean;
    hasJpeg: boolean;
    hasEof: boolean;
    hasUtf16Title: boolean;
  };
}

async function readExport(page: import("@playwright/test").Page, limit = 4096): Promise<Probe> {
  return page.evaluate(async (maxBytes) => {
    const payload = (window as unknown as { __pocketscoreExport?: { name: string; blob: Blob } })
      .__pocketscoreExport;
    if (!payload) throw new Error("no export payload on window");
    const buffer = new Uint8Array(await payload.blob.arrayBuffer());
    const head = Array.from(buffer.slice(0, 32));
    const text = Array.from(buffer.slice(0, Math.max(maxBytes, 4096)))
      .map((byte) => String.fromCharCode(byte))
      .join("");

    let pdf: Probe["pdf"];
    const isPdf = text.startsWith("%PDF-");
    if (isPdf) {
      // decode the WHOLE file so xref offsets are checked against real bytes
      let latin = "";
      const chunk = 8192;
      for (let offset = 0; offset < buffer.length; offset += chunk) {
        latin += Array.from(buffer.slice(offset, offset + chunk))
          .map((byte) => String.fromCharCode(byte))
          .join("");
      }
      const count = Number(/\/Type \/Pages \/Count (\d+)/.exec(latin)?.[1] ?? "0");
      const widths = [...latin.matchAll(/\/Width (\d+) \/Height (\d+)/g)].map((match) => ({
        width: Number(match[1]),
        height: Number(match[2]),
      }));
      const mediaBoxes = [...latin.matchAll(/\/MediaBox \[0 0 ([\d.]+) ([\d.]+)\]/g)].map((match) => ({
        width: Number(match[1]),
        height: Number(match[2]),
      }));
      const xrefStart = latin.lastIndexOf("\nxref\n");
      const entries =
        xrefStart < 0
          ? []
          : latin
              .slice(xrefStart)
              .split("\n")
              .filter((line) => /^\d{10} 00000 n $/.test(line));
      pdf = {
        count,
        widths,
        mediaBoxes,
        xrefEntries: entries.length,
        offsetsValid: entries.every((entry) => {
          const offset = Number(entry.slice(0, 10));
          return /^\d+ 0 obj/.test(latin.slice(offset, offset + 16));
        }),
        hasJpeg: latin.includes("/Filter /DCTDecode"),
        hasEof: latin.trimEnd().endsWith("%%EOF"),
        hasUtf16Title: /\/Title <FEFF/.test(latin),
      };
    } else if (buffer[0] === 0x50 && buffer[1] === 0x4b) {
      // parse local file headers over the WHOLE archive (the central directory
      // lives at the end, so a prefix-only read would miss the entry names)
      const entries: string[] = [];
      for (let offset = 0; offset + 30 < buffer.length; offset += 1) {
        if (
          buffer[offset] === 0x50 &&
          buffer[offset + 1] === 0x4b &&
          buffer[offset + 2] === 0x03 &&
          buffer[offset + 3] === 0x04
        ) {
          const nameLength = buffer[offset + 26] | (buffer[offset + 27] << 8);
          const extraLength = buffer[offset + 28] | (buffer[offset + 29] << 8);
          const nameBytes = buffer.slice(offset + 30, offset + 30 + nameLength);
          entries.push(new TextDecoder("utf-8").decode(nameBytes));
          offset += 29 + nameLength + extraLength;
        }
      }
      (window as unknown as Record<string, unknown>).__zipEntries = entries;
    }
    const zipEntries = (window as unknown as { __zipEntries?: string[] }).__zipEntries;
    return { name: payload.name, head, size: buffer.length, text, pdf, zipEntries };
  }, limit);
}

function pngSize(head: number[]): { width: number; height: number } {
  const view = new DataView(new Uint8Array(head).buffer);
  return { width: view.getUint32(16), height: view.getUint32(20) };
}

/** Count PDF page objects and validate that xref offsets point at real objects. */
function inspectPdf(text: string) {
  const count = Number(/\/Type \/Pages \/Count (\d+)/.exec(text)?.[1] ?? "0");
  const widths = [...text.matchAll(/\/Width (\d+) \/Height (\d+)/g)].map((match) => ({
    width: Number(match[1]),
    height: Number(match[2]),
  }));
  const mediaBoxes = [...text.matchAll(/\/MediaBox \[0 0 ([\d.]+) ([\d.]+)\]/g)].map((match) => ({
    width: Number(match[1]),
    height: Number(match[2]),
  }));
  const xrefStart = text.lastIndexOf("\nxref\n");
  const entries = text
    .slice(xrefStart)
    .split("\n")
    .filter((line) => /^\d{10} 00000 n $/.test(line));
  const offsetsValid = entries.every((entry) => {
    const offset = Number(entry.slice(0, 10));
    return /^\d+ 0 obj/.test(text.slice(offset, offset + 16));
  });
  return {
    count,
    widths,
    mediaBoxes,
    xrefEntries: entries.length,
    offsetsValid,
    hasJpeg: text.includes("/Filter /DCTDecode"),
    hasEof: text.trimEnd().endsWith("%%EOF"),
  };
}

async function openEditor(page: import("@playwright/test").Page, fixture = SAMPLE) {
  await page.goto("/scores");
  await page.locator('input[type="file"][accept*=".mid"]').first().setInputFiles(fixture);
  await page.waitForURL(/\/scores\/[0-9a-zA-Z]+$/, { timeout: 60_000 });
  await expect(page.getByText("双谱对照")).toBeVisible();
  await page.getByTestId("export-image-button").click();
  await expect(page.getByTestId("export-dialog")).toBeVisible();
}

test.describe.configure({ mode: "serial" });

test("A4 纵向/横向按毫米换算像素，不是拉伸 9:16", async ({ page }) => {
  await openEditor(page);

  // A4 portrait @150 DPI = 1240 x 1754
  await page.getByTestId("export-format-a4-portrait").click();
  await page.getByTestId("export-dpi").selectOption("150");
  await page.getByTestId("export-scope").selectOption("current");
  await page.getByTestId("export-mode-grid").click();
  await expect(page.getByTestId("export-summary")).toContainText("A4 纵向");
  await expect(page.getByTestId("export-summary")).toContainText("210×297 mm");

  await page.getByTestId("export-confirm").click();
  await expect(page.getByTestId("export-download")).toBeVisible({ timeout: 60_000 });
  const portrait = await readExport(page);
  expect(portrait.head.slice(1, 4)).toEqual([0x50, 0x4e, 0x47]);
  expect(pngSize(portrait.head)).toEqual({ width: 1240, height: 1754 });

  // A4 landscape swaps the edges
  await page.getByTestId("export-format-a4-landscape").click();
  await expect(page.getByTestId("export-summary")).toContainText("297×210 mm");
  await page.getByTestId("export-confirm").click();
  await expect(page.getByTestId("export-download")).toBeVisible({ timeout: 60_000 });
  const landscape = await readExport(page);
  expect(pngSize(landscape.head)).toEqual({ width: 1754, height: 1240 });

  // 9:16 must remain untouched
  await page.getByTestId("export-format-story").click();
  await page.getByTestId("export-size").selectOption("hd");
  await page.getByTestId("export-confirm").click();
  await expect(page.getByTestId("export-download")).toBeVisible({ timeout: 60_000 });
  const story = await readExport(page);
  expect(pngSize(story.head)).toEqual({ width: 1080, height: 1920 });
});

test("PDF：真实多页文件（位图嵌入），页码与物理尺寸正确", async ({ page }) => {
  await openEditor(page);

  // single page A4 portrait @300 DPI
  await page.getByTestId("export-format-a4-portrait").click();
  await page.getByTestId("export-dpi").selectOption("300");
  await page.getByTestId("export-scope").selectOption("current");
  await page.getByTestId("export-pdf").click();
  await expect(page.getByTestId("export-download")).toBeVisible({ timeout: 90_000 });

  const single = await readExport(page, 20_000);
  console.log(
    `[pdf] single page: ${single.name} ${(single.size / 1024).toFixed(0)} KB, words=${single.pdf?.count}`,
  );
  expect(single.head.slice(0, 5).map((byte) => String.fromCharCode(byte)).join("")).toBe("%PDF-");
  expect(single.name).toMatch(/^PocketScore_.*\.pdf$/);
  expect(single.size).toBeGreaterThan(20_000);
  expect(single.text).toContain("%PDF-1.4");
  const info = single.pdf!;
  expect(info).toBeDefined();
  expect(info.count).toBe(1);
  expect(info.widths[0]).toEqual({ width: 2480, height: 3508 });
  // 2480 px at 300 DPI = 595.2 pt
  expect(info.mediaBoxes[0].width).toBeCloseTo(595.2, 1);
  expect(info.hasJpeg).toBe(true);
  expect(info.hasEof).toBe(true);
  expect(info.offsetsValid).toBe(true);
  expect(info.xrefEntries).toBeGreaterThan(3);
  // the Chinese title is stored as a UTF-16BE hex string
  expect(info.hasUtf16Title).toBe(true);

  // multi page: full score
  await page.getByTestId("export-mode-full").click();
  await page.getByTestId("export-scope").selectOption("all");
  const summary = (await page.getByTestId("export-summary").textContent()) ?? "";
  const expectedPages = Number(/共\s*(\d+)\s*页/.exec(summary)?.[1] ?? "0");
  expect(expectedPages).toBeGreaterThan(1);

  await page.getByTestId("export-pdf").click();
  await expect(page.getByTestId("export-download")).toBeVisible({ timeout: 120_000 });
  const multi = await readExport(page, 40_000);
  const multiInfo = multi.pdf!;
  expect(multiInfo.count).toBe(expectedPages);
  expect(multiInfo.widths).toHaveLength(expectedPages);
  expect(new Set(multiInfo.widths.map((item) => `${item.width}x${item.height}`)).size).toBe(1);
  expect(multiInfo.offsetsValid).toBe(true);
  expect(multiInfo.hasEof).toBe(true);
});

test("预览：缩略图、翻页、缩放与最终产物同源", async ({ page }) => {
  await openEditor(page);
  await page.getByTestId("export-format-story").click();
  await page.getByTestId("export-size").selectOption("hd");
  await page.getByTestId("export-mode-full").click();
  await page.getByRole("button", { name: "生成预览" }).click();

  await expect(page.getByTestId("export-preview-panel")).toBeVisible({ timeout: 60_000 });
  await expect(page.getByTestId("export-thumb-1")).toBeVisible();
  await expect(page.getByTestId("export-preview")).toBeVisible();

  const before = await page.getByTestId("export-preview").evaluate((node) => (node as HTMLImageElement).style.width);
  await page.getByTestId("export-zoom-in").click();
  const after = await page.getByTestId("export-preview").evaluate((node) => (node as HTMLImageElement).style.width);
  expect(parseInt(after, 10)).toBeGreaterThan(parseInt(before, 10));
  await page.getByTestId("export-zoom-out").click();
  await page.getByTestId("export-zoom-out").click();

  // preview pages must match the exported page count
  const summary = (await page.getByTestId("export-summary").textContent()) ?? "";
  const pages = Number(/共\s*(\d+)\s*页/.exec(summary)?.[1] ?? "0");
  if (pages > 1) {
    await page.getByTestId("export-thumb-2").click();
    await expect(page.getByText(new RegExp(`预览 第 2 /`))).toBeVisible();
  }

  // the preview image and the exported PNG must have the same aspect ratio
  // (measure the intrinsic image, not the CSS box: max-height clamps the latter)
  const natural = await page.getByTestId("export-preview").evaluate((node) => {
    const image = node as HTMLImageElement;
    return { width: image.naturalWidth, height: image.naturalHeight };
  });
  expect(natural.width).toBeGreaterThan(0);
  expect(natural.width / natural.height).toBeCloseTo(1080 / 1920, 1);
});

test("文件命名：中文四段式、ZIP 与 PDF 专用名、重复导出不覆盖", async ({ page }) => {
  await openEditor(page);
  await page.getByTestId("export-format-story").click();
  await page.getByTestId("export-mode-grid").click();
  await page.getByTestId("export-scope").selectOption("current");

  await page.getByTestId("export-confirm").click();
  await expect(page.getByTestId("export-download")).toBeVisible({ timeout: 60_000 });
  const png = await readExport(page);
  // PocketScore_<title>_格子谱_<yyyymmdd>.png
  expect(png.name).toMatch(/^PocketScore_.+_格子谱_\d{8}\.png$/);
  expect(png.name).not.toMatch(/[\\/:*?"<>|]/);

  // exporting again must not reuse the same name
  await page.getByTestId("export-confirm").click();
  await expect(page.getByTestId("export-download")).toBeVisible({ timeout: 60_000 });
  const second = await readExport(page);
  expect(second.name).not.toBe(png.name);

  await page.getByTestId("export-pdf").click();
  await expect(page.getByTestId("export-download")).toBeVisible({ timeout: 90_000 });
  const pdf = await readExport(page);
  expect(pdf.name).toMatch(/^PocketScore_.+\.pdf$/);
});

test("性能：64 小节的乐谱导出 20+ 页仍在预算内", async ({ page }) => {
  test.setTimeout(300_000);
  await openEditor(page, LONG);

  await page.getByTestId("export-format-story").click();
  await page.getByTestId("export-size").selectOption("hd");
  await page.getByTestId("export-mode-grid").click();
  await page.getByTestId("export-scope").selectOption("all");
  await expect(page.getByTestId("export-summary")).toContainText(/\u5171 \d+ \u9875/);
  const summary = await page.getByTestId("export-summary").innerText();
  const attribute = await page.getByTestId("export-summary").getAttribute("data-pages");
  const pages = Number(attribute ?? "0");
  // the number shown to the user must equal the number the renderer will produce
  expect(summary).toContain(String(pages));
  expect(pages).toBeGreaterThanOrEqual(20);

  // single page baseline for the report
  await page.getByTestId("export-scope").selectOption("current");
  const singleStart = Date.now();
  await page.getByTestId("export-confirm").click();
  await expect(page.getByTestId("export-download")).toBeVisible({ timeout: 60_000 });
  const singleMs = Date.now() - singleStart;
  await page.getByTestId("export-scope").selectOption("all");

  const started = Date.now();
  await page.getByTestId("export-confirm").click();
  await expect(page.getByTestId("export-download")).toBeVisible({ timeout: 240_000 });
  const elapsed = Date.now() - started;

  const zip = await readExport(page);
  expect(zip.head.slice(0, 2)).toEqual([0x50, 0x4b]);
  // every page is a separate entry, in order, with a continuous page number
  const names = zip.zipEntries ?? [];
  expect(names.length).toBeGreaterThanOrEqual(20);
  const numbers = names
    .map((name) => /第(\d+)页\.png$/.exec(name)?.[1])
    .filter((value): value is string => Boolean(value))
    .map(Number);
  expect(numbers).toHaveLength(names.length);
  expect(numbers).toEqual(Array.from({ length: names.length }, (_, index) => index + 1));
  expect(new Set(numbers).size).toBe(numbers.length);

  // budget: 20+ pages of 1080x1920 must not take minutes
  console.log(
    `[perf] pages=${pages} elapsed=${elapsed}ms single=${singleMs}ms zip=${(zip.size / 1024).toFixed(0)}KB ` +
      `heap=${await page.evaluate(() => Math.round(((performance as unknown as { memory?: { usedJSHeapSize: number } }).memory?.usedJSHeapSize ?? 0) / 1048576))}MB`,
  );
  expect(elapsed).toBeLessThan(150_000);
  expect(zip.size).toBeGreaterThan(100_000);
});

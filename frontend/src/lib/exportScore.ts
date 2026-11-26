/** Canvas rendering pipeline for score image / PDF export (no viewport capture). */

import {
  THEMES,
  measuresPerPage,
  paginate,
  renderScorePage,
  resolveExportSize,
  type ExportOptions,
  type ScorePage,
} from "./scoreImage";
import { createPdf, pointsFromPixels, type PdfPageImage } from "./pdf";
import { exceedsMemoryLimit, formatMegapixels } from "./pageFormats";
import type { DualNotationResponse } from "./types";

export interface RenderedPage {
  page: ScorePage;
  blob: Blob;
  width: number;
  height: number;
}

function createCanvas(
  width: number,
  height: number,
): { canvas: HTMLCanvasElement; ctx: CanvasRenderingContext2D } {
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d", { alpha: false });
  if (!ctx) throw new Error("当前浏览器无法创建 Canvas 2D 上下文，无法导出图片");
  return { canvas, ctx };
}

function canvasToBlob(canvas: HTMLCanvasElement, type: string, quality?: number): Promise<Blob> {
  return new Promise((resolve, reject) => {
    canvas.toBlob(
      (blob) => {
        if (blob) resolve(blob);
        else reject(new Error(`${type === "image/png" ? "PNG" : "JPEG"} 编码失败（画布可能超出浏览器限制）`));
      },
      type,
      quality,
    );
  });
}

export interface RenderResult {
  pages: RenderedPage[];
  total: number;
  mode: ExportOptions["mode"];
  size: ExportOptions["size"];
  width: number;
  height: number;
  pageCount: number;
}

function pagePlan(dual: DualNotationResponse, options: ExportOptions) {
  const size = resolveExportSize(options);
  if (exceedsMemoryLimit(size)) {
    throw new Error(
      `单页像素 ${formatMegapixels(size)} 超出安全上限，请降低 DPI 或改用较小的版式`,
    );
  }
  const perPage =
    options.measuresPerPage ?? measuresPerPage(options.mode, size.width, dual.grid.slots_per_measure, size.height);
  const totalMeasures = Math.max(dual.grid.stats.measures, dual.jianpu.stats.measures, 1);
  const pages = paginate(totalMeasures, perPage);
  const selected = options.scope === "current" ? pages.slice(0, 1) : pages;
  return { size, selected };
}

/** Pages that would be produced, without rendering (used by the preview summary). */
export function planExport(dual: DualNotationResponse, options: ExportOptions) {
  const { size, selected } = pagePlan(dual, options);
  return { size, pages: selected, pageCount: selected.length };
}

/**
 * Render every page at the requested pixel size.
 *
 * Pages are produced one at a time and released immediately after encoding, so a
 * 20-page A4/600 DPI export never holds more than one canvas at a time.
 */
export async function renderScoreImages(
  dual: DualNotationResponse,
  options: ExportOptions,
  onProgress?: (done: number, total: number) => void,
): Promise<RenderResult> {
  const { size, selected } = pagePlan(dual, options);
  const theme = THEMES[options.theme];

  const rendered: RenderedPage[] = [];
  for (const page of selected) {
    const { canvas, ctx } = createCanvas(size.width, size.height);
    renderScorePage({ ctx, width: size.width, height: size.height, theme, options, dual }, page);
    const blob = await canvasToBlob(canvas, "image/png");
    rendered.push({ page, blob, width: size.width, height: size.height });
    // free the backing store before the next page
    canvas.width = 0;
    canvas.height = 0;
    onProgress?.(rendered.length, selected.length);
  }

  return {
    pages: rendered,
    total: selected.length,
    mode: options.mode,
    size: options.size,
    width: size.width,
    height: size.height,
    pageCount: selected.length,
  };
}

export interface PdfRenderResult {
  bytes: Uint8Array;
  pageCount: number;
  width: number;
  height: number;
  dpi: number;
  /** Bitmap pages: the resolution is the rendered pixel size, not vector. */
  vector: false;
}

/**
 * Render a score PDF.
 *
 * Each page is drawn to a canvas at the requested DPI and embedded as a JPEG
 * (DCTDecode) in a PDF page of the matching physical size. This is a **bitmap
 * PDF**: the caller must state the pixel/DPI limit to the user.
 */
export async function renderScorePdf(
  dual: DualNotationResponse,
  options: ExportOptions,
  onProgress?: (done: number, total: number) => void,
): Promise<PdfRenderResult> {
  const { size, selected } = pagePlan(dual, options);
  const dpi = options.dpi ?? 150;
  const theme = THEMES[options.theme];
  const images: PdfPageImage[] = [];

  for (const page of selected) {
    const { canvas, ctx } = createCanvas(size.width, size.height);
    renderScorePage({ ctx, width: size.width, height: size.height, theme, options, dual }, page);
    const blob = await canvasToBlob(canvas, "image/jpeg", 0.92);
    const data = new Uint8Array(await blob.arrayBuffer());
    images.push({
      data,
      pixelWidth: size.width,
      pixelHeight: size.height,
      pageWidth: pointsFromPixels(size.width, dpi),
      pageHeight: pointsFromPixels(size.height, dpi),
    });
    canvas.width = 0;
    canvas.height = 0;
    onProgress?.(images.length, selected.length);
  }

  const bytes = createPdf(images, {
    title: dual.document.title || "未命名谱面",
    author: dual.document.artist || "未知艺术家",
    subject: `${options.mode} · ${options.theme} · ${dpi} DPI`,
    creator: "PocketScore AI",
  });

  return { bytes, pageCount: images.length, width: size.width, height: size.height, dpi, vector: false };
}

/**
 * Thumbnails for the export preview.
 *
 * Each page is rendered at full size through the same `renderScorePage` path as
 * the real export, then downscaled - so the preview shows exactly the layout
 * that will be written to disk (no second, "preview-only" renderer).
 */
export async function renderPageThumbnails(
  dual: DualNotationResponse,
  options: ExportOptions,
  maxPages = 8,
  thumbWidth = 320,
): Promise<{ url: string; index: number }[]> {
  const { size, selected } = pagePlan(dual, options);
  const theme = THEMES[options.theme];
  const output: { url: string; index: number }[] = [];

  for (const page of selected.slice(0, Math.max(1, maxPages))) {
    const { canvas, ctx } = createCanvas(size.width, size.height);
    renderScorePage({ ctx, width: size.width, height: size.height, theme, options, dual }, page);
    const scaled = document.createElement("canvas");
    scaled.width = thumbWidth;
    scaled.height = Math.max(1, Math.round((size.height / size.width) * thumbWidth));
    const scaledCtx = scaled.getContext("2d", { alpha: false });
    if (scaledCtx) {
      scaledCtx.imageSmoothingQuality = "high";
      scaledCtx.drawImage(canvas, 0, 0, scaled.width, scaled.height);
    }
    const blob = await canvasToBlob(scaled, "image/jpeg", 0.82);
    output.push({ url: URL.createObjectURL(blob), index: page.index });
    canvas.width = 0;
    canvas.height = 0;
    scaled.width = 0;
    scaled.height = 0;
  }
  return output;
}

/**
 * Save a blob through the browser.
 *
 * Order of preference:
 *  1. File System Access API (`showSaveFilePicker`) - a real save dialog, and
 *     the only path that works when a browser blocks programmatic downloads.
 *  2. `<a download>` - the ordinary path; the blob URL is kept alive because
 *     Chromium aborts an in-flight download if its URL is revoked.
 *
 * The return value distinguishes "the file was written" from "a download was
 * requested": the UI must not claim a save it cannot confirm.
 */
export type SaveOutcome = "saved" | "download-requested" | "cancelled";

interface SaveFilePickerWindow extends Window {
  showSaveFilePicker?: (options: {
    suggestedName?: string;
    types?: { description: string; accept: Record<string, string[]> }[];
  }) => Promise<{ createWritable: () => Promise<{ write: (data: Blob) => Promise<void>; close: () => Promise<void> }> }>;
}

export async function saveBlob(
  blob: Blob,
  filename: string,
  mimeType: string,
): Promise<SaveOutcome> {
  const picker = (window as SaveFilePickerWindow).showSaveFilePicker;
  if (typeof picker === "function") {
    try {
      const handle = await picker({
        suggestedName: filename,
        types: [{ description: "PocketScore 导出", accept: { [mimeType]: [`.${filename.split(".").pop()}`] } }],
      });
      const writable = await handle.createWritable();
      await writable.write(blob);
      await writable.close();
      return "saved";
    } catch (error) {
      // AbortError = user cancelled the dialog; anything else falls back
      if (error instanceof DOMException && error.name === "AbortError") {
        return "cancelled";
      }
    }
  }
  downloadBlob(blob, filename);
  return "download-requested";
}

export function downloadBlob(blob: Blob, filename: string): string {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.rel = "noopener";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  // Deliberately not revoked: Chromium cancels an in-flight download when its
  // blob URL is released, and the leak is bounded to this page's lifetime.
  return url;
}

export async function blobToBytes(blob: Blob): Promise<Uint8Array> {
  return new Uint8Array(await blob.arrayBuffer());
}

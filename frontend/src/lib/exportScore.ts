/** Canvas rendering pipeline for score image export (no viewport capture). */

import {
  PAGE_SIZES,
  THEMES,
  measuresPerPage,
  paginate,
  renderScorePage,
  type ExportOptions,
  type ScorePage,
} from "./scoreImage";
import type { DualNotationResponse } from "./types";

export interface RenderedPage {
  page: ScorePage;
  blob: Blob;
  width: number;
  height: number;
}

function createCanvas(width: number, height: number): { canvas: HTMLCanvasElement; ctx: CanvasRenderingContext2D } {
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d", { alpha: false });
  if (!ctx) throw new Error("当前浏览器无法创建 Canvas 2D 上下文，无法导出图片");
  return { canvas, ctx };
}

function canvasToPng(canvas: HTMLCanvasElement): Promise<Blob> {
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => {
      if (blob) resolve(blob);
      else reject(new Error("PNG 编码失败（可能是画布尺寸超出浏览器限制）"));
    }, "image/png");
  });
}

export interface RenderResult {
  pages: RenderedPage[];
  total: number;
  mode: ExportOptions["mode"];
  size: ExportOptions["size"];
}

/**
 * Render every page at the requested pixel size.
 *
 * Pages are produced one at a time and released immediately after encoding, so
 * a 4K multi-page export does not hold all canvases in memory at once.
 */
export async function renderScoreImages(
  dual: DualNotationResponse,
  options: ExportOptions,
  onProgress?: (done: number, total: number) => void,
): Promise<RenderResult> {
  const size = PAGE_SIZES[options.size];
  const perPage =
    options.measuresPerPage ?? measuresPerPage(options.mode, size.width, dual.grid.slots_per_measure);
  const totalMeasures = Math.max(dual.grid.stats.measures, dual.jianpu.stats.measures, 1);
  const pages = paginate(totalMeasures, perPage);
  const selected = options.scope === "current" ? pages.slice(0, 1) : pages;
  const theme = THEMES[options.theme];

  const rendered: RenderedPage[] = [];
  for (const page of selected) {
    const { canvas, ctx } = createCanvas(size.width, size.height);
    renderScorePage(
      { ctx, width: size.width, height: size.height, theme, options, dual },
      page,
    );
    const blob = await canvasToPng(canvas);
    rendered.push({ page, blob, width: size.width, height: size.height });
    // free the backing store before the next page
    canvas.width = 0;
    canvas.height = 0;
    onProgress?.(rendered.length, selected.length);
  }

  return { pages: rendered, total: selected.length, mode: options.mode, size: options.size };
}

export function downloadBlob(blob: Blob, filename: string): void {
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
}

export async function blobToBytes(blob: Blob): Promise<Uint8Array> {
  return new Uint8Array(await blob.arrayBuffer());
}

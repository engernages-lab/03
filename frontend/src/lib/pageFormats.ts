/**
 * Page formats and physical sizes for score export.
 *
 * A4 is computed from its real millimetre dimensions at the requested DPI -
 * never by stretching a 9:16 image. The 9:16 "story" format keeps the pixel
 * sizes shipped in V1.0 for backward compatibility.
 */

export type PageFormat = "story" | "a4-portrait" | "a4-landscape" | "long";
export type Dpi = 150 | 300 | 600;

/** ISO 216 A4 in millimetres (portrait). */
export const A4_MM = { width: 210, height: 297 };

const MM_PER_INCH = 25.4;

/** Guard against canvas sizes browsers refuse to allocate. */
export const MAX_CANVAS_PIXELS = 40_000_000; // ~40 MP, Chrome's hard limit is lower for some GPUs

export interface ResolvedSize {
  width: number;
  height: number;
  dpi: Dpi;
  format: PageFormat;
  label: string;
  /** Physical size in millimetres when the format has a fixed paper size. */
  millimetres?: { width: number; height: number };
  /** True when the page grows to fit the content instead of paginating. */
  autoHeight?: boolean;
}

const STORY_SIZES: Record<string, { width: number; height: number }> = {
  hd: { width: 1080, height: 1920 },
  uhd: { width: 1440, height: 2560 },
  "4k": { width: 2160, height: 3840 },
};

export interface SizeRequest {
  format: PageFormat;
  dpi?: Dpi;
  /** Legacy 9:16 preset, honoured when format is "story". */
  storyPreset?: "hd" | "uhd" | "4k";
  /** Long format: total content height in CSS pixels at 96 DPI. */
  contentHeight?: number;
}

export function millimetresToPixels(mm: number, dpi: Dpi): number {
  return Math.round((mm / MM_PER_INCH) * dpi);
}

export function resolvePageSize(request: SizeRequest): ResolvedSize {
  const dpi = request.dpi ?? 150;
  switch (request.format) {
    case "a4-portrait": {
      const width = millimetresToPixels(A4_MM.width, dpi);
      const height = millimetresToPixels(A4_MM.height, dpi);
      return {
        width,
        height,
        dpi,
        format: request.format,
        label: `A4 纵向 · ${dpi} DPI · ${width}×${height}`,
        millimetres: { ...A4_MM },
      };
    }
    case "a4-landscape": {
      const width = millimetresToPixels(A4_MM.height, dpi);
      const height = millimetresToPixels(A4_MM.width, dpi);
      return {
        width,
        height,
        dpi,
        format: request.format,
        label: `A4 横向 · ${dpi} DPI · ${width}×${height}`,
        millimetres: { width: A4_MM.height, height: A4_MM.width },
      };
    }
    case "long": {
      const width = STORY_SIZES[request.storyPreset ?? "hd"].width;
      // grow by 96 DPI worth of content plus padding; capped for memory safety
      const content = Math.max(600, Math.round(request.contentHeight ?? 1600));
      const height = Math.min(20_000, content + 360);
      return {
        width,
        height,
        dpi,
        format: request.format,
        label: `自适应长图 · ${width}×${height}`,
        autoHeight: true,
      };
    }
    case "story":
    default: {
      const preset = request.storyPreset ?? "hd";
      const size = STORY_SIZES[preset] ?? STORY_SIZES.hd;
      return {
        width: size.width,
        height: size.height,
        dpi,
        format: "story",
        label: `9:16 竖版 · ${size.width}×${size.height}`,
      };
    }
  }
}

/** A4/9:16 page count given the usable content height, used by the preview UI. */
export function estimatePixels(size: ResolvedSize): number {
  return size.width * size.height;
}

export function exceedsMemoryLimit(size: ResolvedSize): boolean {
  return estimatePixels(size) > MAX_CANVAS_PIXELS;
}

/** Human readable megapixels, for the export summary line. */
export function formatMegapixels(size: ResolvedSize): string {
  return `${(estimatePixels(size) / 1_000_000).toFixed(1)} MP`;
}

/** Physical inspection size (mm) for a pixel canvas at a given DPI. */
export function physicalSizeLabel(size: ResolvedSize): string {
  if (size.millimetres) {
    return `${size.millimetres.width}×${size.millimetres.height} mm`;
  }
  const width = (size.width / size.dpi) * MM_PER_INCH;
  const height = (size.height / size.dpi) * MM_PER_INCH;
  return `${width.toFixed(0)}×${height.toFixed(0)} mm @ ${size.dpi} DPI`;
}

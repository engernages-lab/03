import { describe, expect, it } from "vitest";
import {
  A4_MM,
  MAX_CANVAS_PIXELS,
  exceedsMemoryLimit,
  formatMegapixels,
  millimetresToPixels,
  physicalSizeLabel,
  resolvePageSize,
} from "./pageFormats";

describe("page formats", () => {
  it("converts A4 millimetres to pixels at each DPI", () => {
    // 210 mm / 25.4 * 150 = 1240.15 -> 1240
    expect(millimetresToPixels(A4_MM.width, 150)).toBe(1240);
    expect(millimetresToPixels(A4_MM.height, 150)).toBe(1754);
    // 300 DPI is exactly double
    expect(millimetresToPixels(A4_MM.width, 300)).toBe(2480);
    expect(millimetresToPixels(A4_MM.height, 300)).toBe(3508);
    // 600 DPI is exactly 4x the 150 DPI page
    expect(millimetresToPixels(A4_MM.width, 600)).toBe(4961);
    expect(millimetresToPixels(A4_MM.height, 600)).toBe(7016);
  });

  it("keeps the A4 aspect ratio instead of the 9:16 story ratio", () => {
    const a4 = resolvePageSize({ format: "a4-portrait", dpi: 300 });
    expect(a4.width / a4.height).toBeCloseTo(210 / 297, 3);
    expect(a4.width / a4.height).not.toBeCloseTo(9 / 16, 3);
  });

  it("swaps width and height for A4 landscape", () => {
    const portrait = resolvePageSize({ format: "a4-portrait", dpi: 300 });
    const landscape = resolvePageSize({ format: "a4-landscape", dpi: 300 });
    expect(landscape.width).toBe(portrait.height);
    expect(landscape.height).toBe(portrait.width);
    expect(landscape.millimetres).toEqual({ width: 297, height: 210 });
  });

  it("returns the legacy 9:16 presets unchanged", () => {
    expect(resolvePageSize({ format: "story", storyPreset: "hd" })).toMatchObject({
      width: 1080,
      height: 1920,
    });
    expect(resolvePageSize({ format: "story", storyPreset: "uhd" })).toMatchObject({
      width: 1440,
      height: 2560,
    });
    expect(resolvePageSize({ format: "story", storyPreset: "4k" })).toMatchObject({
      width: 2160,
      height: 3840,
    });
  });

  it("grows the long format with the content and marks it auto-height", () => {
    const short = resolvePageSize({ format: "long", contentHeight: 800 });
    const tall = resolvePageSize({ format: "long", contentHeight: 5000 });
    expect(tall.height).toBeGreaterThan(short.height);
    expect(tall.autoHeight).toBe(true);
    expect(tall.height).toBeLessThanOrEqual(20_000);
  });

  it("reports the physical size in millimetres", () => {
    const a4 = resolvePageSize({ format: "a4-portrait", dpi: 300 });
    expect(physicalSizeLabel(a4)).toBe("210×297 mm");
    const story = resolvePageSize({ format: "story", dpi: 150 });
    expect(physicalSizeLabel(story)).toContain("mm @ 150 DPI");
  });

  it("flags canvases that would exhaust browser memory", () => {
    const small = resolvePageSize({ format: "a4-portrait", dpi: 150 });
    const huge = resolvePageSize({ format: "a4-portrait", dpi: 600 });
    expect(exceedsMemoryLimit(small)).toBe(false);
    // 4961 * 7016 = 34.8 MP, still under the 40 MP guard
    expect(huge.width * huge.height).toBeLessThan(MAX_CANVAS_PIXELS);
    expect(formatMegapixels(huge)).toBe("34.8 MP");
    expect(
      exceedsMemoryLimit({ width: 8000, height: 8000, dpi: 600, format: "a4-portrait", label: "x" }),
    ).toBe(true);
  });
});

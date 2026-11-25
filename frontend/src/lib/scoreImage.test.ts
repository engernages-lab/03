import { describe, expect, it } from "vitest";
import {
  PAGE_SIZES,
  THEMES,
  fileNameFor,
  measuresPerPage,
  pageCountFor,
  paginate,
  zipNameFor,
} from "./scoreImage";
import type { DualNotationResponse } from "./types";

function fakeDual(measures: number, slotsPerMeasure = 16): DualNotationResponse {
  return {
    document: {
      document_id: "doc-1",
      title: "测试谱面",
      artist: "测试",
      tempo: 120,
      key_signature: "C",
      time_signature: { numerator: 4, denominator: 4 },
    },
    grid: { slots_per_measure: slotsPerMeasure, stats: { measures, notes: measures * 4 } },
    jianpu: { stats: { measures, notes: measures * 4 }, max_notes_per_line: 8, measures: [] },
    findings: [],
  } as unknown as DualNotationResponse;
}

describe("paginate", () => {
  it("splits on whole measures without gaps or duplicates", () => {
    const pages = paginate(8, 2);
    expect(pages).toHaveLength(4);
    expect(pages.map((page) => page.measures)).toEqual([[1, 2], [3, 4], [5, 6], [7, 8]]);
    const flat = pages.flatMap((page) => page.measures);
    expect(flat).toEqual([1, 2, 3, 4, 5, 6, 7, 8]);
  });

  it("numbers pages and reports the total", () => {
    const pages = paginate(5, 2);
    expect(pages.map((page) => page.index)).toEqual([1, 2, 3]);
    expect(pages.every((page) => page.total === 3)).toBe(true);
  });

  it("keeps a partial last page intact", () => {
    const pages = paginate(5, 2);
    expect(pages[2].measures).toEqual([5]);
  });

  it("never splits a measure across pages", () => {
    for (const perPage of [1, 2, 3, 4]) {
      const pages = paginate(7, perPage);
      for (const page of pages) {
        expect(page.measures.length).toBeLessThanOrEqual(perPage);
      }
      expect(pages.flatMap((page) => page.measures)).toEqual([1, 2, 3, 4, 5, 6, 7]);
    }
  });

  it("handles an empty score", () => {
    const pages = paginate(0, 2);
    expect(pages).toHaveLength(1);
    expect(pages[0].measures).toEqual([]);
    expect(pages[0].total).toBe(1);
  });

  it("clamps a nonsensical per-page value", () => {
    expect(paginate(3, 0)).toHaveLength(3);
    expect(paginate(3, -5)).toHaveLength(3);
  });
});

describe("measuresPerPage", () => {
  it("stays within a readable range for every size", () => {
    for (const preset of Object.values(PAGE_SIZES)) {
      for (const mode of ["grid", "jianpu", "keyboard", "combined", "full"] as const) {
        const value = measuresPerPage(mode, preset.width, 16);
        expect(value).toBeGreaterThanOrEqual(1);
        expect(value).toBeLessThanOrEqual(mode === "combined" || mode === "full" ? 2 : 3);
      }
    }
  });

  it("gives combined layouts fewer measures than single ones", () => {
    const single = measuresPerPage("grid", 1080, 16);
    const combined = measuresPerPage("combined", 1080, 16);
    expect(combined).toBeLessThanOrEqual(single);
  });

  it("handles dense subdivisions without returning zero", () => {
    expect(measuresPerPage("grid", 1080, 64)).toBeGreaterThanOrEqual(1);
  });
});

describe("pageCountFor", () => {
  it("matches paginate for the same input", () => {
    const dual = fakeDual(7);
    const perPage = measuresPerPage("grid", 1080, 16);
    const expected = paginate(7, perPage).length;
    expect(
      pageCountFor(dual, {
        mode: "grid",
        size: "hd",
        theme: "classic",
        showInfo: true,
        showWatermark: true,
      }),
    ).toBe(expected);
  });

  it("produces several pages for a long score", () => {
    const dual = fakeDual(40);
    const count = pageCountFor(dual, {
      mode: "full",
      size: "hd",
      theme: "dark",
      showInfo: true,
      showWatermark: false,
    });
    expect(count).toBeGreaterThan(1);
  });

  it("honours an explicit measuresPerPage", () => {
    const dual = fakeDual(10);
    expect(
      pageCountFor(dual, {
        mode: "grid",
        size: "hd",
        theme: "classic",
        showInfo: true,
        showWatermark: true,
        measuresPerPage: 5,
      }),
    ).toBe(2);
  });
});

describe("file naming", () => {
  it("uses a page suffix only when there are multiple pages", () => {
    expect(fileNameFor("我的歌", 1, 1)).toBe("PocketScore_我的歌.png");
    expect(fileNameFor("我的歌", 2, 3)).toBe("PocketScore_我的歌_第2页.png");
  });

  it("strips characters that break downloads", () => {
    const name = fileNameFor('a/b:c*?"<>|', 1, 1);
    expect(name.startsWith("PocketScore_")).toBe(true);
    expect(name.endsWith(".png")).toBe(true);
    expect(name).not.toMatch(/[\\/:*?"<>|]/);
  });

  it("falls back for an empty title", () => {
    expect(fileNameFor("", 1, 1)).toBe("PocketScore_未命名谱面.png");
    expect(zipNameFor("")).toBe("PocketScore_未命名谱面_ScoreImages.zip");
  });
});

describe("themes", () => {
  it("exposes the three required themes with distinct backgrounds", () => {
    const ids = Object.keys(THEMES).sort();
    expect(ids).toEqual(["classic", "dark", "soft"]);
    const backgrounds = new Set(Object.values(THEMES).map((theme) => theme.background));
    expect(backgrounds.size).toBe(3);
  });
});

describe("page sizes", () => {
  it("are all 9:16", () => {
    for (const preset of Object.values(PAGE_SIZES)) {
      expect(preset.width / preset.height).toBeCloseTo(9 / 16, 5);
    }
  });

  it("defaults to 1080 × 1920", () => {
    expect(PAGE_SIZES.hd.width).toBe(1080);
    expect(PAGE_SIZES.hd.height).toBe(1920);
    expect(PAGE_SIZES.uhd.width).toBe(1440);
    expect(PAGE_SIZES["4k"].width).toBe(2160);
  });
});

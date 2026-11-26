import { describe, expect, it } from "vitest";
import {
  dateStamp,
  exportFileName,
  measuresPerPage,
  modeLabel,
  paginate,
  resolveExportSize,
  sanitiseFileNamePart,
  wrapTitle,
} from "./scoreImage";

/** Minimal 2D context stub: every glyph is 10px wide, so widths are countable. */
function fakeCtx(charWidth = 10) {
  return {
    font: "",
    measureText: (text: string) => ({ width: text.length * charWidth }),
  } as unknown as CanvasRenderingContext2D;
}

describe("export layout (V1.1-B)", () => {
  it("paginates on whole measures only", () => {
    const pages = paginate(10, 3);
    expect(pages.map((page) => page.measures)).toEqual([
      [1, 2, 3],
      [4, 5, 6],
      [7, 8, 9],
      [10],
    ]);
    expect(pages.every((page) => page.total === 4)).toBe(true);
    // no measure is lost or duplicated
    const flat = pages.flatMap((page) => page.measures);
    expect(flat).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
  });

  it("never emits an empty page for an empty score", () => {
    const pages = paginate(0, 2);
    expect(pages).toHaveLength(1);
    expect(pages[0].measures).toEqual([]);
  });

  it("fits fewer measures per page in a narrow portrait page than a landscape one", () => {
    const portrait = resolveExportSize({ mode: "grid", size: "hd", theme: "classic", showInfo: true, showWatermark: true, format: "a4-portrait", dpi: 150 });
    const landscape = resolveExportSize({ mode: "grid", size: "hd", theme: "classic", showInfo: true, showWatermark: true, format: "a4-landscape", dpi: 150 });
    const narrow = measuresPerPage("grid", portrait.width, 16, portrait.height);
    const wide = measuresPerPage("grid", landscape.width, 16, landscape.height);
    expect(wide).toBeGreaterThanOrEqual(narrow);
  });

  it("reduces measures per page as slot density grows", () => {
    const sparse = measuresPerPage("grid", 1080, 4, 1920);
    const dense = measuresPerPage("grid", 1080, 16, 1920);
    expect(dense).toBeLessThanOrEqual(sparse);
  });

  it("wraps a long Chinese title into two lines instead of truncating it blindly", () => {
    const ctx = fakeCtx(10);
    const title = "这是一个非常非常长的中文歌曲标题".repeat(3);
    const lines = wrapTitle(ctx, title, 200, 2);
    expect(lines.length).toBe(2);
    expect(lines[0].length).toBeLessThanOrEqual(20);
    // the ellipsis marks that text was dropped - it is visible, not silent
    expect(lines[1].endsWith("…")).toBe(true);
  });

  it("keeps a short title on one line", () => {
    const lines = wrapTitle(fakeCtx(10), "晴天", 400, 2);
    expect(lines).toEqual(["晴天"]);
  });

  it("falls back to a placeholder for an empty title", () => {
    expect(wrapTitle(fakeCtx(10), "   ", 200, 2)).toEqual(["未命名谱面"]);
  });
});

describe("export file naming (V1.1-B)", () => {
  it("follows PocketScore_歌曲_谱种_日期 for single PNG", () => {
    const name = exportFileName({
      title: "晴天",
      mode: "grid",
      ext: "png",
      date: new Date(2026, 10, 26),
    });
    expect(name).toBe("PocketScore_晴天_格子谱_20261126.png");
  });

  it("numbers pages for multi-page PNG exports", () => {
    const name = exportFileName({
      title: "晴天",
      mode: "jianpu",
      ext: "png",
      date: new Date(2026, 0, 5),
      page: 3,
      total: 5,
    });
    expect(name).toBe("PocketScore_晴天_数字谱_20260105_第3页.png");
  });

  it("uses the documented ZIP and PDF names", () => {
    expect(exportFileName({ title: "晴天", mode: "grid", ext: "zip" })).toBe(
      "PocketScore_晴天_ScoreImages.zip",
    );
    expect(exportFileName({ title: "晴天", mode: "grid", ext: "pdf" })).toBe("PocketScore_晴天.pdf");
  });

  it("strips characters that are illegal on Windows without dropping CJK", () => {
    const name = sanitiseFileNamePart('晴天/你好:世界*?"<>|');
    expect(name).toBe("晴天_你好_世界_");  // a run of illegal chars collapses to one separator
    expect(name).not.toMatch(/[\\/:*?"<>|]/);
  });

  it("removes control characters and trailing dots", () => {
    expect(sanitiseFileNamePart("ab\u0000cd...")).toBe("abcd");
  });

  it("truncates long names without splitting a surrogate pair", () => {
    const emoji = "🎹";
    const long = emoji.repeat(40);
    const safe = sanitiseFileNamePart(long, 9);
    expect(safe.length).toBeLessThanOrEqual(9);
    // no lone surrogate at the end
    const lastCode = safe.charCodeAt(safe.length - 1);
    expect(lastCode >= 0xd800 && lastCode <= 0xdbff).toBe(false);
  });

  it("appends a counter so re-exporting does not overwrite the previous file", () => {
    const first = exportFileName({ title: "晴天", mode: "grid", ext: "pdf" });
    const second = exportFileName({ title: "晴天", mode: "grid", ext: "pdf", duplicate: 2 });
    expect(first).not.toBe(second);
    expect(second).toBe("PocketScore_晴天_2.pdf");
  });

  it("labels every export mode", () => {
    expect(modeLabel("grid")).toBe("格子谱");
    expect(modeLabel("jianpu")).toBe("数字谱");
    expect(modeLabel("keyboard")).toBe("键盘谱");
    expect(modeLabel("combined")).toBe("双谱");
    expect(modeLabel("full")).toBe("完整谱面");
  });

  it("formats the date stamp as yyyymmdd", () => {
    expect(dateStamp(new Date(2026, 8, 7))).toBe("20260907");
  });
});

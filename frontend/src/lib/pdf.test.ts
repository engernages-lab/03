import { describe, expect, it } from "vitest";
import { createPdf, escapePdfText, pdfHexString, pointsFromPixels, type PdfPageImage } from "./pdf";

function page(fill = 1): PdfPageImage {
  // a tiny fake JPEG: the writer must not care about the actual image content
  return {
    data: new Uint8Array([0xff, 0xd8, 0xff, 0xe0, ...Array(32).fill(fill), 0xff, 0xd9]),
    pixelWidth: 1240,
    pixelHeight: 1754,
    pageWidth: 595.2,
    pageHeight: 841.9,
  };
}

const decoder = new TextDecoder("latin1");

describe("pdf writer", () => {
  it("emits a valid PDF skeleton with an xref table that points at objects", () => {
    const bytes = createPdf([page()], { title: "测试" });
    const text = decoder.decode(bytes);
    expect(text.startsWith("%PDF-1.4")).toBe(true);
    expect(text.trimEnd().endsWith("%%EOF")).toBe(true);
    expect(text).toContain("/Type /Catalog");
    expect(text).toContain("/Type /Pages /Count 1");
    expect(text).toContain("/Subtype /Image");
    expect(text).toContain("/Filter /DCTDecode");
    expect(text).toContain("startxref");

    // every xref entry must point at "N 0 obj"
    const xrefIndex = text.lastIndexOf("\nxref\n");
    const entries = text
      .slice(xrefIndex)
      .split("\n")
      .filter((line) => /^\d{10} 00000 n $/.test(line));
    expect(entries.length).toBeGreaterThan(3);
    entries.forEach((entry, index) => {
      const offset = Number(entry.slice(0, 10));
      const slice = text.slice(offset, offset + 24);
      expect(slice.startsWith(`${index + 1} 0 obj`)).toBe(true);
    });
  });

  it("writes one page object per image and keeps the order", () => {
    const bytes = createPdf([page(1), page(2), page(3)], { title: "三页" });
    const text = decoder.decode(bytes);
    expect(text).toContain("/Count 3");
    const kids = text.match(/\/Kids \[([^\]]+)\]/)?.[1] ?? "";
    // three "<pageId> 0 R" references, in order
    expect(kids.trim().split("  ").join(" ").match(/\d+ 0 R/g)).toHaveLength(3);
  });

  it("stores a CJK title as a UTF-16BE hex string", () => {
    const hex = pdfHexString("晴天");
    expect(hex.startsWith("<FEFF")).toBe(true);
    // 晴 U+6674, 天 U+5929
    expect(hex).toBe("<FEFF66745929>");
    const bytes = createPdf([page()], { title: "晴天", author: "周杰伦" });
    expect(decoder.decode(bytes)).toContain("/Title <FEFF66745929>");
  });

  it("escapes PDF literal string punctuation", () => {
    expect(escapePdfText("a(b)c\\d")).toBe("a\\(b\\)c\\\\d");
  });

  it("refuses to build an empty PDF", () => {
    expect(() => createPdf([], { title: "x" })).toThrow(/至少一页/);
  });

  it("converts pixels to PDF points at the given DPI", () => {
    expect(pointsFromPixels(2480, 300)).toBe(595.2);
    expect(pointsFromPixels(3508, 300)).toBe(841.92);
    expect(pointsFromPixels(1080, 150)).toBe(518.4);
  });
});

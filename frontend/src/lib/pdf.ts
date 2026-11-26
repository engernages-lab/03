/**
 * Minimal image-based PDF writer.
 *
 * Each score page is rendered to a canvas at the requested DPI and embedded as
 * a JPEG (DCTDecode) in its own PDF page. This is a **bitmap PDF**, not a vector
 * score: the resolution limit is exactly the pixel size of the rendered page,
 * which the UI states next to the export button.
 *
 * Kept dependency-free so the export stack stays auditable and testable.
 */

export interface PdfPageImage {
  /** JPEG bytes (already compressed). */
  data: Uint8Array;
  pixelWidth: number;
  pixelHeight: number;
  /** Page size in PDF points (1/72 inch). */
  pageWidth: number;
  pageHeight: number;
}

const encoder = new TextEncoder();

function ascii(text: string): Uint8Array {
  return encoder.encode(text);
}

/** Escape a PDF literal string (parentheses and backslashes). */
export function escapePdfText(text: string): string {
  return text.replace(/\\/g, "\\\\").replace(/\(/g, "\\(").replace(/\)/g, "\\)");
}

/** Convert a UTF-16 string to a PDF hex string for the Info dictionary. */
export function pdfHexString(text: string): string {
  let hex = "FEFF"; // UTF-16BE BOM so readers know it is unicode
  for (const char of text) {
    const code = char.codePointAt(0) ?? 0;
    if (code <= 0xffff) {
      hex += code.toString(16).toUpperCase().padStart(4, "0");
    } else {
      // surrogate pair
      const adjusted = code - 0x10000;
      const high = 0xd800 + (adjusted >> 10);
      const low = 0xdc00 + (adjusted & 0x3ff);
      hex += high.toString(16).toUpperCase().padStart(4, "0");
      hex += low.toString(16).toUpperCase().padStart(4, "0");
    }
  }
  return `<${hex}>`;
}

class PdfBuilder {
  private chunks: Uint8Array[] = [];
  private length = 0;

  push(data: Uint8Array | string): void {
    const bytes = typeof data === "string" ? ascii(data) : data;
    this.chunks.push(bytes);
    this.length += bytes.length;
  }

  get offset(): number {
    return this.length;
  }

  toBytes(): Uint8Array {
    const output = new Uint8Array(this.length);
    let cursor = 0;
    for (const chunk of this.chunks) {
      output.set(chunk, cursor);
      cursor += chunk.length;
    }
    return output;
  }
}

export interface PdfOptions {
  title: string;
  author?: string;
  subject?: string;
  creator?: string;
}

/**
 * Build a multi-page PDF from rendered page images.
 *
 * Object layout: 1 catalog, 2 pages tree, 3 info, then per page
 * (page object, image xobject, content stream).
 */
export function createPdf(pages: PdfPageImage[], options: PdfOptions): Uint8Array {
  if (!pages.length) {
    throw new Error("PDF 需要至少一页");
  }
  const builder = new PdfBuilder();
  const offsets: number[] = [];

  builder.push("%PDF-1.4\n");
  // binary comment so tools treat the file as binary
  builder.push(new Uint8Array([0x25, 0xe2, 0xe3, 0xcf, 0xd3, 0x0a]));

  const objectCount = 3 + pages.length * 3;
  const objectOffsets = new Map<number, number>();
  const startObject = (id: number) => {
    objectOffsets.set(id, builder.offset);
    builder.push(`${id} 0 obj\n`);
  };
  const endObject = () => builder.push("endobj\n");

  // 1: catalog
  startObject(1);
  builder.push("<< /Type /Catalog /Pages 2 0 R >>\n");
  endObject();

  // 2: pages tree
  startObject(2);
  const kids = pages.map((_, index) => `${4 + index * 3} 0 R`).join(" ");
  builder.push(`<< /Type /Pages /Count ${pages.length} /Kids [${kids}] >>\n`);
  endObject();

  // 3: info
  startObject(3);
  builder.push(
    `<< /Title ${pdfHexString(options.title)}` +
      (options.author ? ` /Author ${pdfHexString(options.author)}` : "") +
      (options.subject ? ` /Subject ${pdfHexString(options.subject)}` : "") +
      ` /Creator ${pdfHexString(options.creator ?? "PocketScore AI")}` +
      ` /Producer ${pdfHexString("PocketScore AI score export")} >>\n`,
  );
  endObject();

  pages.forEach((page, index) => {
    const pageId = 4 + index * 3;
    const imageId = pageId + 1;
    const contentId = pageId + 2;

    startObject(pageId);
    builder.push(
      `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${page.pageWidth} ${page.pageHeight}] ` +
        `/Resources << /XObject << /Im0 ${imageId} 0 R >> >> /Contents ${contentId} 0 R >>\n`,
    );
    endObject();

    startObject(imageId);
    builder.push(
      `<< /Type /XObject /Subtype /Image /Width ${page.pixelWidth} /Height ${page.pixelHeight} ` +
        `/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length ${page.data.length} >>\nstream\n`,
    );
    builder.push(page.data);
    builder.push("\nendstream\n");
    endObject();

    const content = `q\n${page.pageWidth} 0 0 ${page.pageHeight} 0 0 cm\n/Im0 Do\nQ\n`;
    startObject(contentId);
    builder.push(`<< /Length ${content.length} >>\nstream\n${content}endstream\n`);
    endObject();
  });

  // cross-reference table
  const xrefOffset = builder.offset;
  builder.push(`xref\n0 ${objectCount + 1}\n`);
  builder.push("0000000000 65535 f \n");
  for (let id = 1; id <= objectCount; id += 1) {
    const offset = objectOffsets.get(id) ?? 0;
    builder.push(`${offset.toString().padStart(10, "0")} 00000 n \n`);
  }
  builder.push(
    `trailer\n<< /Size ${objectCount + 1} /Root 1 0 R /Info 3 0 R >>\nstartxref\n${xrefOffset}\n%%EOF\n`,
  );
  offsets.length = 0;
  return builder.toBytes();
}

/** Point size for a page given its pixel size and DPI (1 pt = 1/72 inch). */
export function pointsFromPixels(pixels: number, dpi: number): number {
  return Math.round((pixels / dpi) * 72 * 100) / 100;
}

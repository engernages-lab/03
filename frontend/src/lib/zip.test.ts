import { describe, expect, it } from "vitest";
import { createZip, crc32 } from "./zip";

function bytes(text: string): Uint8Array {
  return new TextEncoder().encode(text);
}

function readU16(view: DataView, offset: number): number {
  return view.getUint16(offset, true);
}
function readU32(view: DataView, offset: number): number {
  return view.getUint32(offset, true);
}

describe("crc32", () => {
  it("matches the known CRC of 'abc'", () => {
    expect(crc32(bytes("abc"))).toBe(0x352441c2);
  });

  it("returns 0 for empty input", () => {
    expect(crc32(new Uint8Array())).toBe(0);
  });
});

describe("createZip", () => {
  it("writes a valid local header and end-of-central-directory", () => {
    const zip = createZip([
      { name: "a.png", data: bytes("hello") },
      { name: "b.png", data: bytes("world!") },
    ]);
    const view = new DataView(zip.buffer);

    expect(readU32(view, 0)).toBe(0x04034b50); // local file header
    expect(readU16(view, 8)).toBe(0); // stored
    expect(readU32(view, 18)).toBe(5); // size of "hello"
    expect(new TextDecoder().decode(zip.slice(30, 35))).toBe("a.png");

    // end of central directory at the tail
    const endOffset = zip.length - 22;
    expect(readU32(view, endOffset)).toBe(0x06054b50);
    expect(readU16(view, endOffset + 8)).toBe(2); // entries on this disk
    expect(readU16(view, endOffset + 10)).toBe(2); // entries total
  });

  it("records the correct CRC for each entry", () => {
    const payload = bytes("abc");
    const zip = createZip([{ name: "x.png", data: payload }]);
    const view = new DataView(zip.buffer);
    expect(readU32(view, 14)).toBe(crc32(payload));
  });

  it("handles an empty archive", () => {
    const zip = createZip([]);
    expect(zip.length).toBe(22);
    expect(readU32(new DataView(zip.buffer), 0)).toBe(0x06054b50);
  });

  it("keeps UTF-8 file names intact", () => {
    const name = "PocketScore_测试_第1页.png";
    const zip = createZip([{ name, data: bytes("x") }]);
    const nameLength = readU16(new DataView(zip.buffer), 26);
    const decoded = new TextDecoder().decode(zip.slice(30, 30 + nameLength));
    expect(decoded).toBe(name);
  });
});

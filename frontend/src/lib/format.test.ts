import { describe, expect, it } from "vitest";
import { formatBytes, formatDuration, formatRelative, clamp } from "./format";

describe("formatDuration", () => {
  it("formats minutes and seconds", () => {
    expect(formatDuration(0)).toBe("0:00");
    expect(formatDuration(9)).toBe("0:09");
    expect(formatDuration(75)).toBe("1:15");
    expect(formatDuration(599)).toBe("9:59");
  });

  it("adds an hour component when needed", () => {
    expect(formatDuration(3600)).toBe("1:00:00");
    expect(formatDuration(3725)).toBe("1:02:05");
  });

  it("returns a placeholder for missing or invalid input", () => {
    expect(formatDuration(undefined)).toBe("--:--");
    expect(formatDuration(null)).toBe("--:--");
    expect(formatDuration(Number.NaN)).toBe("--:--");
    expect(formatDuration(-5)).toBe("--:--");
  });
});

describe("formatBytes", () => {
  it("scales units", () => {
    expect(formatBytes(0)).toBe("0 B");
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(1024)).toBe("1 KB");
    expect(formatBytes(1536)).toBe("1.5 KB");
    expect(formatBytes(5 * 1024 * 1024)).toBe("5 MB");
  });
});

describe("formatRelative", () => {
  it("describes recent timestamps", () => {
    const now = new Date().toISOString();
    expect(formatRelative(now)).toBe("刚刚");
    const twoHoursAgo = new Date(Date.now() - 2 * 3600 * 1000).toISOString();
    expect(formatRelative(twoHoursAgo)).toBe("2 小时前");
  });

  it("falls back for empty input", () => {
    expect(formatRelative(null)).toBe("—");
  });
});

describe("clamp", () => {
  it("bounds values", () => {
    expect(clamp(5, 0, 10)).toBe(5);
    expect(clamp(-1, 0, 10)).toBe(0);
    expect(clamp(11, 0, 10)).toBe(10);
  });
});

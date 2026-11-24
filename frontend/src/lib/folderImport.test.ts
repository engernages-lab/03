import { describe, expect, it, vi } from "vitest";
import { audioFilesFromInput, isAudioFile, uploadSequentially } from "./folderImport";

function file(name: string): File {
  return new File([new Uint8Array([1, 2, 3])], name, { type: "audio/mpeg" });
}

function fileList(files: File[]): FileList {
  const list = {
    length: files.length,
    item: (index: number) => files[index] ?? null,
    ...files.reduce<Record<number, File>>((acc, entry, index) => {
      acc[index] = entry;
      return acc;
    }, {}),
    [Symbol.iterator]: () => files[Symbol.iterator](),
  };
  return list as unknown as FileList;
}

describe("isAudioFile", () => {
  it("accepts every supported container case-insensitively", () => {
    for (const name of ["a.mp3", "b.WAV", "c.Flac", "d.m4a", "e.aac", "f.ogg", "g.opus"]) {
      expect(isAudioFile(name)).toBe(true);
    }
  });

  it("rejects non-audio files", () => {
    for (const name of ["cover.jpg", "notes.txt", "song.aiff", "archive.zip", "noext"]) {
      expect(isAudioFile(name)).toBe(false);
    }
  });
});

describe("audioFilesFromInput", () => {
  it("keeps only audio files from a folder pick", () => {
    const files = [file("01.mp3"), file("cover.jpg"), file("02.flac"), file("readme.txt")];
    const picked = audioFilesFromInput(fileList(files));
    expect(picked.map((item) => item.name)).toEqual(["01.mp3", "02.flac"]);
  });

  it("handles null input", () => {
    expect(audioFilesFromInput(null)).toEqual([]);
  });
});

describe("uploadSequentially", () => {
  it("uploads every file and reports progress", async () => {
    const uploaded: string[] = [];
    const progress: number[] = [];
    const outcome = await uploadSequentially(
      [file("a.mp3"), file("b.mp3"), file("c.mp3")],
      async (item) => {
        uploaded.push(item.name);
      },
      (done) => progress.push(done),
    );
    expect(outcome.imported).toBe(3);
    expect(outcome.failed).toEqual([]);
    expect(uploaded).toEqual(["a.mp3", "b.mp3", "c.mp3"]);
    expect(progress).toEqual([0, 1, 2, 3]);
  });

  it("continues after a failure and records the reason", async () => {
    const upload = vi.fn(async (item: File) => {
      if (item.name === "bad.mp3") throw new Error("415 Unsupported Media Type");
    });
    const outcome = await uploadSequentially([file("ok.mp3"), file("bad.mp3"), file("ok2.mp3")], upload);
    expect(outcome.imported).toBe(2);
    expect(outcome.failed).toHaveLength(1);
    expect(outcome.failed[0]).toEqual({ name: "bad.mp3", reason: "415 Unsupported Media Type" });
    expect(upload).toHaveBeenCalledTimes(3);
  });

  it("handles an empty selection", async () => {
    const outcome = await uploadSequentially([], async () => undefined);
    expect(outcome).toEqual({ imported: 0, failed: [] });
  });
});

/** Folder / multi-file import helpers for the local music library. */

export const AUDIO_EXTENSIONS = [".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".opus"];

export function isAudioFile(name: string): boolean {
  const lower = name.toLowerCase();
  return AUDIO_EXTENSIONS.some((ext) => lower.endsWith(ext));
}

/** The browser exposes ``webkitGetAsEntry`` outside the TypeScript lib typings. */
interface FileSystemEntryLike {
  isFile: boolean;
  isDirectory: boolean;
  name: string;
  file?: (success: (file: File) => void, error?: (err: unknown) => void) => void;
  createReader?: () => {
    readEntries: (
      success: (entries: FileSystemEntryLike[]) => void,
      error?: (err: unknown) => void,
    ) => void;
  };
}

function readEntryBatch(
  reader: NonNullable<FileSystemEntryLike["createReader"]> extends () => infer R
    ? R
    : never,
): Promise<FileSystemEntryLike[]> {
  return new Promise((resolve, reject) => {
    reader.readEntries(resolve, reject);
  });
}

async function walkEntry(entry: FileSystemEntryLike, out: File[]): Promise<void> {
  if (entry.isFile && entry.file) {
    const file = await new Promise<File | null>((resolve) => {
      entry.file!(
        (value) => resolve(value),
        () => resolve(null),
      );
    });
    if (file && isAudioFile(file.name)) out.push(file);
    return;
  }
  if (entry.isDirectory && entry.createReader) {
    const reader = entry.createReader();
    // readEntries returns at most 100 entries per call; loop until empty.
    for (;;) {
      const batch = await readEntryBatch(reader);
      if (!batch.length) break;
      for (const child of batch) await walkEntry(child, out);
    }
  }
}

/**
 * Recursively collect audio files from a drop event, including dropped folders.
 * Falls back to ``dataTransfer.files`` when the entries API is unavailable.
 */
export async function collectDroppedAudio(dataTransfer: DataTransfer): Promise<File[]> {
  const items = Array.from(dataTransfer.items ?? []);
  const entries = items
    .filter((item) => item.kind === "file")
    .map((item) => {
      const extended = item as DataTransferItem & {
        webkitGetAsEntry?: () => FileSystemEntryLike | null;
        getAsFile?: () => File | null;
      };
      const entry = extended.webkitGetAsEntry?.() ?? null;
      if (entry) return entry;
      const file = extended.getAsFile?.() ?? null;
      return file
        ? ({
            isFile: true,
            isDirectory: false,
            name: file.name,
            file: (ok: (value: File) => void) => ok(file),
          } as FileSystemEntryLike)
        : null;
    })
    .filter((entry): entry is FileSystemEntryLike => entry !== null);

  if (!entries.length) {
    return Array.from(dataTransfer.files ?? []).filter((file) => isAudioFile(file.name));
  }

  const collected: File[] = [];
  for (const entry of entries) await walkEntry(entry, collected);
  return collected;
}

/** Files picked through an ``<input webkitdirectory>`` element. */
export function audioFilesFromInput(files: FileList | null): File[] {
  return Array.from(files ?? []).filter((file) => isAudioFile(file.name));
}

export interface UploadOutcome {
  imported: number;
  failed: { name: string; reason: string }[];
}

/** Upload sequentially (SQLite-friendly) while reporting progress. */
export async function uploadSequentially(
  files: File[],
  upload: (file: File) => Promise<unknown>,
  onProgress?: (done: number, total: number, current: string) => void,
): Promise<UploadOutcome> {
  const failed: { name: string; reason: string }[] = [];
  let imported = 0;
  for (let index = 0; index < files.length; index += 1) {
    const file = files[index];
    onProgress?.(index, files.length, file.name);
    try {
      await upload(file);
      imported += 1;
    } catch (error) {
      failed.push({ name: file.name, reason: error instanceof Error ? error.message : "上传失败" });
    }
  }
  onProgress?.(files.length, files.length, "");
  return { imported, failed };
}

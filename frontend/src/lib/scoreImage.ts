/**
 * Score image export: pagination + canvas rendering.
 *
 * Everything here reads the *compiled* notation view models that the backend
 * produced from the one MusicDocument, so an exported page can never disagree
 * with the editor. Rendering targets an offscreen canvas at the requested pixel
 * size - it never captures the browser viewport.
 */

import type { DualNotationResponse, GridViewModel, JianpuViewModel } from "./types";
import { resolvePageSize, type Dpi, type PageFormat, type ResolvedSize } from "./pageFormats";

export type { Dpi, PageFormat, ResolvedSize } from "./pageFormats";

export type ExportMode = "grid" | "jianpu" | "keyboard" | "combined" | "full";
export type PageSizeId = "hd" | "uhd" | "4k";
export type ThemeId = "classic" | "dark" | "soft";

export const PAGE_SIZES: Record<PageSizeId, { width: number; height: number; label: string }> = {
  hd: { width: 1080, height: 1920, label: "标准高清 1080 × 1920" },
  uhd: { width: 1440, height: 2560, label: "超清 1440 × 2560" },
  "4k": { width: 2160, height: 3840, label: "4K 竖版 2160 × 3840" },
};

export interface Theme {
  id: ThemeId;
  label: string;
  background: string;
  panel: string;
  text: string;
  muted: string;
  accent: string;
  grid: string;
  note: string;
  noteText: string;
  watermark: string;
}

export const THEMES: Record<ThemeId, Theme> = {
  classic: {
    id: "classic",
    label: "CLASSIC 白底黑字",
    background: "#ffffff",
    panel: "#f4f4f5",
    text: "#111114",
    muted: "#6b7280",
    accent: "#2563eb",
    grid: "#d4d4d8",
    note: "#111114",
    noteText: "#ffffff",
    watermark: "rgba(17,17,20,0.35)",
  },
  dark: {
    id: "dark",
    label: "DARK 深色科技",
    background: "#0b0d12",
    panel: "#141821",
    text: "#f4f6fb",
    muted: "#8b93a7",
    accent: "#22d3ee",
    grid: "#232936",
    note: "#22d3ee",
    noteText: "#04121a",
    watermark: "rgba(244,246,251,0.35)",
  },
  soft: {
    id: "soft",
    label: "SOFT 柔和浅色",
    background: "#fbf7f1",
    panel: "#f3ece1",
    text: "#3b3226",
    muted: "#8a7c6a",
    accent: "#c2703d",
    grid: "#e2d7c7",
    note: "#c2703d",
    noteText: "#fffaf4",
    watermark: "rgba(59,50,38,0.35)",
  },
};

export interface ExportOptions {
  mode: ExportMode;
  size: PageSizeId;
  theme: ThemeId;
  showInfo: boolean;
  showWatermark: boolean;
  /** "all" exports every page (ZIP when >1); "current" exports page 1 only. */
  scope?: "all" | "current";
  measuresPerPage?: number;
  /** V1.1-B: paper format (defaults to the legacy 9:16 story format). */
  format?: PageFormat;
  /** V1.1-B: print resolution for A4/PDF exports. */
  dpi?: Dpi;
  /** V1.1-B: independent toggles for the title/author block. */
  showTitle?: boolean;
  showAuthor?: boolean;
}

export interface ScorePage {
  index: number;
  total: number;
  measures: number[];
}

const MARGIN_RATIO = 0.055;

/**
 * Resolve the concrete pixel canvas for the chosen format.
 *
 * A4 is computed from millimetres at the requested DPI (never by stretching a
 * 9:16 canvas); the 9:16 presets are returned unchanged for compatibility.
 */
export function resolveExportSize(
  options: ExportOptions,
  contentHeight?: number,
): ResolvedSize {
  const format: PageFormat = options.format ?? "story";
  return resolvePageSize({
    format,
    dpi: options.dpi ?? 150,
    storyPreset: options.size,
    contentHeight,
  });
}

/** Format-aware measure budget, derived from the usable page width. */
export function measuresPerPage(
  mode: ExportMode,
  pageWidth: number,
  slotsPerMeasure: number,
  // kept for call-site compatibility; vertical density is handled by the row
  // renderer, since a page always shows every key row
  _pageHeight?: number,
): number {
  const usable = pageWidth * (1 - 2 * MARGIN_RATIO) - pageWidth * 0.1; // minus key labels
  // target cell width: readable at every page size without wasting a whole page
  // on a single measure (capped at 18 px, floor of 10 px)
  const slotWidth = Math.max(10, Math.min(18, Math.round(pageWidth / 70)));
  const perMeasure = slotWidth * Math.max(1, slotsPerMeasure);
  const fit = Math.floor(usable / perMeasure);
  const cap = mode === "combined" || mode === "full" ? 2 : 3;
  return Math.max(1, Math.min(cap, fit || 1));
}

/**
 * Split the score into pages on measure boundaries.
 *
 * Whole measures only: a page never starts or ends mid-measure, which is what
 * keeps chords and ties intact.
 */
export function paginate(totalMeasures: number, perPage: number): ScorePage[] {
  const limit = Math.max(1, Math.floor(perPage));
  const measures = Array.from({ length: Math.max(0, totalMeasures) }, (_, index) => index + 1);
  const pages: ScorePage[] = [];
  for (let start = 0; start < measures.length; start += limit) {
    pages.push({
      index: pages.length + 1,
      total: 0,
      measures: measures.slice(start, start + limit),
    });
  }
  if (!pages.length) {
    pages.push({ index: 1, total: 1, measures: [] });
  }
  const total = pages.length;
  return pages.map((page) => ({ ...page, total }));
}

function roundRect(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  width: number,
  height: number,
  radius: number,
): void {
  const r = Math.min(radius, width / 2, height / 2);
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + width, y, x + width, y + height, r);
  ctx.arcTo(x + width, y + height, x, y + height, r);
  ctx.arcTo(x, y + height, x, y, r);
  ctx.arcTo(x, y, x + width, y, r);
  ctx.closePath();
}

export interface RenderContext {
  ctx: CanvasRenderingContext2D;
  width: number;
  height: number;
  theme: Theme;
  options: ExportOptions;
  dual: DualNotationResponse;
}

const FONT_STACK =
  '"Inter", "Noto Sans SC", "PingFang SC", "Microsoft YaHei", "Segoe UI", system-ui, sans-serif';
const MUSIC_STACK = '"Noto Music", "Segoe UI Symbol", "DejaVu Sans", serif';

/** Wrap a title into at most `maxLines` lines that fit `maxWidth`. */
export function wrapTitle(
  ctx: CanvasRenderingContext2D,
  title: string,
  maxWidth: number,
  maxLines = 2,
): string[] {
  const text = (title || "未命名谱面").trim();
  if (!text) return ["未命名谱面"];
  const lines: string[] = [];
  let rest = text;
  while (rest.length > 0 && lines.length < maxLines) {
    if (ctx.measureText(rest).width <= maxWidth) {
      lines.push(rest);
      rest = "";
      break;
    }
    // binary search the longest prefix that fits
    let low = 1;
    let high = rest.length;
    while (low < high) {
      const mid = Math.ceil((low + high) / 2);
      if (ctx.measureText(rest.slice(0, mid)).width <= maxWidth) {
        low = mid;
      } else {
        high = mid - 1;
      }
    }
    let cut = Math.max(1, low);
    // prefer breaking at a space for latin titles
    const space = rest.lastIndexOf(" ", cut);
    if (space > cut * 0.6) cut = space;
    lines.push(rest.slice(0, cut).trimEnd());
    rest = rest.slice(cut).trimStart();
  }
  if (rest.length > 0) {
    // truncated: mark it instead of silently dropping characters
    const last = lines[lines.length - 1] ?? "";
    let trimmed = last;
    while (trimmed.length > 1 && ctx.measureText(`${trimmed}…`).width > maxWidth) {
      trimmed = trimmed.slice(0, -1);
    }
    lines[lines.length - 1] = `${trimmed}…`;
  }
  return lines.length ? lines : ["未命名谱面"];
}

function drawHeader(render: RenderContext, page: ScorePage): number {
  const { ctx, width, height, theme, options, dual } = render;
  const margin = width * MARGIN_RATIO;
  const usable = width - margin * 2;
  let y = margin + height * 0.012;

  if (!options.showInfo) {
    return margin + height * 0.02;
  }

  const showTitle = options.showTitle !== false;
  const showAuthor = options.showAuthor !== false;

  if (showTitle) {
    ctx.fillStyle = theme.text;
    let fontPx = Math.round(width * 0.052);
    ctx.font = `700 ${fontPx}px ${FONT_STACK}`;
    let lines = wrapTitle(ctx, dual.document.title || "未命名谱面", usable, 2);
    // shrink once if a single line still would not fit
    if (lines.length === 2 && lines[1].endsWith("…")) {
      fontPx = Math.round(width * 0.042);
      ctx.font = `700 ${fontPx}px ${FONT_STACK}`;
      lines = wrapTitle(ctx, dual.document.title || "未命名谱面", usable, 2);
    }
    ctx.textBaseline = "top";
    const lineHeight = fontPx * 1.18;
    lines.forEach((line, index) => {
      ctx.fillText(line, margin, y + index * lineHeight);
    });
    y += lines.length * lineHeight + width * 0.006;
  }

  if (showAuthor) {
    ctx.font = `400 ${Math.round(width * 0.026)}px ${FONT_STACK}`;
    ctx.fillStyle = theme.muted;
    const artist = dual.document.artist || "未知艺术家";
    ctx.textBaseline = "top";
    ctx.fillText(artist, margin, y);
    y += width * 0.036;
  }

  // meta chips - wrapped onto extra rows if they would overflow the page
  const chips = [
    `BPM ${Math.round(dual.document.tempo)}`,
    `调号 ${dual.document.key_signature}`,
    `${dual.document.time_signature.numerator}/${dual.document.time_signature.denominator}`,
    `${dual.grid.stats.notes} 音符`,
    `第 ${page.index} / ${page.total} 页`,
  ];
  ctx.font = `500 ${Math.round(width * 0.022)}px ${FONT_STACK}`;
  const padding = width * 0.012;
  const chipHeight = width * 0.042;
  let x = margin;
  for (const chip of chips) {
    const textWidth = ctx.measureText(chip).width;
    const chipWidth = textWidth + padding * 2;
    if (x + chipWidth > width - margin) {
      x = margin;
      y += chipHeight + height * 0.008;
    }
    ctx.fillStyle = theme.panel;
    roundRect(ctx, x, y, chipWidth, chipHeight, chipHeight / 2);
    ctx.fill();
    ctx.fillStyle = theme.muted;
    ctx.textBaseline = "top";
    ctx.fillText(chip, x + padding, y + chipHeight * 0.26);
    x += chipWidth + width * 0.012;
  }
  y += chipHeight + height * 0.012;

  ctx.strokeStyle = theme.grid;
  ctx.lineWidth = Math.max(1, width * 0.002);
  ctx.beginPath();
  ctx.moveTo(margin, y);
  ctx.lineTo(width - margin, y);
  ctx.stroke();
  return y + height * 0.014;
}

function drawFooter(render: RenderContext, page: ScorePage): void {
  const { ctx, width, height, theme, options } = render;
  const margin = width * MARGIN_RATIO;
  const baseline = height - margin * 0.75;

  ctx.font = `400 ${Math.round(width * 0.02)}px ${FONT_STACK}`;
  ctx.fillStyle = theme.muted;
  ctx.textBaseline = "bottom";
  const range = page.measures.length
    ? `小节 ${page.measures[0]}–${page.measures[page.measures.length - 1]}`
    : "空谱面";
  ctx.fillText(`${range} · 第 ${page.index} / ${page.total} 页`, margin, baseline);

  if (options.showWatermark) {
    ctx.textAlign = "right";
    ctx.fillStyle = theme.watermark;
    ctx.font = `600 ${Math.round(width * 0.021)}px ${FONT_STACK}`;
    ctx.fillText("PocketScore AI", width - margin, baseline);
    ctx.textAlign = "left";
  }
}

function drawGridSection(
  render: RenderContext,
  grid: GridViewModel,
  page: ScorePage,
  top: number,
  height: number,
): void {
  const { ctx, width, theme } = render;
  const margin = width * MARGIN_RATIO;
  const rows = [...grid.rows];
  if (!rows.length) {
    return;
  }

  const labelWidth = width * 0.1;
  const gridWidth = width - margin * 2 - labelWidth;
  const perPage = Math.max(1, page.measures.length);
  const slots = Math.max(1, grid.slots_per_measure);
  const cellWidth = gridWidth / (perPage * slots);
  // Fill the page instead of leaving the score floating at the top.
  const rowHeight = Math.min(height / rows.length, width * 0.115);
  const blockHeight = rowHeight * rows.length;
  const blockTop = top + Math.max(0, (height - blockHeight) / 2) * 0.6;
  const cellHeight = rowHeight;

  ctx.textBaseline = "middle";
  rows.forEach((row, rowIndex) => {
    const y = blockTop + rowIndex * cellHeight;
    ctx.fillStyle = theme.panel;
    roundRect(ctx, margin, y + cellHeight * 0.1, labelWidth - width * 0.008, cellHeight * 0.8, cellHeight * 0.18);
    ctx.fill();
    ctx.fillStyle = theme.text;
    ctx.font = `600 ${Math.round(cellHeight * 0.42)}px ${FONT_STACK}`;
    ctx.fillText(row.label.slice(0, 4), margin + width * 0.012, y + cellHeight / 2);

    const cells = row.cells.filter((cell) => page.measures.includes(cell.measure));
    for (const cell of cells) {
      const measureOffset = page.measures.indexOf(cell.measure);
      if (measureOffset < 0) continue;
      const x = margin + labelWidth + (measureOffset * slots + cell.slot) * cellWidth;
      if (cell.state === "note") {
        ctx.fillStyle = cell.color || theme.note;
        roundRect(ctx, x + cellWidth * 0.08, y + cellHeight * 0.12, cellWidth * 0.84, cellHeight * 0.76, cellWidth * 0.18);
        ctx.fill();
      } else if (cell.state === "rest") {
        ctx.fillStyle = theme.muted;
        ctx.font = `500 ${Math.round(cellHeight * 0.4)}px ${MUSIC_STACK}`;
        ctx.fillText("𝄽", x + cellWidth * 0.28, y + cellHeight / 2);
      }
    }
  });

  // measure separators + numbers
  ctx.strokeStyle = theme.grid;
  ctx.lineWidth = Math.max(1, width * 0.0016);
  const totalHeight = rows.length * cellHeight;
  for (let index = 0; index <= perPage; index += 1) {
    const x = margin + labelWidth + index * slots * cellWidth;
    ctx.beginPath();
    ctx.moveTo(x, blockTop);
    ctx.lineTo(x, blockTop + totalHeight);
    ctx.stroke();
  }
  ctx.font = `500 ${Math.round(width * 0.018)}px ${FONT_STACK}`;
  ctx.fillStyle = theme.muted;
  ctx.textBaseline = "bottom";
  page.measures.forEach((measure, index) => {
    const x = margin + labelWidth + index * slots * cellWidth + width * 0.004;
    ctx.fillText(String(measure), x, blockTop - height * 0.006);
  });
}

function drawJianpuSection(
  render: RenderContext,
  jianpu: JianpuViewModel,
  page: ScorePage,
  top: number,
  height: number,
): void {
  const { ctx, width, theme } = render;
  const margin = width * MARGIN_RATIO;
  const measures = jianpu.measures.filter((measure) => page.measures.includes(measure.measure));
  if (!measures.length) {
    return;
  }

  const lineHeight = Math.min(height / Math.max(1, measures.length), width * 0.22);
  const blockTop = top + Math.max(0, height - lineHeight * measures.length) / 2;
  const noteFont = Math.round(Math.min(width * 0.058, lineHeight * 0.34));
  const perLine = Math.max(4, Math.min(16, jianpu.max_notes_per_line || 8));

  measures.forEach((measure, measureIndex) => {
    const y = blockTop + measureIndex * lineHeight;
    ctx.textBaseline = "middle";
    ctx.font = `500 ${Math.round(width * 0.018)}px ${FONT_STACK}`;
    ctx.fillStyle = theme.muted;
    ctx.fillText(`#${measure.measure}`, margin, y + lineHeight * 0.16);

    const startX = margin + width * 0.055;
    const usable = width - margin * 2 - width * 0.055;
    const perRow = Math.min(perLine, Math.max(1, measure.notes.length));
    const stepX = usable / perRow;
    const beatsInMeasure = Math.max(1, measure.beats || 4);

    measure.notes.forEach((note, noteIndex) => {
      const row = Math.floor(noteIndex / perRow);
      const column = noteIndex % perRow;
      // place the degree on its real beat when the note carries one, so the
      // image matches the score's rhythm instead of an even spread
      const beatOffset = Number.isFinite(note.beat_in_measure)
        ? Math.max(0, (note.beat_in_measure as number) - 1)
        : column;
      const x = Number.isFinite(note.beat_in_measure)
        ? startX + Math.min(usable - stepX * 0.5, (beatOffset / beatsInMeasure) * usable)
        : startX + column * stepX;
      const ny = y + lineHeight * 0.5 + row * lineHeight * 0.45;

      ctx.font = `600 ${noteFont}px ${MUSIC_STACK}`;
      ctx.fillStyle = theme.text;
      const token = note.is_rest ? "0" : note.token || "?";
      ctx.fillText(token, x, ny);

      const tokenWidth = ctx.measureText(token).width;
      // octave dots
      if (note.octave > 0) {
        ctx.fillStyle = theme.accent;
        for (let dot = 0; dot < Math.min(note.octave, 3); dot += 1) {
          ctx.beginPath();
          ctx.arc(
            x + tokenWidth * 0.35 + dot * noteFont * 0.26,
            ny - noteFont * 0.62,
            noteFont * 0.09,
            0,
            Math.PI * 2,
          );
          ctx.fill();
        }
      } else if (note.octave < 0) {
        ctx.fillStyle = theme.accent;
        for (let dot = 0; dot < Math.min(-note.octave, 3); dot += 1) {
          ctx.beginPath();
          ctx.arc(
            x + tokenWidth * 0.35 + dot * noteFont * 0.26,
            ny + noteFont * 0.62,
            noteFont * 0.09,
            0,
            Math.PI * 2,
          );
          ctx.fill();
        }
      }

      if (note.accidental) {
        ctx.fillStyle = theme.accent;
        ctx.font = `500 ${Math.round(noteFont * 0.5)}px ${MUSIC_STACK}`;
        ctx.fillText(note.accidental, x - noteFont * 0.32, ny - noteFont * 0.2);
      }

      if (note.duration_label && note.duration_label !== "1") {
        ctx.fillStyle = theme.muted;
        ctx.font = `500 ${Math.round(noteFont * 0.42)}px ${FONT_STACK}`;
        ctx.fillText(note.duration_label, x + tokenWidth * 0.15, ny + noteFont * 0.62);
      }

      if (note.key_label) {
        ctx.fillStyle = theme.muted;
        ctx.font = `500 ${Math.round(noteFont * 0.34)}px ${FONT_STACK}`;
        ctx.fillText(note.key_label, x + tokenWidth * 0.15, ny - noteFont * 0.72);
      }
    });
  });
}

function drawKeyboardSection(
  render: RenderContext,
  grid: GridViewModel,
  page: ScorePage,
  top: number,
  height: number,
): void {
  const { ctx, width, theme } = render;
  const margin = width * MARGIN_RATIO;
  const rows = grid.rows;
  if (!rows.length) return;

  const cellHeight = Math.min(height / rows.length, width * 0.1);
  const keyWidth = width * 0.24;
  const trackWidth = width - margin * 2 - keyWidth;
  const slots = Math.max(1, grid.slots_per_measure) * Math.max(1, page.measures.length);
  const cellWidth = trackWidth / slots;

  rows.forEach((row, rowIndex) => {
    const y = top + rowIndex * cellHeight;
    ctx.fillStyle = theme.panel;
    roundRect(ctx, margin, y + cellHeight * 0.08, keyWidth, cellHeight * 0.84, cellHeight * 0.2);
    ctx.fill();

    ctx.fillStyle = theme.text;
    ctx.font = `700 ${Math.round(cellHeight * 0.4)}px ${FONT_STACK}`;
    ctx.textBaseline = "middle";
    ctx.fillText(row.label.slice(0, 6), margin + width * 0.014, y + cellHeight * 0.4);

    if (row.pitch_name) {
      ctx.fillStyle = theme.muted;
      ctx.font = `500 ${Math.round(cellHeight * 0.26)}px ${FONT_STACK}`;
      ctx.fillText(row.pitch_name, margin + width * 0.014, y + cellHeight * 0.72);
    }

    for (const cell of row.cells) {
      if (cell.state !== "note") continue;
      const measureOffset = page.measures.indexOf(cell.measure);
      if (measureOffset < 0) continue;
      const slotIndex = measureOffset * grid.slots_per_measure + cell.slot;
      const x = margin + keyWidth + slotIndex * cellWidth;
      ctx.fillStyle = cell.color || theme.note;
      roundRect(ctx, x + cellWidth * 0.1, y + cellHeight * 0.22, cellWidth * 0.8, cellHeight * 0.56, cellWidth * 0.2);
      ctx.fill();
    }
  });

  ctx.strokeStyle = theme.grid;
  ctx.lineWidth = Math.max(1, width * 0.0014);
  page.measures.forEach((measure, index) => {
    const x = margin + keyWidth + index * grid.slots_per_measure * cellWidth;
    ctx.beginPath();
    ctx.moveTo(x, top);
    ctx.lineTo(x, top + rows.length * cellHeight);
    ctx.stroke();
    ctx.fillStyle = theme.muted;
    ctx.font = `500 ${Math.round(width * 0.018)}px ${FONT_STACK}`;
    ctx.textBaseline = "bottom";
    ctx.fillText(String(measure), x + width * 0.004, top - height * 0.004);
  });
}

/** Render one page of the score into an existing 2D context. */
export function renderScorePage(render: RenderContext, page: ScorePage): void {
  const { ctx, width, height, theme, options, dual } = render;
  ctx.save();
  ctx.fillStyle = theme.background;
  ctx.fillRect(0, 0, width, height);

  const top = drawHeader(render, page);
  const bottom = height - height * 0.055;
  const contentHeight = Math.max(40, bottom - top);

  const mode = options.mode;
  if (mode === "grid") {
    drawGridSection(render, dual.grid, page, top, contentHeight);
  } else if (mode === "jianpu") {
    drawJianpuSection(render, dual.jianpu, page, top, contentHeight);
  } else if (mode === "keyboard") {
    drawKeyboardSection(render, dual.grid, page, top, contentHeight);
  } else {
    // combined / full: grid on top, jianpu below
    const gridHeight = contentHeight * 0.58;
    drawGridSection(render, dual.grid, page, top, gridHeight);
    const dividerY = top + gridHeight + contentHeight * 0.03;
    ctx.strokeStyle = theme.grid;
    ctx.lineWidth = Math.max(1, width * 0.0016);
    ctx.beginPath();
    ctx.moveTo(width * MARGIN_RATIO, dividerY);
    ctx.lineTo(width - width * MARGIN_RATIO, dividerY);
    ctx.stroke();
    drawJianpuSection(render, dual.jianpu, page, dividerY + contentHeight * 0.03, contentHeight * 0.36);
  }

  drawFooter(render, page);
  ctx.restore();
}

export function pageCountFor(dual: DualNotationResponse, options: ExportOptions): number {
  const size = resolveExportSize(options);
  const perPage =
    options.measuresPerPage ??
    measuresPerPage(options.mode, size.width, dual.grid.slots_per_measure, size.height);
  const totalMeasures = Math.max(dual.grid.stats.measures, dual.jianpu.stats.measures, 1);
  const total = paginate(totalMeasures, perPage).length;
  return options.scope === "current" ? 1 : total;
}

/* ------------------------------------------------------------------ */
/* V1.1-B file naming: PocketScore_<title>_<notation>_<date>           */
/* ------------------------------------------------------------------ */

const MODE_LABEL: Record<ExportMode, string> = {
  grid: "格子谱",
  jianpu: "数字谱",
  keyboard: "键盘谱",
  combined: "双谱",
  full: "完整谱面",
};

export function modeLabel(mode: ExportMode): string {
  return MODE_LABEL[mode] ?? "谱面";
}

/**
 * Make one filename segment safe on Windows/macOS/Linux while keeping CJK.
 * Illegal characters become "_", control chars are dropped, and the result is
 * truncated without splitting a surrogate pair.
 */
export function sanitiseFileNamePart(input: string, maxLength = 40): string {
  const cleaned = (input || "")
    // eslint-disable-next-line no-control-regex
    .replace(/[\u0000-\u001f\u007f]+/g, "")
    .replace(/[\\/:*?"<>|]+/g, "_")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/^[.]+|[. ]+$/g, "");
  const safe = cleaned || "未命名谱面";
  if (safe.length <= maxLength) return safe;
  // avoid cutting a surrogate pair in half
  let cut = maxLength;
  const code = safe.charCodeAt(cut - 1);
  if (code >= 0xd800 && code <= 0xdbff) cut -= 1;
  return safe.slice(0, cut);
}

export function dateStamp(date = new Date()): string {
  const year = date.getFullYear();
  const month = `${date.getMonth() + 1}`.padStart(2, "0");
  const day = `${date.getDate()}`.padStart(2, "0");
  return `${year}${month}${day}`;
}

export interface FileNameInput {
  title: string;
  mode: ExportMode;
  ext: "png" | "zip" | "pdf";
  date?: Date;
  page?: number;
  total?: number;
  /** Counter appended when the same name is generated twice in one session. */
  duplicate?: number;
}

/**
 * Build an export filename.
 *
 * - single PNG: `PocketScore_<title>_<notation>_<yyyymmdd>.png`
 * - paged PNG:  `..._第<N>页.png`
 * - ZIP:        `PocketScore_<title>_ScoreImages.zip`
 * - PDF:        `PocketScore_<title>.pdf`
 */
export function exportFileName(input: FileNameInput): string {
  const title = sanitiseFileNamePart(input.title, 32);
  const suffix = input.duplicate && input.duplicate > 1 ? `_${input.duplicate}` : "";
  const total = input.total ?? 1;
  if (input.ext === "zip") {
    return `PocketScore_${title}_ScoreImages${suffix}.zip`;
  }
  if (input.ext === "pdf") {
    return `PocketScore_${title}${suffix}.pdf`;
  }
  const parts = ["PocketScore", title, modeLabel(input.mode), dateStamp(input.date)];
  const base = parts.join("_");
  if (total > 1) {
    return `${base}_第${input.page ?? 1}页${suffix}.png`;
  }
  return `${base}${suffix}.png`;
}

/** Legacy helper kept for callers/tests that predate the V1.1-B naming. */
export function fileNameFor(title: string, page: number, total: number): string {
  const safe = sanitiseFileNamePart(title, 40);
  if (total <= 1) return `PocketScore_${safe}.png`;
  return `PocketScore_${safe}_第${page}页.png`;
}

export function zipNameFor(title: string): string {
  return exportFileName({ title, mode: "grid", ext: "zip" });
}

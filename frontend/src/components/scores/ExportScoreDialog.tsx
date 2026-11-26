import { useMemo, useRef, useState } from "react";
import { Download, FileImage, FileText, Loader2, Minus, Plus, X } from "lucide-react";
import clsx from "clsx";
import {
  PAGE_SIZES,
  THEMES,
  exportFileName,
  measuresPerPage,
  modeLabel,
  pageCountFor,
  resolveExportSize,
  type ExportMode,
  type ExportOptions,
  type PageFormat,
  type PageSizeId,
  type ThemeId,
  type Dpi,
} from "../../lib/scoreImage";
import {
  blobToBytes,
  planExport,
  renderPageThumbnails,
  renderScoreImages,
  renderScorePdf,
  saveBlob,
} from "../../lib/exportScore";
import { formatMegapixels, physicalSizeLabel } from "../../lib/pageFormats";
import { createZip } from "../../lib/zip";
import type { DualNotationResponse } from "../../lib/types";

const MODES: { id: ExportMode; label: string; hint: string }[] = [
  { id: "grid", label: "格子谱", hint: "口袋键盘格子视图" },
  { id: "jianpu", label: "数字谱", hint: "简谱数字 + 八度点" },
  { id: "keyboard", label: "键盘谱", hint: "仅键位行与节奏位置" },
  { id: "combined", label: "组合谱", hint: "格子谱 + 数字谱同页" },
  { id: "full", label: "完整谱面", hint: "自动分页导出全部" },
];

const FORMATS: { id: PageFormat; label: string; hint: string }[] = [
  { id: "story", label: "9:16 竖版", hint: "1080×1920 起" },
  { id: "a4-portrait", label: "A4 纵向", hint: "210×297 mm" },
  { id: "a4-landscape", label: "A4 横向", hint: "297×210 mm" },
  { id: "long", label: "自适应长图", hint: "按内容加高" },
];

const DPIS: Dpi[] = [150, 300, 600];

/** Names already used in this tab, so a re-export never silently overwrites. */
const usedNames = new Map<string, number>();

function uniqueName(base: (duplicate: number) => string): string {
  let counter = (usedNames.get(base(1)) ?? 0) + 1;
  let name = base(counter);
  while (usedNames.has(name)) {
    counter += 1;
    name = base(counter);
  }
  usedNames.set(base(1), counter);
  usedNames.set(name, counter);
  return name;
}

interface Artifact {
  url: string;
  name: string;
  label: string;
  size: number;
}

export function ExportScoreDialog({
  dual,
  onClose,
}: {
  dual: DualNotationResponse;
  onClose: () => void;
}) {
  const [mode, setMode] = useState<ExportMode>("grid");
  const [format, setFormat] = useState<PageFormat>("story");
  const [size, setSize] = useState<PageSizeId>("hd");
  const [dpi, setDpi] = useState<Dpi>(300);
  const [theme, setTheme] = useState<ThemeId>("classic");
  const [showInfo, setShowInfo] = useState(true);
  const [showTitle, setShowTitle] = useState(true);
  const [showAuthor, setShowAuthor] = useState(true);
  const [showWatermark, setShowWatermark] = useState(true);
  const [scope, setScope] = useState<"all" | "current">("all");
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState({ done: 0, total: 0 });
  const [message, setMessage] = useState<string | null>(null);
  const [thumbs, setThumbs] = useState<{ url: string; index: number }[]>([]);
  const [activePage, setActivePage] = useState(1);
  const [zoom, setZoom] = useState(1);
  const [artifact, setArtifact] = useState<Artifact | null>(null);
  const thumbUrls = useRef<string[]>([]);

  const options: ExportOptions = {
    mode,
    size,
    theme,
    showInfo,
    showTitle,
    showAuthor,
    showWatermark,
    scope,
    format,
    dpi,
  };

  const resolved = useMemo(() => resolveExportSize(options), [format, size, dpi]);
  const totalPages = useMemo(
    () => pageCountFor(dual, options),
    [dual, mode, size, format, dpi, showInfo, scope],
  );
  const plan = useMemo(() => {
    try {
      return planExport(dual, options);
    } catch {
      return null;
    }
  }, [dual, mode, size, format, dpi, showInfo, scope]);
  const perPage = measuresPerPage(mode, resolved.width, dual.grid.slots_per_measure, resolved.height);

  const remember = (name: string, blob: Blob) => {
    (window as unknown as Record<string, unknown>).__pocketscoreExport = { name, blob };
    setArtifact({ url: URL.createObjectURL(blob), name, label: name, size: blob.size });
  };

  const handlePreview = async () => {
    setBusy(true);
    setMessage(null);
    try {
      const pages = await renderPageThumbnails(dual, options, 8);
      thumbUrls.current.forEach((url) => URL.revokeObjectURL(url));
      thumbUrls.current = pages.map((page) => page.url);
      setThumbs(pages);
      setActivePage(1);
      setZoom(1);
      setMessage(
        pages.length < totalPages
          ? `已生成前 ${pages.length} 页缩略图（共 ${totalPages} 页）`
          : `已生成 ${pages.length} 页缩略图`,
      );
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "预览失败");
    } finally {
      setBusy(false);
    }
  };

  const handleExport = async () => {
    setBusy(true);
    setMessage(null);
    setArtifact(null);
    setProgress({ done: 0, total: 0 });
    try {
      const result = await renderScoreImages(dual, options, (done, total) =>
        setProgress({ done, total }),
      );
      if (result.total === 1) {
        const blob = result.pages[0].blob;
        const name = uniqueName((duplicate) =>
          exportFileName({
            title: dual.document.title,
            mode,
            ext: "png",
            total: 1,
            duplicate,
          }),
        );
        remember(name, blob);
        setMessage(
          `已生成 PNG（${result.pages[0].width}×${result.pages[0].height}，${(blob.size / 1024).toFixed(0)} KB）`,
        );
      } else {
        const entries = await Promise.all(
          result.pages.map(async (page) => ({
            name: exportFileName({
              title: dual.document.title,
              mode,
              ext: "png",
              page: page.page.index,
              total: result.total,
            }),
            data: await blobToBytes(page.blob),
          })),
        );
        const zip = createZip(entries);
        const name = uniqueName((duplicate) =>
          exportFileName({ title: dual.document.title, mode, ext: "zip", duplicate }),
        );
        const blob = new Blob([zip.buffer as ArrayBuffer], { type: "application/zip" });
        remember(name, blob);
        setMessage(`已生成 ${result.total} 张 PNG 并打包为 ZIP（${(blob.size / 1024).toFixed(0)} KB）`);
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "导出失败");
    } finally {
      setBusy(false);
    }
  };

  const handlePdf = async () => {
    setBusy(true);
    setMessage(null);
    setArtifact(null);
    setProgress({ done: 0, total: 0 });
    try {
      const result = await renderScorePdf(
        { ...dual },
        { ...options, scope },
        (done, total) => setProgress({ done, total }),
      );
      const blob = new Blob([result.bytes.buffer as ArrayBuffer], { type: "application/pdf" });
      const name = uniqueName((duplicate) =>
        exportFileName({ title: dual.document.title, mode, ext: "pdf", duplicate }),
      );
      remember(name, blob);
      setMessage(
        `已生成 ${result.pageCount} 页 PDF（位图 ${result.width}×${result.height} @ ${result.dpi} DPI，` +
          `${(blob.size / 1024).toFixed(0)} KB）— 这是位图 PDF，不是矢量 PDF`,
      );
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "PDF 导出失败");
    } finally {
      setBusy(false);
    }
  };

  const handleSave = async () => {
    if (!artifact) return;
    const blob = await fetch(artifact.url).then((response) => response.blob());
    const mime = artifact.name.endsWith(".pdf") ? "application/pdf" : artifact.name.endsWith(".zip") ? "application/zip" : "image/png";
    try {
      const outcome = await saveBlob(blob, artifact.name, mime);
      setMessage(
        outcome === "saved"
          ? `已保存：${artifact.name}`
          : outcome === "cancelled"
            ? "已取消保存"
            : `已发起浏览器下载：${artifact.name}。若没有出现保存提示，请点下方文件名链接用「链接另存为」`,
      );
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "保存失败");
    }
  };

  const activeThumb = thumbs.find((item) => item.index === activePage) ?? thumbs[0];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
      <div
        data-testid="export-dialog"
        className="max-h-[92vh] w-full max-w-4xl overflow-auto rounded-xl border border-studio-700 bg-studio-900 p-4"
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <FileImage size={16} className="text-accent" />
            <h3 className="text-sm font-semibold text-white">导出谱面（PNG / ZIP / PDF）</h3>
          </div>
          <button className="btn-ghost h-7 w-7 p-0" onClick={onClose} aria-label="关闭">
            <X size={14} />
          </button>
        </div>

        <div className="mt-3 grid gap-3 md:grid-cols-2">
          <div>
            <p className="text-[11px] font-medium text-studio-300">谱面类型</p>
            <div className="mt-1.5 grid grid-cols-2 gap-1.5">
              {MODES.map((item) => (
                <button
                  key={item.id}
                  data-testid={`export-mode-${item.id}`}
                  onClick={() => setMode(item.id)}
                  className={clsx(
                    "rounded-lg border px-2 py-1.5 text-left text-[11px] transition",
                    mode === item.id
                      ? "border-accent bg-accent/10 text-accent"
                      : "border-studio-700 text-studio-300 hover:border-studio-600",
                  )}
                >
                  <span className="block font-medium">{item.label}</span>
                  <span className="block text-[10px] text-studio-500">{item.hint}</span>
                </button>
              ))}
            </div>

            <p className="mt-3 text-[11px] font-medium text-studio-300">版式</p>
            <div className="mt-1.5 grid grid-cols-2 gap-1.5">
              {FORMATS.map((item) => (
                <button
                  key={item.id}
                  data-testid={`export-format-${item.id}`}
                  onClick={() => setFormat(item.id)}
                  className={clsx(
                    "rounded-lg border px-2 py-1.5 text-left text-[11px] transition",
                    format === item.id
                      ? "border-accent bg-accent/10 text-accent"
                      : "border-studio-700 text-studio-300 hover:border-studio-600",
                  )}
                >
                  <span className="block font-medium">{item.label}</span>
                  <span className="block text-[10px] text-studio-500">{item.hint}</span>
                </button>
              ))}
            </div>
          </div>

          <div className="space-y-3">
            <div>
              <p className="text-[11px] font-medium text-studio-300">图片尺寸</p>
              <select
                data-testid="export-size"
                className="input mt-1.5 h-8 text-[11px]"
                value={size}
                onChange={(event) => setSize(event.target.value as PageSizeId)}
                disabled={format !== "story" && format !== "long"}
              >
                {Object.entries(PAGE_SIZES).map(([id, preset]) => (
                  <option key={id} value={id}>
                    9:16 · {preset.label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <p className="text-[11px] font-medium text-studio-300">打印精度（A4 / PDF）</p>
              <select
                data-testid="export-dpi"
                className="input mt-1.5 h-8 text-[11px]"
                value={dpi}
                onChange={(event) => setDpi(Number(event.target.value) as Dpi)}
              >
                {DPIS.map((value) => (
                  <option key={value} value={value}>
                    {value} DPI{value === 600 ? "（内存占用高）" : ""}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <p className="text-[11px] font-medium text-studio-300">主题</p>
              <select
                data-testid="export-theme"
                className="input mt-1.5 h-8 text-[11px]"
                value={theme}
                onChange={(event) => setTheme(event.target.value as ThemeId)}
              >
                {Object.values(THEMES).map((preset) => (
                  <option key={preset.id} value={preset.id}>
                    {preset.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex flex-wrap gap-3 text-[11px] text-studio-300">
              <label className="flex items-center gap-1.5">
                <input
                  type="checkbox"
                  data-testid="export-show-info"
                  checked={showInfo}
                  onChange={(event) => setShowInfo(event.target.checked)}
                />
                显示歌曲信息
              </label>
              <label className="flex items-center gap-1.5">
                <input
                  type="checkbox"
                  data-testid="export-show-title"
                  checked={showTitle}
                  onChange={(event) => setShowTitle(event.target.checked)}
                />
                标题
              </label>
              <label className="flex items-center gap-1.5">
                <input
                  type="checkbox"
                  data-testid="export-show-author"
                  checked={showAuthor}
                  onChange={(event) => setShowAuthor(event.target.checked)}
                />
                作者
              </label>
              <label className="flex items-center gap-1.5">
                <input
                  type="checkbox"
                  data-testid="export-show-watermark"
                  checked={showWatermark}
                  onChange={(event) => setShowWatermark(event.target.checked)}
                />
                品牌水印
              </label>
            </div>
            <div>
              <p className="text-[11px] font-medium text-studio-300">导出范围</p>
              <select
                data-testid="export-scope"
                className="input mt-1.5 h-8 text-[11px]"
                value={scope}
                onChange={(event) => setScope(event.target.value as "all" | "current")}
              >
                <option value="all">全部页面（多页自动打包 ZIP / 多页 PDF）</option>
                <option value="current">仅第 1 页（单张 PNG / 单页 PDF）</option>
              </select>
            </div>
          </div>
        </div>

        <div
          data-testid="export-summary"
          data-pages={totalPages}
          data-width={resolved.width}
          data-height={resolved.height}
          className="mt-3 rounded-lg border border-studio-800 bg-studio-950/60 px-3 py-2 text-[10px] leading-relaxed text-studio-400"
        >
          <p>
            版式 <b className="text-studio-200">{resolved.label}</b> · 物理尺寸{" "}
            <b className="text-studio-200">{physicalSizeLabel(resolved)}</b> ·{" "}
            {formatMegapixels(resolved)}
          </p>
          <p className="mt-0.5">
            共 <b className="text-studio-200">{totalPages}</b> 页 · 每页{" "}
            <b className="text-studio-200">{perPage}</b> 小节（整小节分页，不截断）·{" "}
            {modeLabel(mode)} · 数据来自同一份 MusicDocument，共 {dual.grid.stats.notes} 个音符
          </p>
          <p className="mt-0.5 text-studio-500">
            A4 由毫米尺寸按 DPI 换算，不是把 9:16 拉伸；PDF 为位图嵌入，分辨率即上面的像素尺寸。
          </p>
        </div>

        {thumbs.length > 0 && (
          <div className="mt-3" data-testid="export-preview-panel">
            <div className="flex items-center justify-between">
              <p className="text-[11px] text-studio-400">
                预览 第 {activePage} / {thumbs.length} 页 · {resolved.width}×{resolved.height}
              </p>
              <div className="flex items-center gap-1">
                <button
                  data-testid="export-zoom-out"
                  className="btn-ghost h-6 w-6 p-0"
                  onClick={() => setZoom((value) => Math.max(0.5, Number((value - 0.25).toFixed(2))))}
                  aria-label="缩小"
                >
                  <Minus size={12} />
                </button>
                <span className="w-10 text-center text-[10px] text-studio-400">{Math.round(zoom * 100)}%</span>
                <button
                  data-testid="export-zoom-in"
                  className="btn-ghost h-6 w-6 p-0"
                  onClick={() => setZoom((value) => Math.min(2, Number((value + 0.25).toFixed(2))))}
                  aria-label="放大"
                >
                  <Plus size={12} />
                </button>
              </div>
            </div>
            <div className="mt-1 flex gap-2 overflow-x-auto pb-1">
              {thumbs.map((thumb) => (
                <button
                  key={thumb.index}
                  data-testid={`export-thumb-${thumb.index}`}
                  onClick={() => setActivePage(thumb.index)}
                  className={clsx(
                    "shrink-0 overflow-hidden rounded border",
                    thumb.index === activePage ? "border-accent" : "border-studio-700",
                  )}
                >
                  <img src={thumb.url} alt={`第 ${thumb.index} 页`} className="h-20 w-auto" />
                </button>
              ))}
            </div>
            {activeThumb && (
              <img
                src={activeThumb.url}
                alt={`第 ${activeThumb.index} 页预览`}
                data-testid="export-preview"
                style={{ width: `${Math.round(320 * zoom)}px` }}
                className="mt-2 max-h-[46vh] rounded border border-studio-700 object-contain"
              />
            )}
          </div>
        )}

        {busy && progress.total > 0 && (
          <p className="mt-2 text-[11px] text-studio-300">
            渲染中 {progress.done}/{progress.total} 页…
          </p>
        )}
        {message && (
          <p data-testid="export-message" className="mt-2 text-[11px] text-accent">
            {message}
          </p>
        )}

        {artifact && (
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <button data-testid="export-save" className="btn-primary h-8 text-[11px]" onClick={handleSave}>
              <Download size={13} /> 保存 {artifact.name}
            </button>
            <a
              data-testid="export-download"
              className="text-[11px] text-accent underline"
              href={artifact.url}
              download={artifact.name}
            >
              {artifact.name}（{(artifact.size / 1024).toFixed(0)} KB）
            </a>
          </div>
        )}

        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button className="btn-ghost h-8 text-[11px]" onClick={handlePreview} disabled={busy}>
            生成预览
          </button>
          <button
            data-testid="export-confirm"
            className="btn-primary h-8 text-[11px]"
            onClick={handleExport}
            disabled={busy || !plan}
          >
            {busy ? <Loader2 size={13} className="animate-spin" /> : <Download size={13} />}
            {busy ? "渲染中…" : totalPages > 1 ? `生成 ${totalPages} 页（ZIP）` : "生成 PNG"}
          </button>
          <button
            data-testid="export-pdf"
            className="btn-ghost h-8 text-[11px]"
            onClick={handlePdf}
            disabled={busy}
          >
            {busy ? <Loader2 size={13} className="animate-spin" /> : <FileText size={13} />}
            导出 PDF
          </button>
          <button className="btn-ghost ml-auto h-8 text-[11px]" onClick={onClose} disabled={busy}>
            取消
          </button>
        </div>
      </div>
    </div>
  );
}

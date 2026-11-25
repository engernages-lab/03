import { useMemo, useState } from "react";
import { Download, FileImage, Loader2, X } from "lucide-react";
import clsx from "clsx";
import {
  PAGE_SIZES,
  THEMES,
  fileNameFor,
  measuresPerPage,
  pageCountFor,
  zipNameFor,
  type ExportMode,
  type ExportOptions,
  type PageSizeId,
  type ThemeId,
} from "../../lib/scoreImage";
import { blobToBytes, renderScoreImages } from "../../lib/exportScore";
import { createZip } from "../../lib/zip";
import type { DualNotationResponse } from "../../lib/types";

const MODES: { id: ExportMode; label: string; hint: string }[] = [
  { id: "grid", label: "格子谱", hint: "口袋键盘格子视图" },
  { id: "jianpu", label: "数字谱", hint: "简谱数字 + 八度点" },
  { id: "keyboard", label: "键盘谱", hint: "仅键位行与节奏位置" },
  { id: "combined", label: "组合谱", hint: "格子谱 + 数字谱同页" },
  { id: "full", label: "完整谱面", hint: "自动分页导出全部" },
];

export function ExportScoreDialog({
  dual,
  onClose,
}: {
  dual: DualNotationResponse;
  onClose: () => void;
}) {
  const [mode, setMode] = useState<ExportMode>("grid");
  const [size, setSize] = useState<PageSizeId>("hd");
  const [theme, setTheme] = useState<ThemeId>("classic");
  const [showInfo, setShowInfo] = useState(true);
  const [showWatermark, setShowWatermark] = useState(true);
  const [scope, setScope] = useState<"all" | "current">("all");
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState({ done: 0, total: 0 });
  const [message, setMessage] = useState<string | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [artifact, setArtifact] = useState<{ url: string; name: string; label: string } | null>(null);

  const options: ExportOptions = { mode, size, theme, showInfo, showWatermark, scope };
  const totalPages = useMemo(
    () => pageCountFor(dual, options),
    [dual, mode, size, showInfo, showWatermark, scope],
  );
  const perPage = measuresPerPage(mode, PAGE_SIZES[size].width, dual.grid.slots_per_measure);

  const handlePreview = async () => {
    setBusy(true);
    setMessage(null);
    try {
      const result = await renderScoreImages(dual, options);
      setPreview(URL.createObjectURL(result.pages[0].blob));
      setMessage(`预览已生成：共 ${result.total} 页，第 1 页 ${result.pages[0].width}×${result.pages[0].height}`);
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
        const name = fileNameFor(dual.document.title, 1, 1);
        const blob = result.pages[0].blob;
        // Exposed for automated tests: the sandboxed CI browser cannot save a
        // download, so the E2E suite inspects the produced bytes instead.
        (window as unknown as Record<string, unknown>).__pocketscoreExport = { name, blob };
        setArtifact({ url: URL.createObjectURL(blob), name, label: "下载 PNG" });
        setMessage(`已生成 1 张 PNG（${result.pages[0].width}×${result.pages[0].height}），点下方按钮保存`);
      } else {
        const entries = await Promise.all(
          result.pages.map(async (page) => ({
            name: fileNameFor(dual.document.title, page.page.index, result.total),
            data: await blobToBytes(page.blob),
          })),
        );
        const zip = createZip(entries);
        const name = zipNameFor(dual.document.title);
        const blob = new Blob([zip.buffer as ArrayBuffer], { type: "application/zip" });
        (window as unknown as Record<string, unknown>).__pocketscoreExport = { name, blob };
        setArtifact({ url: URL.createObjectURL(blob), name, label: `下载 ZIP（${result.total} 张）` });
        setMessage(`已生成 ${result.total} 张 PNG 并打包，点下方按钮保存`);
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "导出失败");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
      <div
        data-testid="export-dialog"
        className="max-h-[92vh] w-full max-w-3xl overflow-auto rounded-xl border border-studio-700 bg-studio-900 p-4"
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <FileImage size={16} className="text-accent" />
            <h3 className="text-sm font-semibold text-white">导出谱面图片</h3>
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
          </div>

          <div className="space-y-3">
            <div>
              <p className="text-[11px] font-medium text-studio-300">图片尺寸</p>
              <select
                data-testid="export-size"
                className="input mt-1.5 h-8 text-[11px]"
                value={size}
                onChange={(event) => setSize(event.target.value as PageSizeId)}
              >
                {Object.entries(PAGE_SIZES).map(([id, preset]) => (
                  <option key={id} value={id}>
                    {preset.label}
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
                <option value="all">全部页面（多页自动打包 ZIP）</option>
                <option value="current">仅第 1 页（单张 PNG）</option>
              </select>
            </div>
          </div>
        </div>

        <p className="mt-3 rounded-lg border border-studio-800 bg-studio-950/60 px-3 py-2 text-[10px] leading-relaxed text-studio-400">
          将导出 <b>{totalPages}</b> 页 · 每页 {perPage} 小节（整小节分页，不截断）·{" "}
          {PAGE_SIZES[size].width}×{PAGE_SIZES[size].height}（9:16）· 数据来自同一份 MusicDocument，
          共 {dual.grid.stats.notes} 个音符。
        </p>

        {preview && (
          <div className="mt-3">
            <p className="text-[11px] text-studio-400">第 1 页预览</p>
            <img
              src={preview}
              alt="导出预览"
              data-testid="export-preview"
              className="mt-1 max-h-64 rounded border border-studio-700 object-contain"
            />
          </div>
        )}

        {busy && progress.total > 0 && (
          <p className="mt-2 text-[11px] text-studio-300">
            渲染中 {progress.done}/{progress.total} 页…
          </p>
        )}
        {message && <p className="mt-2 text-[11px] text-accent">{message}</p>}

        {artifact && (
          <a
            data-testid="export-download"
            className="btn-primary mt-2 h-8 text-[11px]"
            href={artifact.url}
            download={artifact.name}
          >
            <Download size={13} /> {artifact.label}
          </a>
        )}

        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button className="btn-ghost h-8 text-[11px]" onClick={handlePreview} disabled={busy}>
            生成预览
          </button>
          <button
            data-testid="export-confirm"
            className="btn-primary h-8 text-[11px]"
            onClick={handleExport}
            disabled={busy}
          >
            {busy ? <Loader2 size={13} className="animate-spin" /> : <Download size={13} />}
            {busy ? "渲染中…" : totalPages > 1 ? `生成 ${totalPages} 页（ZIP）` : "生成 PNG"}
          </button>
          <button className="btn-ghost ml-auto h-8 text-[11px]" onClick={onClose} disabled={busy}>
            取消
          </button>
        </div>
      </div>
    </div>
  );
}

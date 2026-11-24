import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
  Download,
  FileJson,
  FileMusic,
  Grid3x3,
  Keyboard,
  ListMusic,
  Minus,
  Plus,
  Redo2,
  Save,
  Sparkles,
  Trash2,
  Undo2,
} from "lucide-react";
import clsx from "clsx";
import { api, API_V1 } from "../lib/api";
import type {
  DualNotationResponse,
  EditOperation,
  KeyboardLayout,
  MusicDocument,
} from "../lib/types";
import { useDocumentStore } from "../store/document";
import { GridScore } from "../components/notation/GridScore";
import { JianpuScore } from "../components/notation/JianpuScore";
import { Badge } from "../components/ui/Badge";
import { EmptyState, Spinner } from "../components/ui/Feedback";
import { formatDate, formatDuration } from "../lib/format";

type NotationTab = "split" | "grid" | "jianpu";

export function ScoreEditorPage() {
  const { documentId } = useParams<{ documentId: string }>();

  const document = useDocumentStore((state) => state.document);
  const view = useDocumentStore((state) => state.view);
  const past = useDocumentStore((state) => state.past);
  const future = useDocumentStore((state) => state.future);
  const pending = useDocumentStore((state) => state.pending);
  const lastError = useDocumentStore((state) => state.lastError);
  const load = useDocumentStore((state) => state.load);
  const applyEditResult = useDocumentStore((state) => state.applyEditResult);
  const undoSnapshot = useDocumentStore((state) => state.undo);
  const redoSnapshot = useDocumentStore((state) => state.redo);
  const reset = useDocumentStore((state) => state.reset);
  const setPending = useDocumentStore((state) => state.setPending);
  const setError = useDocumentStore((state) => state.setError);

  const [tab, setTab] = useState<NotationTab>("split");
  const [zoom, setZoom] = useState(1);
  const [divisions, setDivisions] = useState(4);
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);
  const [layoutId, setLayoutId] = useState<string | null>(null);
  const [layouts, setLayouts] = useState<KeyboardLayout[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const refresh = useCallback(
    async (targetLayoutId?: string | null) => {
      const response = await api.get<DualNotationResponse>(`/notation/${documentId}/both`, {
        layout_id: targetLayoutId ?? undefined,
        divisions,
      });
      return response;
    },
    [documentId, divisions],
  );

  // Initial load
  useEffect(() => {
    let cancelled = false;
    reset();
    setLoading(true);
    setLoadError(null);
    (async () => {
      try {
        const [dual, layoutList] = await Promise.all([
          api.get<DualNotationResponse>(`/notation/${documentId}/both`, { divisions }),
          api.get<{ items: KeyboardLayout[] }>("/keyboard-layouts"),
        ]);
        if (cancelled) return;
        load(dual);
        setLayouts(layoutList.items);
        setLayoutId(dual.document.keyboard_layout.layout_id);
      } catch (error) {
        if (!cancelled) setLoadError(error instanceof Error ? error.message : "加载失败");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [documentId]);

  // Re-fetch when divisions change
  useEffect(() => {
    if (!document) return;
    (async () => {
      try {
        const dual = await refresh(layoutId);
        applyEditResult(dual);
      } catch {
        /* keep the current view */
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [divisions]);

  const applyEdits = useCallback(
    async (operations: EditOperation[]) => {
      if (!documentId) return;
      setPending(true);
      try {
        await api.post(`/documents/${documentId}/edits`, { operations });
        const dual = await refresh(layoutId);
        applyEditResult(dual);
      } catch (error) {
        setError(error instanceof Error ? error.message : "编辑失败");
      }
    },
    [documentId, layoutId, refresh, applyEditResult, setPending, setError],
  );

  const restore = useCallback(
    async (snapshot: MusicDocument | null) => {
      if (!snapshot || !documentId) return;
      setPending(true);
      try {
        await api.put(`/documents/${documentId}`, snapshot);
        const dual = await refresh(layoutId);
        applyEditResult({ ...dual, document: dual.document });
      } catch (error) {
        setError(error instanceof Error ? error.message : "撤销失败");
      }
    },
    [documentId, layoutId, refresh, applyEditResult, setPending, setError],
  );

  const handleUndo = useCallback(async () => {
    const snapshot = undoSnapshot();
    await restore(snapshot);
  }, [undoSnapshot, restore]);

  const handleRedo = useCallback(async () => {
    const snapshot = redoSnapshot();
    await restore(snapshot);
  }, [redoSnapshot, restore]);

  const changeLayout = useCallback(
    async (nextLayoutId: string) => {
      if (!documentId) return;
      setPending(true);
      try {
        const layout = await api.get<KeyboardLayout>(`/keyboard-layouts/${nextLayoutId}`);
        await api.post(`/documents/${documentId}/edits`, {
          operations: [{ op: "set_layout", layout }],
        });
        setLayoutId(nextLayoutId);
        const dual = await api.get<DualNotationResponse>(`/notation/${documentId}/both`, {
          layout_id: nextLayoutId,
          divisions,
        });
        applyEditResult(dual);
      } catch (error) {
        setError(error instanceof Error ? error.message : "切换键盘布局失败");
      }
    },
    [documentId, divisions, applyEditResult, setPending, setError],
  );

  const selectedEvent = useMemo(
    () => document?.events.find((event) => event.event_id === selectedEventId) ?? null,
    [document, selectedEventId],
  );

  if (loading) {
    return (
      <div className="grid place-items-center py-20">
        <Spinner label="正在加载谱面…" />
      </div>
    );
  }

  if (loadError || !document || !view) {
    return (
      <EmptyState
        title="谱面加载失败"
        description={loadError ?? "文档不存在或已被删除。"}
        action={
          <Link to="/scores" className="btn-ghost">
            返回谱面列表
          </Link>
        }
      />
    );
  }

  const totalMeasures = view.grid.measures.length;

  return (
    <div className="space-y-4">
      {/* header */}
      <div className="flex flex-wrap items-center gap-3">
        <Link to="/scores" className="btn-icon" aria-label="返回谱面列表">
          <ArrowLeft size={16} />
        </Link>
        <div className="min-w-0">
          <h2 className="truncate text-lg font-semibold text-white">{document.title}</h2>
          <p className="text-[11px] text-studio-500">
            {document.artist} · {document.time_signature.numerator}/{document.time_signature.denominator} ·{" "}
            {document.tempo} BPM · {formatDuration(document.duration)} · 更新于{" "}
            {formatDate(document.updated_at)}
          </p>
        </div>
        <div className="ml-auto flex items-center gap-1.5">
          <button className="btn-icon" onClick={handleUndo} disabled={past.length === 0 || pending} title="撤销">
            <Undo2 size={15} />
          </button>
          <button className="btn-icon" onClick={handleRedo} disabled={future.length === 0 || pending} title="重做">
            <Redo2 size={15} />
          </button>
          <span className="mx-1 h-5 w-px bg-studio-700" />
          <button
            className="btn-icon"
            onClick={() => setZoom((value) => Math.max(0.6, Number((value - 0.1).toFixed(2))))}
            title="缩小"
          >
            <Minus size={15} />
          </button>
          <span className="w-10 text-center font-mono text-[11px] text-studio-400">
            {Math.round(zoom * 100)}%
          </span>
          <button
            className="btn-icon"
            onClick={() => setZoom((value) => Math.min(2, Number((value + 0.1).toFixed(2))))}
            title="放大"
          >
            <Plus size={15} />
          </button>
        </div>
      </div>

      {/* toolbar */}
      <div className="panel space-y-3 p-3">
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex rounded-lg border border-studio-700 p-0.5">
            {(
              [
                { key: "split", label: "双谱对照", icon: Grid3x3 },
                { key: "grid", label: "格子谱", icon: Grid3x3 },
                { key: "jianpu", label: "数字谱", icon: ListMusic },
              ] as const
            ).map((item) => {
              const Icon = item.icon;
              return (
                <button
                  key={item.key}
                  onClick={() => setTab(item.key)}
                  className={clsx(
                    "flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs transition",
                    tab === item.key ? "bg-accent text-studio-950" : "text-studio-300 hover:text-white",
                  )}
                >
                  <Icon size={13} />
                  {item.label}
                </button>
              );
            })}
          </div>

          <label className="flex items-center gap-1.5 text-[11px] text-studio-400">
            键盘布局
            <select
              className="input h-8 w-44 py-0 text-xs"
              value={layoutId ?? ""}
              onChange={(event) => changeLayout(event.target.value)}
            >
              {layouts.map((layout) => (
                <option key={layout.layout_id} value={layout.layout_id}>
                  {layout.name}
                </option>
              ))}
            </select>
          </label>

          <label className="flex items-center gap-1.5 text-[11px] text-studio-400">
            网格
            <select
              className="input h-8 w-20 py-0 text-xs"
              value={divisions}
              onChange={(event) => setDivisions(Number(event.target.value))}
            >
              {[1, 2, 4, 8, 16].map((value) => (
                <option key={value} value={value}>
                  1/{value}
                </option>
              ))}
            </select>
          </label>

          <label className="flex items-center gap-1.5 text-[11px] text-studio-400">
            BPM
            <input
              type="number"
              min={20}
              max={400}
              className="input h-8 w-20 py-0 text-xs"
              value={document.tempo}
              onChange={(event) => {
                const tempo = Number(event.target.value);
                if (tempo >= 20 && tempo <= 400) applyEdits([{ op: "set_tempo", tempo }]);
              }}
            />
          </label>

          <label className="flex items-center gap-1.5 text-[11px] text-studio-400">
            拍号
            <select
              className="input h-8 w-24 py-0 text-xs"
              value={`${document.time_signature.numerator}/${document.time_signature.denominator}`}
              onChange={(event) => {
                const [numerator, denominator] = event.target.value.split("/").map(Number);
                applyEdits([{ op: "set_time_signature", numerator, denominator }]);
              }}
            >
              {["4/4", "3/4", "2/4", "6/8", "12/8", "5/4"].map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="flex flex-wrap items-center gap-2 border-t border-studio-800 pt-2.5">
          <button
            className="btn-ghost h-8 py-0 text-xs"
            onClick={() =>
              applyEdits([
                { op: "add_rest", start_time: selectedEvent?.start_time ?? 0, duration: 1 },
              ])
            }
          >
            插入休止符
          </button>
          <button
            className="btn-ghost h-8 py-0 text-xs"
            disabled={!selectedEvent}
            onClick={() =>
              selectedEvent && applyEdits([{ op: "update_note", event_id: selectedEvent.event_id, patch: { duration: Math.min(8, selectedEvent.duration * 2) } }])
            }
          >
            时值 ×2
          </button>
          <button
            className="btn-ghost h-8 py-0 text-xs"
            disabled={!selectedEvent}
            onClick={() =>
              selectedEvent && applyEdits([{ op: "update_note", event_id: selectedEvent.event_id, patch: { duration: Math.max(0.25, selectedEvent.duration / 2) } }])
            }
          >
            时值 ÷2
          </button>
          <button
            className="btn-ghost h-8 py-0 text-xs"
            disabled={!selectedEvent || selectedEvent.pitch === null}
            onClick={() =>
              selectedEvent && applyEdits([{ op: "update_note", event_id: selectedEvent.event_id, patch: { pitch: Math.min(127, (selectedEvent.pitch ?? 0) + 1) } }])
            }
          >
            ♯ 升半音
          </button>
          <button
            className="btn-ghost h-8 py-0 text-xs"
            disabled={!selectedEvent || selectedEvent.pitch === null}
            onClick={() =>
              selectedEvent && applyEdits([{ op: "update_note", event_id: selectedEvent.event_id, patch: { pitch: Math.max(0, (selectedEvent.pitch ?? 0) - 1) } }])
            }
          >
            ♭ 降半音
          </button>
          <button
            className="btn-ghost h-8 gap-1 py-0 text-xs"
            onClick={() => applyEdits([{ op: "quantize", divisions: 4 }])}
            title="把所有音符吸附到十六分网格"
          >
            <Sparkles size={12} /> 量化
          </button>
          <button
            className="btn-danger h-8 py-0 text-xs"
            disabled={!selectedEvent}
            onClick={() => selectedEvent && applyEdits([{ op: "delete_note", event_id: selectedEvent.event_id }])}
          >
            <Trash2 size={12} /> 删除音符
          </button>

          <div className="ml-auto flex items-center gap-1.5">
            <a className="btn-icon h-8 w-8" href={`${API_V1}/documents/${document.document_id}/export`} title="导出 JSON">
              <FileJson size={14} />
            </a>
            <a className="btn-icon h-8 w-8" href={`${API_V1}/notation/${document.document_id}/grid.svg`} title="导出格子谱 SVG">
              <Grid3x3 size={14} />
            </a>
            <a className="btn-icon h-8 w-8" href={`${API_V1}/notation/${document.document_id}/jianpu.txt`} title="导出数字谱文本">
              <Download size={14} />
            </a>
            <a className="btn-icon h-8 w-8" href={`${API_V1}/midi/${document.document_id}/export`} title="导出 MIDI">
              <FileMusic size={14} />
            </a>
            <Link to="/keyboard" className="btn-icon h-8 w-8" title="编辑键盘布局">
              <Keyboard size={14} />
            </Link>
          </div>
        </div>

        {(lastError || pending) && (
          <div className="flex items-center gap-2 text-[11px]">
            {pending ? (
              <span className="text-studio-400">正在保存…</span>
            ) : (
              <span className="text-key-rose">编辑失败：{lastError}</span>
            )}
          </div>
        )}
      </div>

      {/* stats strip */}
      <div className="flex flex-wrap items-center gap-2 text-[11px] text-studio-400">
        <Badge tone="success">音符 {view.grid.stats.notes}</Badge>
        <Badge tone="neutral">休止 {view.grid.stats.rests}</Badge>
        <Badge tone="violet">和弦 {view.grid.stats.chords}</Badge>
        <Badge tone="info">小节 {totalMeasures}</Badge>
        <Badge tone="warning">变音 {view.jianpu.stats.accidentals}</Badge>
        {view.grid.stats.unmapped > 0 && (
          <Badge tone="danger">超出键盘 {view.grid.stats.unmapped}</Badge>
        )}
        <span className="ml-auto flex items-center gap-1">
          <Save size={11} /> 所有编辑都写入同一份 MusicDocument，两种谱面同步更新
        </span>
      </div>

      {/* notation surface */}
      <div className={clsx("grid gap-4", tab === "split" ? "xl:grid-cols-2" : "grid-cols-1")}>
        {tab !== "jianpu" && (
          <section className="space-y-2">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-studio-400">格子谱</h3>
              <div className="flex items-center gap-1">
                <button className="btn-icon h-7 w-7" onClick={() => setSelectedEventId(null)} title="取消选择">
                  <ChevronLeft size={13} />
                </button>
                <span className="font-mono text-[10px] text-studio-500">
                  {document.events.length} events
                </span>
                <button className="btn-icon h-7 w-7" title="选择下一个">
                  <ChevronRight size={13} />
                </button>
              </div>
            </div>
            <GridScore
              view={view.grid}
              selectedEventId={selectedEventId}
              zoom={zoom}
              showKeyNames={document.notation_settings.grid.show_key_names}
              onSelect={setSelectedEventId}
              onAddNote={(pitch, startTime, duration) =>
                applyEdits([{ op: "add_note", pitch, start_time: startTime, duration }])
              }
            />
            {view.grid.unmapped.length > 0 && (
              <div className="rounded-lg border border-key-amber/25 bg-key-amber/5 p-3 text-[11px] text-key-amber">
                <p className="mb-1 font-medium">以下音符不在当前键盘布局范围内：</p>
                <ul className="flex flex-wrap gap-2">
                  {view.grid.unmapped.slice(0, 12).map((note) => (
                    <li key={note.event_id} className="rounded bg-studio-900 px-2 py-0.5 font-mono">
                      {note.pitch_name} @ {note.start_time}拍
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </section>
        )}

        {tab !== "grid" && (
          <section className="space-y-2">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-studio-400">数字谱</h3>
              <span className="font-mono text-[10px] text-studio-500">
                1={view.jianpu.tonic} · {view.jianpu.mode === "minor" ? "小调" : "大调"}
              </span>
            </div>
            <JianpuScore
              view={view.jianpu}
              selectedEventId={selectedEventId}
              onSelect={setSelectedEventId}
              zoom={zoom}
              onUpdatePitch={(eventId, semitones) => {
                const event = document.events.find((item) => item.event_id === eventId);
                if (!event || event.pitch === null) return;
                const pitch = event.pitch + semitones;
                if (pitch < 0 || pitch > 127) return;
                applyEdits([{ op: "update_note", event_id: eventId, patch: { pitch } }]);
              }}
            />
          </section>
        )}
      </div>

      {selectedEvent && (
        <div className="panel flex flex-wrap items-center gap-3 px-4 py-2.5 text-[11px] text-studio-400">
          <span className="font-medium text-studio-200">已选音符</span>
          <span className="font-mono">pitch {selectedEvent.pitch ?? "rest"}</span>
          <span className="font-mono">起始 {selectedEvent.start_time} 拍</span>
          <span className="font-mono">时值 {selectedEvent.duration} 拍</span>
          <span className="font-mono">第 {selectedEvent.measure} 小节 第 {selectedEvent.beat} 拍</span>
          <span className="font-mono">
            键位 {selectedEvent.mapped_key ?? "—"}（{view.jianpu.key_labels[String(selectedEvent.pitch)] ?? "无"}）
          </span>
          <button className="ml-auto text-studio-500 hover:text-white" onClick={() => setSelectedEventId(null)}>
            取消选择
          </button>
        </div>
      )}
    </div>
  );
}

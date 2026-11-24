import { useEffect, useMemo, useState } from "react";
import { Check, Copy, Download, Plus, RotateCcw, Save, Trash2, Upload } from "lucide-react";
import clsx from "clsx";
import { api } from "../lib/api";
import type { KeyboardLayout, KeyDefinition } from "../lib/types";
import {
  useCreateLayout,
  useDeleteLayout,
  useDuplicateLayout,
  useLayouts,
  useSaveLayout,
} from "../lib/resources";
import { Badge } from "../components/ui/Badge";
import { EmptyState, Spinner } from "../components/ui/Feedback";

const COLORS = [
  "#3ddc97", "#22d3ee", "#8b5cf6", "#f5a524", "#fb7185",
  "#38bdf8", "#a3e635", "#f472b6", "#facc15", "#2dd4bf",
];

const NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
function pitchName(pitch: number): string {
  return `${NOTE_NAMES[((pitch % 12) + 12) % 12]}${Math.floor(pitch / 12) - 1}`;
}

export function KeyboardPage() {
  const layouts = useLayouts();
  const saveLayout = useSaveLayout();
  const createLayout = useCreateLayout();
  const deleteLayout = useDeleteLayout();
  const duplicateLayout = useDuplicateLayout();

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [draft, setDraft] = useState<KeyboardLayout | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const selected = useMemo(
    () => layouts.data?.items.find((item) => item.layout_id === selectedId) ?? null,
    [layouts.data, selectedId],
  );

  useEffect(() => {
    if (!selectedId && layouts.data?.items.length) {
      setSelectedId(layouts.data.items[0].layout_id);
    }
  }, [layouts.data, selectedId]);

  useEffect(() => {
    if (selected) setDraft(structuredClone(selected));
  }, [selected]);

  const readOnly = Boolean(draft?.is_builtin);

  const updateKey = (index: number, patch: Partial<KeyDefinition>) => {
    setDraft((current) => {
      if (!current) return current;
      const keys = current.keys.map((key, position) =>
        position === index ? { ...key, ...patch } : key,
      );
      return { ...current, keys };
    });
  };

  const addKey = () => {
    setDraft((current) => {
      if (!current || current.keys.length >= 36) return current;
      const index = current.keys.length;
      const lastPitch = current.keys[current.keys.length - 1]?.midi_pitch ?? current.root_note + 11;
      const key: KeyDefinition = {
        key_id: `k${index}`,
        label: pitchName(Math.min(127, lastPitch + 2)),
        index,
        row: 0,
        col: index,
        midi_pitch: Math.min(127, lastPitch + 2),
        semitone_offset: null,
        color: COLORS[index % COLORS.length],
        octave: null,
      };
      return { ...current, keys: [...current.keys, key], key_count: current.keys.length + 1 };
    });
  };

  const removeKey = (index: number) => {
    setDraft((current) => {
      if (!current || current.keys.length <= 1) return current;
      const keys = current.keys
        .filter((_, position) => position !== index)
        .map((key, position) => ({ ...key, index: position }));
      return { ...current, keys, key_count: keys.length };
    });
  };

  const handleSave = async () => {
    if (!draft) return;
    setMessage(null);
    try {
      if (readOnly) {
        const clone = {
          ...draft,
          layout_id: `layout_${Math.random().toString(16).slice(2, 14)}`,
          name: `${draft.name} 副本`,
          is_builtin: false,
        };
        const created = await createLayout.mutateAsync(clone);
        setSelectedId(created.layout_id);
        setMessage("已基于内置布局创建可编辑副本");
      } else {
        await saveLayout.mutateAsync({ ...draft, key_count: draft.keys.length });
        setMessage("布局已保存");
      }
      await layouts.refetch();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "保存失败");
    }
  };

  const handleExport = async () => {
    if (!draft) return;
    const payload = await api.get<Record<string, unknown>>(`/keyboard-layouts/${draft.layout_id}/export`);
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${draft.name}.layout.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  const handleImport = async (file: File) => {
    try {
      const text = await file.text();
      const created = await api.post<KeyboardLayout>("/keyboard-layouts/import", JSON.parse(text));
      await layouts.refetch();
      setSelectedId(created.layout_id);
      setMessage(`已导入布局：${created.name}`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "导入失败");
    }
  };

  return (
    <div className="grid gap-4 lg:grid-cols-[240px_1fr]">
      {/* layout list */}
      <aside className="panel h-fit">
        <div className="panel-header">
          <h3 className="text-sm font-semibold text-white">布局列表</h3>
          <button
            className="btn-icon h-7 w-7"
            title="恢复默认布局"
            onClick={async () => {
              const layout = await api.post<KeyboardLayout>("/keyboard-layouts/restore-default");
              setSelectedId(layout.layout_id);
              setMessage("已选中内置默认布局");
            }}
          >
            <RotateCcw size={13} />
          </button>
        </div>
        <div className="max-h-[60vh] overflow-y-auto p-2">
          {layouts.isLoading && <Spinner label="加载中" />}
          {layouts.data?.items.map((layout) => (
            <button
              key={layout.layout_id}
              onClick={() => setSelectedId(layout.layout_id)}
              className={clsx(
                "mb-1 flex w-full items-center justify-between gap-2 rounded-lg px-2.5 py-2 text-left text-xs transition",
                selectedId === layout.layout_id
                  ? "bg-accent/10 text-accent"
                  : "text-studio-300 hover:bg-studio-800/60",
              )}
            >
              <span className="min-w-0">
                <span className="block truncate">{layout.name}</span>
                <span className="block font-mono text-[10px] text-studio-600">
                  {layout.key_count} 键 · {layout.octave_span} 八度
                </span>
              </span>
              {layout.is_builtin && <Badge tone="neutral">内置</Badge>}
            </button>
          ))}
        </div>
        <div className="border-t border-studio-800 p-2">
          <label className="btn-ghost w-full cursor-pointer justify-center text-xs">
            <Upload size={13} /> 导入布局
            <input
              type="file"
              accept="application/json"
              className="hidden"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) void handleImport(file);
                event.target.value = "";
              }}
            />
          </label>
        </div>
      </aside>

      {/* editor */}
      <section className="space-y-4">
        {!draft ? (
          <EmptyState title="选择或创建一个布局" description="布局决定音高如何映射到键位，以及格子谱的行顺序。" />
        ) : (
          <>
            <div className="panel p-4">
              <div className="flex flex-wrap items-end gap-3">
                <label className="flex-1 min-w-[180px]">
                  <span className="label">布局名称</span>
                  <input
                    className="input"
                    value={draft.name}
                    disabled={readOnly}
                    onChange={(event) => setDraft({ ...draft, name: event.target.value })}
                  />
                </label>
                <label className="w-28">
                  <span className="label">根音 (MIDI)</span>
                  <input
                    type="number"
                    min={0}
                    max={127}
                    className="input"
                    value={draft.root_note}
                    disabled={readOnly}
                    onChange={(event) => setDraft({ ...draft, root_note: Number(event.target.value) })}
                  />
                </label>
                <label className="w-28">
                  <span className="label">八度跨度</span>
                  <input
                    type="number"
                    min={1}
                    max={4}
                    className="input"
                    value={draft.octave_span}
                    disabled={readOnly}
                    onChange={(event) => setDraft({ ...draft, octave_span: Number(event.target.value) })}
                  />
                </label>
                <Badge tone={readOnly ? "warning" : "success"}>
                  {readOnly ? "内置布局（只读）" : "可编辑"}
                </Badge>
              </div>
              <label className="mt-3 block">
                <span className="label">描述</span>
                <input
                  className="input"
                  value={draft.description}
                  disabled={readOnly}
                  onChange={(event) => setDraft({ ...draft, description: event.target.value })}
                />
              </label>
            </div>

            {/* keyboard preview */}
            <div className="panel p-4">
              <div className="mb-2 flex items-center justify-between">
                <h3 className="text-sm font-semibold text-white">键盘预览</h3>
                <span className="font-mono text-[10px] text-studio-500">
                  {draft.keys.length} 键 · 根音 {pitchName(draft.root_note)}
                </span>
              </div>
              <div className="flex gap-1.5 overflow-x-auto pb-2">
                {draft.keys.map((key) => {
                  const pitch = key.midi_pitch ?? draft.root_note + (key.semitone_offset ?? 0);
                  return (
                    <div
                      key={key.key_id}
                      className="flex min-w-[54px] flex-col items-center gap-1 rounded-lg border border-studio-700 bg-studio-800/60 px-2 py-2"
                      style={{ borderTopColor: key.color, borderTopWidth: 3 }}
                    >
                      <span className="text-[11px] font-semibold" style={{ color: key.color }}>
                        {key.label}
                      </span>
                      <span className="font-mono text-[10px] text-studio-500">{pitchName(pitch)}</span>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* key table */}
            <div className="panel">
              <div className="panel-header">
                <h3 className="text-sm font-semibold text-white">键位定义</h3>
                <div className="flex items-center gap-1.5">
                  <button className="btn-ghost h-8 py-0 text-xs" onClick={addKey} disabled={readOnly}>
                    <Plus size={13} /> 添加键
                  </button>
                  <button className="btn-ghost h-8 py-0 text-xs" onClick={handleExport}>
                    <Download size={13} /> 导出
                  </button>
                  <button
                    className="btn-primary h-8 py-0 text-xs"
                    onClick={handleSave}
                    disabled={saveLayout.isPending || createLayout.isPending}
                  >
                    <Save size={13} /> {readOnly ? "复制为可编辑" : "保存"}
                  </button>
                  {!readOnly && (
                    <button
                      className="btn-icon h-8 w-8 text-key-rose/80 hover:text-key-rose"
                      title="删除布局"
                      onClick={async () => {
                        if (window.confirm(`删除布局《${draft.name}》？`)) {
                          await deleteLayout.mutateAsync(draft.layout_id);
                          setDraft(null);
                          setSelectedId(null);
                        }
                      }}
                    >
                      <Trash2 size={13} />
                    </button>
                  )}
                  <button
                    className="btn-icon h-8 w-8"
                    title="复制布局"
                    onClick={async () => {
                      const clone = await duplicateLayout.mutateAsync({ layoutId: draft.layout_id });
                      await layouts.refetch();
                      setSelectedId(clone.layout_id);
                    }}
                  >
                    <Copy size={13} />
                  </button>
                </div>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-studio-800 text-studio-400">
                      <th className="table-head w-10">#</th>
                      <th className="table-head">键位名称</th>
                      <th className="table-head w-24">MIDI 音高</th>
                      <th className="table-head w-24">相对半音</th>
                      <th className="table-head w-20">颜色</th>
                      <th className="table-head w-16">操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {draft.keys.map((key, index) => (
                      <tr key={key.key_id} className="border-b border-studio-800/50">
                        <td className="table-cell text-studio-500">{index}</td>
                        <td className="table-cell">
                          <input
                            type="text"
                            className="input h-7 py-0"
                            value={key.label}
                            disabled={readOnly}
                            onChange={(event) => updateKey(index, { label: event.target.value })}
                          />
                        </td>
                        <td className="table-cell">
                          <input
                            type="number"
                            min={0}
                            max={127}
                            className="input h-7 py-0"
                            value={key.midi_pitch ?? ""}
                            disabled={readOnly}
                            placeholder="—"
                            onChange={(event) =>
                              updateKey(index, {
                                midi_pitch: event.target.value === "" ? null : Number(event.target.value),
                                semitone_offset: event.target.value === "" ? key.semitone_offset ?? 0 : null,
                              })
                            }
                          />
                        </td>
                        <td className="table-cell">
                          <input
                            type="number"
                            className="input h-7 py-0"
                            value={key.semitone_offset ?? ""}
                            disabled={readOnly || key.midi_pitch !== null}
                            placeholder="—"
                            onChange={(event) =>
                              updateKey(index, { semitone_offset: Number(event.target.value) || 0 })
                            }
                          />
                        </td>
                        <td className="table-cell">
                          <input
                            type="color"
                            className="h-7 w-full cursor-pointer rounded border border-studio-700 bg-transparent"
                            value={key.color}
                            disabled={readOnly}
                            onChange={(event) => updateKey(index, { color: event.target.value })}
                          />
                        </td>
                        <td className="table-cell">
                          <button
                            className="btn-icon h-7 w-7 text-key-rose/70 hover:text-key-rose"
                            onClick={() => removeKey(index)}
                            disabled={readOnly || draft.keys.length <= 1}
                            title="删除此键"
                          >
                            <Trash2 size={12} />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {message && (
              <div className="flex items-center gap-2 rounded-lg border border-accent/25 bg-accent/10 px-4 py-2 text-xs text-accent">
                <Check size={13} /> {message}
              </div>
            )}
            <p className="text-[11px] leading-relaxed text-studio-500">
              修改布局只影响“音高 → 键位”的映射和格子谱的行顺序，绝不会改写音符的原始音高。
              保存后打开任意谱面即可看到键位标记同步更新。
            </p>
          </>
        )}
      </section>
    </div>
  );
}

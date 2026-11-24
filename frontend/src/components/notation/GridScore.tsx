import { useMemo } from "react";
import clsx from "clsx";
import type { GridCell, GridRow, GridViewModel } from "../../lib/types";

export interface GridScoreProps {
  view: GridViewModel;
  selectedEventId?: string | null;
  zoom: number;
  showKeyNames: boolean;
  onSelect: (eventId: string | null) => void;
  onAddNote: (pitch: number, startTime: number, duration: number) => void;
}

const ROW_HEIGHT = 30;

export function GridScore({
  view,
  selectedEventId,
  zoom,
  showKeyNames,
  onSelect,
  onAddNote,
}: GridScoreProps) {
  const cellWidth = Math.max(10, Math.round(16 * zoom));
  const labelWidth = showKeyNames ? Math.max(52, Math.round(64 * Math.min(1.4, zoom))) : 24;

  const rows: GridRow[] = useMemo(
    () => (view.rest_row ? [...view.rows, view.rest_row] : view.rows),
    [view.rows, view.rest_row],
  );

  const beatToStart = (cell: GridCell) => {
    const measure = view.measures[cell.measure - 1];
    const measureStart = measure ? measure.start_beat : 0;
    return measureStart + cell.slot / view.divisions;
  };

  const handleCellClick = (row: GridRow, cell: GridCell) => {
    if (cell.state === "note" || cell.state === "rest") {
      onSelect(cell.event_id ?? null);
      return;
    }
    if (cell.state === "continuation") {
      onSelect(cell.event_id ?? null);
      return;
    }
    if (row.key_id === "*rest*") {
      return; // rests are added from the toolbar
    }
    if (row.pitch === null) return;
    onAddNote(row.pitch, beatToStart(cell), 1);
  };

  const totalWidth = labelWidth + view.stats.slots * cellWidth + 8;

  return (
    <div className="overflow-auto rounded-xl border border-studio-800 bg-studio-950/70">
      <div style={{ minWidth: totalWidth }}>
        {/* measure ruler */}
        <div className="flex border-b border-studio-800 bg-studio-900/70">
          <div style={{ width: labelWidth }} className="shrink-0 px-2 py-1 text-[10px] text-studio-500">
            键位
          </div>
          <div className="relative flex-1" style={{ height: 22 }}>
            {view.measures.map((measure) => (
              <div
                key={measure.measure}
                className="absolute top-0 flex h-full items-center border-l border-studio-700 pl-1 font-mono text-[10px] text-studio-400"
                style={{ left: measure.start_slot * cellWidth, width: measure.slots * cellWidth }}
              >
                {measure.measure}
              </div>
            ))}
          </div>
        </div>

        {rows.map((row) => (
          <div key={row.key_id} className="flex items-stretch border-b border-studio-800/50 last:border-0">
            <div
              style={{ width: labelWidth, height: ROW_HEIGHT }}
              className="flex shrink-0 items-center gap-1.5 px-2"
            >
              <span
                className="h-2.5 w-2.5 shrink-0 rounded-sm"
                style={{ backgroundColor: row.color }}
                aria-hidden
              />
              <span className="truncate text-[11px] text-studio-300">{row.label}</span>
              {row.pitch_name && (
                <span className="ml-auto hidden font-mono text-[9px] text-studio-600 sm:block">
                  {row.pitch_name}
                </span>
              )}
            </div>
            <div className="flex">
              {row.cells.map((cell) => {
                const selected = Boolean(selectedEventId && cell.event_id === selectedEventId);
                const isRest = cell.state === "rest";
                const isNote = cell.state === "note";
                const isContinuation = cell.state === "continuation";
                const strength = (cell.slot % view.divisions === 0 ? 1 : 0.45) as number;
                return (
                  <button
                    key={`${row.key_id}-${cell.measure}-${cell.slot}`}
                    onClick={() => handleCellClick(row, cell)}
                    title={
                      cell.event_id
                        ? `${row.label} · 第 ${cell.measure} 小节`
                        : `点击在第 ${cell.measure} 小节写入 ${row.label}`
                    }
                    style={{ width: cellWidth, height: ROW_HEIGHT }}
                    className={clsx(
                      "relative border-r border-studio-800/60 transition-colors",
                      cell.slot % view.divisions === 0 ? "bg-studio-900/40" : "bg-studio-950/30",
                      !cell.event_id && "hover:bg-accent/10",
                    )}
                  >
                    {cell.slot === 0 && (
                      <span className="pointer-events-none absolute inset-y-0 left-0 w-px bg-studio-600" />
                    )}
                    {(isNote || isRest) && (
                      <span
                        className={clsx(
                          "absolute inset-y-1 left-0.5 right-0.5 rounded-sm border",
                          selected ? "ring-2 ring-white/80" : "",
                        )}
                        style={{
                          backgroundColor: isRest ? "#334155" : cell.color ?? row.color,
                          borderColor: selected ? "#ffffff" : "transparent",
                          opacity: 0.9,
                        }}
                      />
                    )}
                    {isContinuation && (
                      <span
                        className="absolute inset-y-2.5 left-0 right-0"
                        style={{
                          backgroundColor: isRest ? "#475569" : cell.color ?? row.color,
                          opacity: 0.35,
                        }}
                      />
                    )}
                    {(isNote || isRest) && cellWidth >= 18 && (
                      <span className="relative z-10 text-[9px] font-semibold text-studio-950">
                        {isRest ? "休" : ""}
                      </span>
                    )}
                    <span
                      className="pointer-events-none absolute bottom-0 left-0 right-0 bg-studio-700"
                      style={{ height: 1, opacity: strength * 0.5 }}
                    />
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

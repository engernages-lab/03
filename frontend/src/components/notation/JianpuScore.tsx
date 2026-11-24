import clsx from "clsx";
import type { JianpuMeasure, JianpuNote, JianpuViewModel } from "../../lib/types";

export interface JianpuScoreProps {
  view: JianpuViewModel;
  selectedEventId?: string | null;
  onSelect: (eventId: string | null) => void;
  onUpdatePitch?: (eventId: string, semitones: number) => void;
  zoom: number;
}

function OctaveDots({ count }: { count: number }) {
  if (count <= 0) return null;
  return (
    <span className="pointer-events-none absolute left-1/2 top-0 flex -translate-x-1/2 flex-col items-center">
      {Array.from({ length: Math.min(count, 2) }).map((_, index) => (
        <span key={index} className="mb-[1px] h-[3px] w-[3px] rounded-full bg-accent" />
      ))}
    </span>
  );
}

function OctaveDotsBelow({ count }: { count: number }) {
  if (count <= 0) return null;
  return (
    <span className="pointer-events-none absolute bottom-0 left-1/2 flex -translate-x-1/2 flex-col items-center">
      {Array.from({ length: Math.min(count, 2) }).map((_, index) => (
        <span key={index} className="mt-[1px] h-[3px] w-[3px] rounded-full bg-accent" />
      ))}
    </span>
  );
}

function DurationMarks({ note }: { note: JianpuNote }) {
  const underlines = note.duration_label === "_" ? 1 : note.duration_label === "=" ? 2 : 0;
  const dashes = note.duration_label === "-" ? 1 : note.duration_label === "—" ? 3 : 0;
  return (
    <span className="pointer-events-none absolute -bottom-1 left-0 right-0 flex flex-col items-center">
      {Array.from({ length: underlines }).map((_, index) => (
        <span key={`u${index}`} className="mb-[1px] h-[1px] w-3.5 bg-studio-300" />
      ))}
      {dashes > 0 && (
        <span className="font-mono text-[10px] leading-none text-studio-400">
          {"- ".repeat(dashes).trim()}
        </span>
      )}
    </span>
  );
}

function JianpuNoteCell({
  note,
  selected,
  onSelect,
  onUpdatePitch,
}: {
  note: JianpuNote;
  selected: boolean;
  onSelect: (eventId: string) => void;
  onUpdatePitch?: (eventId: string, semitones: number) => void;
}) {
  const width = Math.max(28, Math.max(1, note.width) * 11 + 12);
  return (
    <div className="group relative flex flex-col items-center" style={{ minWidth: width }}>
      <button
        onClick={() => onSelect(note.event_id)}
        className={clsx(
          "relative rounded-md px-1.5 pb-2 pt-2 font-mono text-lg leading-none transition-colors",
          selected ? "bg-accent/20 text-white ring-1 ring-accent" : "text-studio-100 hover:bg-studio-800/70",
          note.is_rest && "text-studio-400",
          note.approximate && "underline decoration-dotted decoration-key-amber",
        )}
        title={`${note.token}${note.key_label ? ` · ${note.key_label}` : ""}${note.tie ? " · 连音" : ""}`}
      >
        <OctaveDots count={note.octave} />
        <span>{note.token}</span>
        {note.dots > 0 && (
          <span className="ml-0.5 text-[10px] text-studio-400">{".".repeat(note.dots)}</span>
        )}
        <OctaveDotsBelow count={-note.octave} />
        <DurationMarks note={note} />
      </button>
      {note.key_label && (
        <span className="mt-0.5 h-3 font-mono text-[9px] text-studio-600">{note.key_label}</span>
      )}
      {onUpdatePitch && !note.is_rest && (
        <span className="absolute -right-1 top-0 hidden flex-col gap-0.5 group-hover:flex">
          <button
            className="text-[9px] text-studio-500 hover:text-accent"
            onClick={() => onUpdatePitch(note.event_id, 1)}
            title="升高半音"
          >
            +
          </button>
          <button
            className="text-[9px] text-studio-500 hover:text-accent"
            onClick={() => onUpdatePitch(note.event_id, -1)}
            title="降低半音"
          >
            −
          </button>
        </span>
      )}
    </div>
  );
}

/** A chord renders as one vertical stack, as in printed jianpu. */
function ChordStack({
  notes,
  selectedEventId,
  onSelect,
}: {
  notes: JianpuNote[];
  selectedEventId?: string | null;
  onSelect: (eventId: string | null) => void;
}) {
  return (
    <div className="flex flex-col items-center gap-0.5 rounded-md border border-studio-800/70 px-1 py-1">
      <span className="font-mono text-[8px] uppercase text-studio-600">和弦</span>
      {notes.map((note) => (
        <button
          key={note.event_id}
          onClick={() => onSelect(note.event_id)}
          className={clsx(
            "relative px-1 font-mono text-base leading-none",
            selectedEventId === note.event_id
              ? "rounded bg-accent/20 text-white ring-1 ring-accent"
              : "text-studio-100 hover:text-accent",
          )}
          title={note.key_label ? `${note.token} · ${note.key_label}` : note.token}
        >
          <OctaveDots count={note.octave} />
          {note.token}
          <OctaveDotsBelow count={-note.octave} />
        </button>
      ))}
    </div>
  );
}

function groupNotes(notes: JianpuNote[]): JianpuNote[][] {
  const groups: JianpuNote[][] = [];
  let index = 0;
  while (index < notes.length) {
    const note = notes[index];
    if (note.chord_id && note.chord_size > 1) {
      const chord: JianpuNote[] = [note];
      let cursor = index + 1;
      while (cursor < notes.length && notes[cursor].chord_id === note.chord_id) {
        chord.push(notes[cursor]);
        cursor += 1;
      }
      groups.push(chord);
      index = cursor;
    } else {
      groups.push([note]);
      index += 1;
    }
  }
  return groups;
}

function MeasureRow({
  measure,
  selectedEventId,
  onSelect,
  onUpdatePitch,
}: {
  measure: JianpuMeasure;
  selectedEventId?: string | null;
  onSelect: (eventId: string | null) => void;
  onUpdatePitch?: (eventId: string, semitones: number) => void;
}) {
  const groups = groupNotes(measure.notes);
  return (
    <div className="flex items-stretch border-r border-studio-700 last:border-r-0">
      <div className="flex min-w-[56px] flex-col justify-center px-2">
        <span className="font-mono text-[10px] text-studio-500">#{measure.measure}</span>
        <span className="font-mono text-[9px] text-studio-700">{measure.beats} 拍</span>
      </div>
      <div className="flex min-h-[64px] flex-1 flex-nowrap items-start gap-1 overflow-x-auto border-l border-studio-800/70 px-2 py-2">
        {groups.length === 0 && (
          <span className="py-2 text-xs text-studio-700">（空小节）</span>
        )}
        {groups.map((group) =>
          group.length > 1 ? (
            <ChordStack
              key={group.map((note) => note.event_id).join("-")}
              notes={group}
              selectedEventId={selectedEventId}
              onSelect={onSelect}
            />
          ) : (
            <JianpuNoteCell
              key={group[0].event_id}
              note={group[0]}
              selected={selectedEventId === group[0].event_id}
              onSelect={onSelect}
              onUpdatePitch={onUpdatePitch}
            />
          ),
        )}
      </div>
    </div>
  );
}

export function JianpuScore({
  view,
  selectedEventId,
  onSelect,
  onUpdatePitch,
  zoom,
}: JianpuScoreProps) {
  const systems = new Map<number, JianpuMeasure[]>();
  for (const measure of view.measures) {
    const list = systems.get(measure.system_index) ?? [];
    list.push(measure);
    systems.set(measure.system_index, list);
  }

  return (
    <div className="rounded-xl border border-studio-800 bg-studio-950/70">
      <div className="flex flex-wrap items-center gap-3 border-b border-studio-800 px-4 py-2.5 text-[11px] text-studio-400">
        <span className="font-mono text-studio-200">
          1 = {view.tonic} {view.mode === "minor" ? "小调" : "大调"}
        </span>
        <span>{view.time_signature}</span>
        <span>♩ = {view.tempo}</span>
        <span className="text-studio-600">
          键盘：{view.layout_name} · 每行 {view.max_notes_per_line} 音
        </span>
      </div>
      <div className="p-3" style={{ fontSize: `${Math.round(16 * zoom)}px` }}>
        {[...systems.entries()].map(([systemIndex, measures]) => (
          <div
            key={systemIndex}
            className="mb-2 flex overflow-hidden rounded-lg border border-studio-800 bg-studio-900/40"
          >
            {measures.map((measure) => (
              <MeasureRow
                key={measure.measure}
                measure={measure}
                selectedEventId={selectedEventId}
                onSelect={onSelect}
                onUpdatePitch={onUpdatePitch}
              />
            ))}
          </div>
        ))}
        {view.measures.length === 0 && (
          <p className="py-8 text-center text-sm text-studio-500">还没有音符</p>
        )}
      </div>
      {view.stats.unmapped > 0 && (
        <p className="border-t border-studio-800 px-4 py-2 text-[11px] text-key-amber">
          有 {view.stats.unmapped} 个音符超出当前键盘布局范围：数字谱照常显示，格子谱会单独列出。
        </p>
      )}
    </div>
  );
}

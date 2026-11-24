import { useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  Copy,
  FileMusic,
  FilePlus2,
  Music4,
  Play,
  Search,
  Trash2,
  Upload,
} from "lucide-react";
import { useDocuments, useCreateDocument, useDeleteDocument, useDuplicateDocument, useImportMidi } from "../lib/resources";
import { Badge } from "../components/ui/Badge";
import { EmptyState, Skeleton } from "../components/ui/Feedback";
import { formatDate, formatDuration } from "../lib/format";

export function ScoresPage() {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [creating, setCreating] = useState(false);
  const [title, setTitle] = useState("");
  const midiInput = useRef<HTMLInputElement | null>(null);

  const documents = useDocuments({ q: query || undefined });
  const createDocument = useCreateDocument();
  const deleteDocument = useDeleteDocument();
  const duplicateDocument = useDuplicateDocument();
  const importMidi = useImportMidi();

  const handleCreate = async () => {
    const created = await createDocument.mutateAsync({
      title: title.trim() || "未命名谱面",
      artist: "未知艺人",
    });
    setCreating(false);
    setTitle("");
    navigate(`/scores/${created.document_id}`);
  };

  const handleMidi = async (file: File) => {
    const imported = await importMidi.mutateAsync({ file, title: file.name.replace(/\.(mid|midi)$/i, "") });
    navigate(`/scores/${imported.document_id}`);
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-[200px]">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-studio-500" />
          <input
            className="input pl-9"
            placeholder="搜索谱面标题或艺人"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </div>
        <input
          ref={midiInput}
          type="file"
          accept=".mid,.midi,audio/midi"
          className="hidden"
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) void handleMidi(file);
            event.target.value = "";
          }}
        />
        <button className="btn-ghost" onClick={() => midiInput.current?.click()} disabled={importMidi.isPending}>
          <FileMusic size={15} />
          {importMidi.isPending ? "解析中…" : "导入 MIDI"}
        </button>
        <button className="btn-primary" onClick={() => setCreating((value) => !value)}>
          <FilePlus2 size={15} /> 新建谱面
        </button>
      </div>

      {importMidi.isError && (
        <div className="rounded-lg border border-key-rose/30 bg-key-rose/10 px-4 py-2 text-xs text-key-rose">
          MIDI 导入失败：{String((importMidi.error as Error)?.message ?? "未知错误")}
        </div>
      )}

      {creating && (
        <div className="panel flex flex-wrap items-center gap-2 p-3">
          <input
            autoFocus
            className="input flex-1"
            placeholder="谱面标题，例如《小星星》"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") void handleCreate();
            }}
          />
          <button className="btn-primary" onClick={handleCreate} disabled={createDocument.isPending}>
            创建并打开
          </button>
          <button className="btn-ghost" onClick={() => setCreating(false)}>
            取消
          </button>
        </div>
      )}

      <div className="panel divide-y divide-studio-800/60">
        {documents.isLoading && (
          <div className="space-y-2 p-4">
            {Array.from({ length: 4 }).map((_, index) => (
              <Skeleton key={index} className="h-14 w-full" />
            ))}
          </div>
        )}

        {documents.data?.items.length === 0 && (
          <EmptyState
            icon={<Music4 size={22} />}
            title="还没有谱面"
            description="新建一个空谱面开始制谱，或导入 .mid/.midi 文件自动生成两种谱面。"
          />
        )}

        {documents.data?.items.map((item) => (
          <div key={item.document_id} className="flex flex-wrap items-center gap-3 px-4 py-3 hover:bg-studio-800/30">
            <div className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-studio-800 text-accent">
              <Music4 size={18} />
            </div>
            <div className="min-w-0 flex-1">
              <Link to={`/scores/${item.document_id}`} className="truncate text-sm font-medium text-white hover:text-accent">
                {item.title}
              </Link>
              <p className="text-[11px] text-studio-500">
                {item.artist} · {item.time_signature} · {item.tempo} BPM · {formatDuration(item.duration)} ·{" "}
                {item.events} 事件 · {item.measures} 小节
              </p>
            </div>
            <div className="hidden items-center gap-2 sm:flex">
              <Badge tone="neutral">{item.source_kind}</Badge>
              <Badge tone="info">{item.layout_name}</Badge>
            </div>
            <span className="hidden w-32 text-right font-mono text-[10px] text-studio-600 md:block">
              {formatDate(item.updated_at)}
            </span>
            <div className="flex items-center gap-1">
              <Link to={`/scores/${item.document_id}`} className="btn-icon h-8 w-8" title="打开">
                <Play size={13} />
              </Link>
              <button
                className="btn-icon h-8 w-8"
                title="复制"
                onClick={() => duplicateDocument.mutate(item.document_id)}
              >
                <Copy size={13} />
              </button>
              <button
                className="btn-icon h-8 w-8 text-key-rose/80 hover:text-key-rose"
                title="删除"
                onClick={() => {
                  if (window.confirm(`确定删除《${item.title}》？此操作不可撤销。`)) {
                    deleteDocument.mutate(item.document_id);
                  }
                }}
              >
                <Trash2 size={13} />
              </button>
            </div>
          </div>
        ))}
      </div>

      <p className="flex items-center gap-1.5 text-[11px] text-studio-500">
        <Upload size={12} />
        谱面数据保存于后端 SQLite；格子谱与数字谱始终由同一份 MusicDocument 生成。
      </p>
    </div>
  );
}

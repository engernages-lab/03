import { FolderClock, Trash2 } from "lucide-react";
import { api } from "../lib/api";
import { useHistory } from "../lib/resources";
import { usePlayQueue } from "../lib/playback";
import { usePlayerStore } from "../store/player";
import { TrackRow } from "../components/music/TrackRow";
import { EmptyState, Skeleton } from "../components/ui/Feedback";
import { formatDuration, formatRelative } from "../lib/format";

export function MusicRecentPage() {
  const history = useHistory(100);
  const { playTrack } = usePlayQueue();
  const current = usePlayerStore((state) => state.queue[state.index] ?? null);
  const isPlaying = usePlayerStore((state) => state.isPlaying);

  const clear = async () => {
    if (!window.confirm("清空播放历史？")) return;
    await api.del("/library/history");
    await history.refetch();
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <div className="grid h-10 w-10 place-items-center rounded-xl bg-studio-800 text-key-cyan">
          <FolderClock size={18} />
        </div>
        <div className="flex-1">
          <h2 className="text-sm font-semibold text-white">最近播放</h2>
          <p className="text-[11px] text-studio-500">{history.data?.total ?? 0} 条记录</p>
        </div>
        <button className="btn-ghost h-8 py-0 text-xs" onClick={clear}>
          <Trash2 size={13} /> 清空
        </button>
      </div>

      <div className="panel">
        {history.isLoading && <Skeleton className="m-3 h-12" />}
        {history.data?.items.length === 0 && (
          <EmptyState
            icon={<FolderClock size={22} />}
            title="还没有播放记录"
            description="开始播放后这里会记录曲目与播放时间。"
          />
        )}
        {history.data?.items.map((entry, index) => (
          <div key={entry.history_id} className="relative">
            <TrackRow
              track={entry.track}
              index={index}
              isCurrent={current?.track_id === entry.track.track_id}
              isPlaying={isPlaying}
              onPlay={(item) => playTrack(item, history.data?.items.map((row) => row.track))}
            />
            <div className="pointer-events-none absolute bottom-1 left-12 flex gap-2 text-[10px] text-studio-600">
              <span>{formatRelative(entry.played_at)}</span>
              <span>· 播放至 {formatDuration(entry.position)}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

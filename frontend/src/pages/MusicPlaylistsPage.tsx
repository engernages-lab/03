import { useState } from "react";
import { ListMusic, Plus, Trash2 } from "lucide-react";
import clsx from "clsx";
import {
  useCreatePlaylist,
  useDeletePlaylist,
  usePlaylistTracks,
  usePlaylists,
  useRemoveFromPlaylist,
} from "../lib/resources";
import { usePlayQueue } from "../lib/playback";
import { usePlayerStore } from "../store/player";
import { TrackRow } from "../components/music/TrackRow";
import { EmptyState, Skeleton } from "../components/ui/Feedback";
import { formatDate } from "../lib/format";

export function MusicPlaylistsPage() {
  const playlists = usePlaylists();
  const createPlaylist = useCreatePlaylist();
  const deletePlaylist = useDeletePlaylist();
  const removeFromPlaylist = useRemoveFromPlaylist();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [name, setName] = useState("");

  const activeId = selectedId ?? playlists.data?.items[0]?.playlist_id ?? null;
  const tracks = usePlaylistTracks(activeId ?? undefined);
  const { playTrack } = usePlayQueue();
  const current = usePlayerStore((state) => state.queue[state.index] ?? null);
  const isPlaying = usePlayerStore((state) => state.isPlaying);

  return (
    <div className="grid gap-4 lg:grid-cols-[260px_1fr]">
      <aside className="panel h-fit">
        <div className="panel-header">
          <h3 className="text-sm font-semibold text-white">歌单</h3>
          <span className="font-mono text-[10px] text-studio-500">{playlists.data?.total ?? 0}</span>
        </div>
        <div className="max-h-[55vh] space-y-1 overflow-y-auto p-2">
          {playlists.data?.items.map((playlist) => (
            <button
              key={playlist.playlist_id}
              onClick={() => setSelectedId(playlist.playlist_id)}
              className={clsx(
                "flex w-full items-center justify-between gap-2 rounded-lg px-2.5 py-2 text-left text-xs",
                activeId === playlist.playlist_id
                  ? "bg-accent/10 text-accent"
                  : "text-studio-300 hover:bg-studio-800/60",
              )}
            >
              <span className="truncate">{playlist.name}</span>
              <span className="font-mono text-[10px] text-studio-600">{playlist.track_count}</span>
            </button>
          ))}
          {playlists.data?.items.length === 0 && (
            <p className="px-2 py-4 text-center text-[11px] text-studio-500">还没有歌单</p>
          )}
        </div>
        <div className="flex items-center gap-1.5 border-t border-studio-800 p-2">
          <input
            className="input h-8 py-0 text-xs"
            placeholder="新歌单名称"
            value={name}
            onChange={(event) => setName(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && name.trim()) {
                createPlaylist.mutate({ name: name.trim() });
                setName("");
              }
            }}
          />
          <button
            className="btn-icon h-8 w-8"
            disabled={!name.trim()}
            onClick={() => {
              createPlaylist.mutate({ name: name.trim() });
              setName("");
            }}
            aria-label="创建歌单"
          >
            <Plus size={14} />
          </button>
        </div>
      </aside>

      <section className="panel">
        {!activeId ? (
          <EmptyState
            icon={<ListMusic size={22} />}
            title="选择或创建一个歌单"
            description="歌单只保存曲目引用，不会复制音频。"
          />
        ) : (
          <>
            <div className="panel-header">
              <div>
                <h3 className="text-sm font-semibold text-white">
                  {playlists.data?.items.find((item) => item.playlist_id === activeId)?.name}
                </h3>
                <p className="text-[11px] text-studio-500">
                  {tracks.data?.total ?? 0} 首 · 创建于{" "}
                  {formatDate(playlists.data?.items.find((item) => item.playlist_id === activeId)?.created_at)}
                </p>
              </div>
              <div className="flex items-center gap-1.5">
                {tracks.data?.items.length ? (
                  <button className="btn-ghost h-8 py-0 text-xs" onClick={() => playTrack(tracks.data!.items[0], tracks.data!.items)}>
                    播放全部
                  </button>
                ) : null}
                <button
                  className="btn-icon h-8 w-8 text-key-rose/80 hover:text-key-rose"
                  title="删除歌单"
                  onClick={() => {
                    if (window.confirm("删除这个歌单？曲目本身不会被删除。")) {
                      deletePlaylist.mutate(activeId);
                      setSelectedId(null);
                    }
                  }}
                >
                  <Trash2 size={13} />
                </button>
              </div>
            </div>
            {tracks.isLoading && <Skeleton className="m-3 h-12" />}
            {tracks.data?.items.length === 0 && (
              <EmptyState title="歌单是空的" description="在音乐资料库中点击曲目右侧的“加入歌单”。" />
            )}
            {tracks.data?.items.map((track, index) => (
              <div key={track.track_id} className="group relative">
                <TrackRow
                  track={track}
                  index={index}
                  isCurrent={current?.track_id === track.track_id}
                  isPlaying={isPlaying}
                  onPlay={(item) => playTrack(item, tracks.data?.items)}
                />
                <button
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-[10px] text-studio-500 opacity-0 transition group-hover:opacity-100 hover:text-key-rose"
                  onClick={() => removeFromPlaylist.mutate({ playlistId: activeId, trackId: track.track_id })}
                >
                  移出歌单
                </button>
              </div>
            ))}
          </>
        )}
      </section>
    </div>
  );
}

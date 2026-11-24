import { useState } from "react";
import { Plus, X } from "lucide-react";
import { useAddToPlaylist, useCreatePlaylist, usePlaylists } from "../../lib/resources";
import type { UnifiedTrack } from "../../lib/types";

export function AddToPlaylistDialog({
  track,
  onClose,
}: {
  track: UnifiedTrack | null;
  onClose: () => void;
}) {
  const playlists = usePlaylists();
  const addToPlaylist = useAddToPlaylist();
  const createPlaylist = useCreatePlaylist();
  const [name, setName] = useState("");
  const [status, setStatus] = useState<string | null>(null);

  if (!track) return null;

  const add = async (playlistId: string) => {
    try {
      await addToPlaylist.mutateAsync({ playlistId, trackId: track.track_id });
      setStatus("已加入歌单");
      setTimeout(onClose, 600);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "加入失败");
    }
  };

  const createAndAdd = async () => {
    if (!name.trim()) return;
    const playlist = await createPlaylist.mutateAsync({ name: name.trim() });
    setName("");
    await add(playlist.playlist_id);
  };

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4 backdrop-blur-sm" onClick={onClose}>
      <div className="panel w-full max-w-md p-4" onClick={(event) => event.stopPropagation()}>
        <div className="mb-3 flex items-center justify-between">
          <div>
            <h3 className="text-sm font-semibold text-white">加入歌单</h3>
            <p className="text-[11px] text-studio-500">{track.title}</p>
          </div>
          <button className="btn-icon h-7 w-7" onClick={onClose} aria-label="关闭">
            <X size={14} />
          </button>
        </div>

        <div className="max-h-64 space-y-1 overflow-y-auto">
          {playlists.data?.items.length === 0 && (
            <p className="py-3 text-center text-xs text-studio-500">还没有歌单，先创建一个吧。</p>
          )}
          {playlists.data?.items.map((playlist) => (
            <button
              key={playlist.playlist_id}
              className="flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-xs text-studio-200 hover:bg-studio-800/70"
              onClick={() => add(playlist.playlist_id)}
            >
              <span className="truncate">{playlist.name}</span>
              <span className="font-mono text-[10px] text-studio-500">{playlist.track_count} 首</span>
            </button>
          ))}
        </div>

        <div className="mt-3 flex items-center gap-2 border-t border-studio-800 pt-3">
          <input
            className="input"
            placeholder="新建歌单名称"
            value={name}
            onChange={(event) => setName(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") void createAndAdd();
            }}
          />
          <button className="btn-primary" onClick={createAndAdd} disabled={!name.trim()}>
            <Plus size={14} /> 新建
          </button>
        </div>
        {status && <p className="mt-2 text-[11px] text-accent">{status}</p>}
      </div>
    </div>
  );
}

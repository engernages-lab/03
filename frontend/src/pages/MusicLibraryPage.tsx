import { useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Album, Disc3, FolderOpen, Music2, Search, Upload, User } from "lucide-react";
import clsx from "clsx";
import {
  useAlbums,
  useArtists,
  useFavorites,
  useImportTrack,
  useLibraryStats,
  useToggleFavorite,
  useTracks,
} from "../lib/resources";
import { usePlayQueue } from "../lib/playback";
import { usePlayerStore } from "../store/player";
import { TrackRow } from "../components/music/TrackRow";
import { AddToPlaylistDialog } from "../components/music/AddToPlaylistDialog";
import { CoverArt } from "../components/music/CoverArt";
import { Badge } from "../components/ui/Badge";
import { EmptyState, Skeleton } from "../components/ui/Feedback";
import { audioFilesFromInput, collectDroppedAudio, uploadSequentially } from "../lib/folderImport";
import { formatDuration } from "../lib/format";
import type { UnifiedTrack } from "../lib/types";

type Tab = "tracks" | "albums" | "artists";

export function MusicLibraryPage() {
  const [tab, setTab] = useState<Tab>("tracks");
  const [query, setQuery] = useState("");
  const [dragging, setDragging] = useState(false);
  const [dialogTrack, setDialogTrack] = useState<UnifiedTrack | null>(null);
  const [uploadMessage, setUploadMessage] = useState<string | null>(null);
  const [progress, setProgress] = useState<{ done: number; total: number; name: string } | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const folderRef = useRef<HTMLInputElement | null>(null);

  const tracks = useTracks({ q: query || undefined, limit: 200 });
  const albums = useAlbums();
  const artists = useArtists();
  const stats = useLibraryStats();
  const favorites = useFavorites();
  const importTrack = useImportTrack();
  const toggleFavorite = useToggleFavorite();
  const { playTrack, playTracks } = usePlayQueue();
  const current = usePlayerStore((state) => state.queue[state.index] ?? null);
  const isPlaying = usePlayerStore((state) => state.isPlaying);

  const favoriteIds = useMemo(
    () => new Set((favorites.data?.items ?? []).map((item) => item.track_id)),
    [favorites.data],
  );

  const uploadFiles = async (files: File[]) => {
    if (!files.length) {
      setUploadMessage("没有找到可导入的音频文件（支持 MP3 / WAV / FLAC / M4A / AAC / OGG / OPUS）。");
      return;
    }
    setUploadMessage(null);
    setProgress({ done: 0, total: files.length, name: files[0].name });
    const outcome = await uploadSequentially(
      files,
      (file) => {
        const form = new FormData();
        form.append("file", file);
        return importTrack.mutateAsync(form);
      },
      (done, total, current) => setProgress(done >= total ? null : { done, total, name: current }),
    );
    setProgress(null);
    const skipped = files.length - outcome.imported - outcome.failed.length;
    const parts = [`成功导入 ${outcome.imported} 个音频文件`];
    if (outcome.failed.length) {
      parts.push(`失败 ${outcome.failed.length} 个（${outcome.failed[0].name}: ${outcome.failed[0].reason}）`);
    }
    if (skipped > 0) parts.push(`跳过 ${skipped} 个非音频文件`);
    setUploadMessage(parts.join("；"));
  };

  return (
    <div className="space-y-4">
      {/* stats */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          { label: "曲目", value: stats.data?.tracks ?? 0, icon: Music2 },
          { label: "专辑", value: albums.data?.total ?? 0, icon: Album },
          { label: "歌手", value: artists.data?.total ?? 0, icon: User },
          { label: "总时长", value: formatDuration(stats.data?.total_duration ?? 0), icon: Disc3 },
        ].map((item) => {
          const Icon = item.icon;
          return (
            <div key={item.label} className="panel flex items-center gap-3 px-4 py-3">
              <div className="grid h-9 w-9 place-items-center rounded-lg bg-studio-800 text-accent">
                <Icon size={16} />
              </div>
              <div>
                <p className="stat-value text-lg">{item.value}</p>
                <p className="text-[10px] uppercase tracking-wider text-studio-500">{item.label}</p>
              </div>
            </div>
          );
        })}
      </div>

      {/* toolbar */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative min-w-[200px] flex-1">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-studio-500" />
          <input
            className="input pl-9"
            placeholder="搜索曲目 / 艺人 / 专辑"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </div>
        <div className="flex rounded-lg border border-studio-700 p-0.5">
          {(
            [
              { key: "tracks", label: "曲目" },
              { key: "albums", label: "专辑" },
              { key: "artists", label: "歌手" },
            ] as const
          ).map((item) => (
            <button
              key={item.key}
              onClick={() => setTab(item.key)}
              className={clsx(
                "rounded-md px-3 py-1.5 text-xs transition",
                tab === item.key ? "bg-accent text-studio-950" : "text-studio-300 hover:text-white",
              )}
            >
              {item.label}
            </button>
          ))}
        </div>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept=".mp3,.wav,.flac,.m4a,.aac,.ogg,.opus"
          className="hidden"
          onChange={(event) => {
            if (event.target.files) void uploadFiles(Array.from(event.target.files));
            event.target.value = "";
          }}
        />
        <input
          ref={folderRef}
          type="file"
          multiple
          className="hidden"
          // webkitdirectory lets the user grant access to a whole folder.
          {...({ webkitdirectory: "", directory: "" } as Record<string, string>)}
          onChange={(event) => {
            void uploadFiles(audioFilesFromInput(event.target.files));
            event.target.value = "";
          }}
        />
        <button className="btn-ghost" onClick={() => folderRef.current?.click()} disabled={importTrack.isPending}>
          <FolderOpen size={14} /> 导入文件夹
        </button>
        <button className="btn-primary" onClick={() => inputRef.current?.click()} disabled={importTrack.isPending}>
          <Upload size={14} /> {importTrack.isPending ? "上传中…" : "导入本地音乐"}
        </button>
      </div>

      {progress && (
        <div className="space-y-1.5 rounded-lg border border-studio-700 bg-studio-900 px-4 py-2.5">
          <div className="flex items-center justify-between text-xs text-studio-300">
            <span className="truncate">
              正在导入 {progress.done + 1}/{progress.total} · {progress.name}
            </span>
            <span className="font-mono text-[10px] text-studio-500">
              {Math.round((progress.done / Math.max(1, progress.total)) * 100)}%
            </span>
          </div>
          <div className="h-1 overflow-hidden rounded-full bg-studio-800">
            <div
              className="h-full rounded-full bg-accent transition-all"
              style={{ width: `${(progress.done / Math.max(1, progress.total)) * 100}%` }}
            />
          </div>
        </div>
      )}

      {uploadMessage && (
        <p className="rounded-lg border border-studio-700 bg-studio-900 px-4 py-2 text-xs text-studio-300">
          {uploadMessage}
        </p>
      )}

      {/* drop zone */}
      <div
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          void collectDroppedAudio(event.dataTransfer).then(uploadFiles);
        }}
        className={clsx(
          "rounded-xl border-2 border-dashed px-4 py-3 text-center text-xs transition",
          dragging ? "border-accent bg-accent/10 text-accent" : "border-studio-800 text-studio-500",
        )}
      >
        拖拽音频文件或整个文件夹到此处即可导入（MP3 / WAV / FLAC / M4A / AAC / OGG / OPUS，递归扫描子目录）。
        文件只在你主动导入时上传到本机后端，未经同意不会上传任何内容。
      </div>

      {/* content */}
      {tab === "tracks" && (
        <div className="panel">
          <div className="panel-header">
            <h3 className="text-sm font-semibold text-white">曲目</h3>
            <div className="flex items-center gap-2">
              <Badge tone="neutral">{tracks.data?.total ?? 0} 首</Badge>
              {tracks.data?.items.length ? (
                <button className="btn-ghost h-8 py-0 text-xs" onClick={() => playTracks(tracks.data!.items, 0)}>
                  播放全部
                </button>
              ) : null}
            </div>
          </div>
          {tracks.isLoading && (
            <div className="space-y-2 p-4">
              {Array.from({ length: 5 }).map((_, index) => (
                <Skeleton key={index} className="h-12 w-full" />
              ))}
            </div>
          )}
          {tracks.data?.items.length === 0 && (
            <EmptyState
              icon={<Music2 size={22} />}
              title="资料库是空的"
              description="导入本地音频文件，或先在“音乐来源”中连接你的 Navidrome 服务器。"
              action={
                <Link to="/music-sources" className="btn-ghost">
                  前往音乐来源
                </Link>
              }
            />
          )}
          {tracks.data?.items.map((track, index) => (
            <TrackRow
              key={track.track_id}
              track={{ ...track, is_favorite: favoriteIds.has(track.track_id) }}
              index={index}
              isCurrent={current?.track_id === track.track_id}
              isPlaying={isPlaying}
              onPlay={(item) => playTrack(item, tracks.data?.items)}
              onToggleFavorite={(item) =>
                toggleFavorite.mutate({ trackId: item.track_id, favorite: favoriteIds.has(item.track_id) })
              }
              onAddToPlaylist={setDialogTrack}
              onEligibility={() => undefined}
            />
          ))}
        </div>
      )}

      {tab === "albums" && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
          {albums.data?.items.map((album) => (
            <div key={`${album.artist}-${album.album}`} className="panel overflow-hidden p-3">
              <CoverArt src={album.artwork} title={album.album} size={999} rounded="rounded-lg" className="w-full" />
              <p className="mt-2 truncate text-sm font-medium text-white">{album.album}</p>
              <p className="truncate text-[11px] text-studio-500">{album.artist}</p>
              <p className="font-mono text-[10px] text-studio-600">
                {album.track_count} 首 · {formatDuration(album.duration)}
              </p>
            </div>
          ))}
          {albums.data?.items.length === 0 && (
            <div className="col-span-full">
              <EmptyState title="暂无专辑" description="导入音频后会自动按元数据聚合专辑。" />
            </div>
          )}
        </div>
      )}

      {tab === "artists" && (
        <div className="panel divide-y divide-studio-800/60">
          {artists.data?.items.map((artist) => (
            <div key={artist.artist} className="flex items-center gap-3 px-4 py-3">
              <div className="grid h-9 w-9 place-items-center rounded-full bg-studio-800 text-studio-300">
                <User size={15} />
              </div>
              <span className="flex-1 text-sm text-studio-100">{artist.artist}</span>
              <Badge tone="neutral">{artist.track_count} 首</Badge>
              <Badge tone="info">{artist.album_count} 张专辑</Badge>
            </div>
          ))}
          {artists.data?.items.length === 0 && <EmptyState title="暂无歌手" />}
        </div>
      )}

      <p className="text-[11px] text-studio-600">
        导入的音频由后端按 SHA-256 去重存储；同一文件重复导入不会产生副本。
        音频与封面落盘在 <code className="font-mono">backend/data/storage</code>，数据库仅保存索引。
      </p>

      <AddToPlaylistDialog track={dialogTrack} onClose={() => setDialogTrack(null)} />
    </div>
  );
}

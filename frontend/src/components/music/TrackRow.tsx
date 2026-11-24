import clsx from "clsx";
import { Heart, ListPlus, Play, Square } from "lucide-react";
import type { UnifiedTrack } from "../../lib/types";
import { formatDuration } from "../../lib/format";
import { CoverArt, SourceBadge } from "./CoverArt";

export function TrackRow({
  track,
  index,
  isCurrent,
  isPlaying,
  onPlay,
  onToggleFavorite,
  onAddToPlaylist,
  onEligibility,
}: {
  track: UnifiedTrack;
  index?: number;
  isCurrent?: boolean;
  isPlaying?: boolean;
  onPlay: (track: UnifiedTrack) => void;
  onToggleFavorite?: (track: UnifiedTrack) => void;
  onAddToPlaylist?: (track: UnifiedTrack) => void;
  onEligibility?: (track: UnifiedTrack) => void;
}) {
  return (
    <div
      className={clsx(
        "group flex items-center gap-3 border-b border-studio-800/60 px-3 py-2 transition-colors last:border-0",
        isCurrent ? "bg-accent/5" : "hover:bg-studio-800/40",
      )}
    >
      <div className="w-6 shrink-0 text-center font-mono text-[11px] text-studio-500">
        {index !== undefined ? index + 1 : ""}
      </div>
      <button
        onClick={() => onPlay(track)}
        className="relative grid h-11 w-11 shrink-0 place-items-center overflow-hidden rounded-lg"
        aria-label={`播放 ${track.title}`}
      >
        <CoverArt src={track.artwork} title={track.title} size={44} />
        <span
          className={clsx(
            "absolute inset-0 grid place-items-center bg-black/55 text-white opacity-0 transition-opacity",
            "group-hover:opacity-100",
            isCurrent && "opacity-100",
          )}
        >
          {isCurrent && isPlaying ? <Square size={14} /> : <Play size={15} />}
        </span>
      </button>

      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <button
            onClick={() => onPlay(track)}
            className={clsx(
              "truncate text-left text-sm font-medium transition-colors",
              isCurrent ? "text-accent" : "text-studio-100 hover:text-white",
            )}
          >
            {track.title}
          </button>
          {isCurrent && <span className="h-1.5 w-1.5 animate-pulse-slow rounded-full bg-accent" />}
        </div>
        <div className="flex items-center gap-2 text-[11px] text-studio-500">
          <span className="truncate">{track.artist || "未知艺人"}</span>
          {track.album && <span className="truncate">· {track.album}</span>}
          {track.availability !== "streamable" && (
            <span className="text-key-amber">仅元数据</span>
          )}
        </div>
      </div>

      <SourceBadge provider={track.source_provider} className="hidden sm:inline-flex" />
      <span className="hidden w-12 text-right font-mono text-[11px] text-studio-500 sm:block">
        {formatDuration(track.duration)}
      </span>

      <div className="flex items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100">
        {onEligibility && (
          <button
            className="btn-icon h-7 w-7"
            onClick={() => onEligibility(track)}
            title="检查 AI 扒谱资格"
            aria-label="检查扒谱资格"
          >
            <span className="text-[10px] font-bold">AI</span>
          </button>
        )}
        {onAddToPlaylist && (
          <button
            className="btn-icon h-7 w-7"
            onClick={() => onAddToPlaylist(track)}
            title="加入歌单"
            aria-label="加入歌单"
          >
            <ListPlus size={14} />
          </button>
        )}
        {onToggleFavorite && (
          <button
            className={clsx("btn-icon h-7 w-7", track.is_favorite && "text-key-rose")}
            onClick={() => onToggleFavorite(track)}
            title={track.is_favorite ? "取消收藏" : "收藏"}
            aria-label={track.is_favorite ? "取消收藏" : "收藏"}
          >
            <Heart size={14} fill={track.is_favorite ? "currentColor" : "none"} />
          </button>
        )}
      </div>
    </div>
  );
}

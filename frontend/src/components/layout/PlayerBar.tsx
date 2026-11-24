import { useEffect, useRef, useState } from "react";
import clsx from "clsx";
import {
  Pause,
  Play,
  Repeat,
  Repeat1,
  Shuffle,
  SkipBack,
  SkipForward,
  Volume2,
  VolumeX,
  AlertTriangle,
} from "lucide-react";
import { usePlayerStore } from "../../store/player";
import { useRecordHistory, useStreamInfo } from "../../lib/resources";
import { API_BASE } from "../../lib/api";
import { formatDuration } from "../../lib/format";
import { CoverArt, SourceBadge } from "../music/CoverArt";
import { Badge } from "../ui/Badge";

const PROVIDER_SDK_HINT: Record<string, string> = {
  apple_music: "Apple Music 需在 MusicKit 授权播放器中播放，本应用不代理音频流。",
  spotify: "Spotify 播放必须通过官方 SDK / 官方控制器，本应用不代理音频流。",
};

export function PlayerBar() {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);
  const recordHistory = useRecordHistory();

  const {
    queue,
    index,
    isPlaying,
    volume,
    muted,
    repeat,
    shuffle,
    currentTime,
    duration,
    error,
    toggle,
    next,
    previous,
    setVolume,
    toggleMute,
    toggleShuffle,
    cycleRepeat,
    setCurrentTime,
    setDuration,
    setError,
  } = usePlayerStore();

  const current = index >= 0 && index < queue.length ? queue[index] : null;
  const stream = useStreamInfo(current?.track_id);

  const playableUrl =
    stream.data?.mode === "direct" && stream.data.url
      ? stream.data.url.startsWith("http")
        ? stream.data.url
        : `${API_BASE}${stream.data.url}`
      : null;

  // Load a new source whenever the current track changes.
  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;
    if (!playableUrl) {
      audio.removeAttribute("src");
      audio.load();
      return;
    }
    if (audio.src !== playableUrl) {
      audio.src = playableUrl;
      audio.load();
    }
  }, [playableUrl]);

  // Reflect play/pause state.
  useEffect(() => {
    const audio = audioRef.current;
    if (!audio || !playableUrl) return;
    if (isPlaying) {
      audio.play().catch(() => setLocalError("浏览器阻止了自动播放，请再次点击播放。"));
    } else {
      audio.pause();
    }
  }, [isPlaying, playableUrl]);

  // Volume + mute.
  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.volume = muted ? 0 : volume;
  }, [volume, muted]);

  // Record history once per track start.
  useEffect(() => {
    if (current && isPlaying) {
      recordHistory.mutate({ track_id: current.track_id, position: 0 });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [current?.track_id]);

  if (!current) return null;

  const sdkHint = PROVIDER_SDK_HINT[current.source_provider];
  const banner = localError ?? error ?? (stream.data && stream.data.mode !== "direct" ? sdkHint : null);
  const progressMax = duration || current.duration || 0;

  return (
    <div className="border-t border-studio-800 bg-studio-900/95 backdrop-blur">
      {banner && (
        <div className="flex items-center gap-2 border-b border-key-amber/25 bg-key-amber/10 px-4 py-1.5 text-[11px] text-key-amber">
          <AlertTriangle size={12} />
          <span className="flex-1">{banner}</span>
          <button className="text-studio-300 hover:text-white" onClick={() => setLocalError(null)}>
            关闭
          </button>
        </div>
      )}
      <div className="flex items-center gap-3 px-3 py-2.5 sm:gap-4 sm:px-4">
        <audio
          ref={audioRef}
          preload="metadata"
          onTimeUpdate={(event) => setCurrentTime(event.currentTarget.currentTime)}
          onLoadedMetadata={(event) => setDuration(event.currentTarget.duration || 0)}
          onEnded={() => next()}
          onError={() => {
            if (playableUrl) setLocalError("音频加载失败，请检查文件或音源状态。");
            else setError(null);
          }}
        />

        <div className="flex min-w-0 flex-1 items-center gap-3 sm:flex-none sm:basis-64">
          <CoverArt src={current.artwork} title={current.title} size={44} />
          <div className="min-w-0">
            <div className="flex items-center gap-1.5">
              <p className="truncate text-sm font-medium text-white">{current.title}</p>
              <SourceBadge provider={current.source_provider} />
            </div>
            <p className="truncate text-[11px] text-studio-400">
              {current.artist || "未知艺人"}
              {current.album ? ` · ${current.album}` : ""}
            </p>
          </div>
        </div>

        <div className="flex flex-1 flex-col items-center gap-1">
          <div className="flex items-center gap-1.5">
            <button
              className={clsx("btn-icon h-8 w-8 border-0 bg-transparent", shuffle && "text-accent")}
              onClick={toggleShuffle}
              title="随机播放"
              aria-label="随机播放"
            >
              <Shuffle size={15} />
            </button>
            <button className="btn-icon h-8 w-8 border-0 bg-transparent" onClick={previous} aria-label="上一首">
              <SkipBack size={16} />
            </button>
            <button
              className="grid h-9 w-9 place-items-center rounded-full bg-accent text-studio-950 transition hover:bg-accent-soft disabled:opacity-50"
              onClick={toggle}
              disabled={!playableUrl}
              aria-label={isPlaying ? "暂停" : "播放"}
            >
              {isPlaying ? <Pause size={16} /> : <Play size={16} className="translate-x-[1px]" />}
            </button>
            <button className="btn-icon h-8 w-8 border-0 bg-transparent" onClick={next} aria-label="下一首">
              <SkipForward size={16} />
            </button>
            <button
              className={clsx("btn-icon h-8 w-8 border-0 bg-transparent", repeat !== "off" && "text-accent")}
              onClick={cycleRepeat}
              title={`循环：${repeat === "off" ? "关闭" : repeat === "all" ? "列表" : "单曲"}`}
              aria-label="切换循环模式"
            >
              {repeat === "one" ? <Repeat1 size={15} /> : <Repeat size={15} />}
            </button>
          </div>
          <div className="flex w-full max-w-lg items-center gap-2">
            <span className="w-9 text-right font-mono text-[10px] text-studio-500">
              {formatDuration(currentTime)}
            </span>
            <input
              type="range"
              min={0}
              max={Math.max(1, progressMax)}
              step={0.1}
              value={Math.min(currentTime, progressMax)}
              onChange={(event) => {
                const value = Number(event.target.value);
                setCurrentTime(value);
                if (audioRef.current) audioRef.current.currentTime = value;
              }}
              className="flex-1"
              aria-label="播放进度"
            />
            <span className="w-9 font-mono text-[10px] text-studio-500">
              {formatDuration(progressMax)}
            </span>
          </div>
        </div>

        <div className="hidden items-center gap-2 sm:flex">
          <Badge tone="neutral">{queue.length} 首</Badge>
          <button
            className="btn-icon h-8 w-8 border-0 bg-transparent"
            onClick={toggleMute}
            aria-label={muted ? "取消静音" : "静音"}
          >
            {muted || volume === 0 ? <VolumeX size={15} /> : <Volume2 size={15} />}
          </button>
          <input
            type="range"
            min={0}
            max={1}
            step={0.01}
            value={muted ? 0 : volume}
            onChange={(event) => setVolume(Number(event.target.value))}
            className="w-20"
            aria-label="音量"
          />
        </div>
      </div>
    </div>
  );
}

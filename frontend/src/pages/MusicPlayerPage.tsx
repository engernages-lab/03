import { useEffect } from "react";
import { Link } from "react-router-dom";
import {
  Heart,
  Pause,
  Play,
  Repeat,
  Repeat1,
  Shuffle,
  SkipBack,
  SkipForward,
  Volume2,
} from "lucide-react";
import clsx from "clsx";
import { usePlayerStore } from "../store/player";
import { useToggleFavorite, useWaveform } from "../lib/resources";
import { usePlayQueue } from "../lib/playback";
import { CoverArt, SourceBadge } from "../components/music/CoverArt";
import { Waveform } from "../components/music/Waveform";
import { Badge } from "../components/ui/Badge";
import { EmptyState } from "../components/ui/Feedback";
import { formatDuration } from "../lib/format";

export function MusicPlayerPage() {
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
    toggle,
    next,
    previous,
    playIndex,
    setVolume,
    toggleMute,
    toggleShuffle,
    cycleRepeat,
    setCurrentTime,
  } = usePlayerStore();
  const toggleFavorite = useToggleFavorite();
  const { playTrack } = usePlayQueue();

  const current = index >= 0 && index < queue.length ? queue[index] : null;
  const assetId = (current?.metadata?.audio_asset_id as string | undefined) ?? undefined;
  const waveform = useWaveform(assetId, 320);

  // Keyboard shortcuts: space toggles, arrows seek.
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement;
      if (["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) return;
      if (event.code === "Space") {
        event.preventDefault();
        toggle();
      } else if (event.code === "ArrowRight" && event.shiftKey) {
        next();
      } else if (event.code === "ArrowLeft" && event.shiftKey) {
        previous();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [toggle, next, previous]);

  if (!current) {
    return (
      <EmptyState
        title="播放队列是空的"
        description="从音乐资料库选择一首歌开始播放，队列会自动建立。"
        action={
          <Link to="/music-library" className="btn-primary">
            打开音乐资料库
          </Link>
        }
      />
    );
  }

  const progress = duration > 0 ? currentTime / duration : 0;
  const totalDuration = queue.reduce((sum, track) => sum + (track.duration || 0), 0);

  return (
    <div className="grid gap-4 xl:grid-cols-[1fr_360px]">
      <section className="panel overflow-hidden">
        <div className="relative p-6">
          <div className="pointer-events-none absolute -right-20 -top-24 h-64 w-64 rounded-full bg-accent/10 blur-3xl" />
          <div className="relative flex flex-col gap-5 sm:flex-row">
            <CoverArt
              src={current.artwork}
              title={current.title}
              size={200}
              rounded="rounded-2xl"
              className="shadow-panel"
            />
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <SourceBadge provider={current.source_provider} />
                <Badge tone={current.availability === "streamable" ? "success" : "warning"}>
                  {current.availability}
                </Badge>
                {current.metadata?.isrc ? <Badge tone="neutral">ISRC {String(current.metadata.isrc)}</Badge> : null}
              </div>
              <h2 className="mt-2 text-2xl font-semibold tracking-tight text-white">{current.title}</h2>
              <p className="text-sm text-studio-400">
                {current.artist} {current.album ? `· ${current.album}` : ""}
              </p>

              <div className="mt-4">
                <Waveform
                  peaks={waveform.data?.peaks ?? []}
                  progress={progress}
                  height={72}
                  onSeek={(ratio) => setCurrentTime(ratio * (duration || current.duration))}
                />
                <div className="mt-1 flex justify-between font-mono text-[10px] text-studio-500">
                  <span>{formatDuration(currentTime)}</span>
                  <span>{formatDuration(duration || current.duration)}</span>
                </div>
              </div>

              <div className="mt-4 flex items-center gap-2">
                <button className="btn-icon" onClick={previous} aria-label="上一首">
                  <SkipBack size={16} />
                </button>
                <button
                  className="grid h-12 w-12 place-items-center rounded-full bg-accent text-studio-950 transition hover:bg-accent-soft"
                  onClick={toggle}
                  aria-label={isPlaying ? "暂停" : "播放"}
                >
                  {isPlaying ? <Pause size={20} /> : <Play size={20} className="translate-x-[2px]" />}
                </button>
                <button className="btn-icon" onClick={next} aria-label="下一首">
                  <SkipForward size={16} />
                </button>
                <span className="mx-2 h-6 w-px bg-studio-700" />
                <button
                  className={clsx("btn-icon", shuffle && "text-accent")}
                  onClick={toggleShuffle}
                  title="随机播放"
                >
                  <Shuffle size={15} />
                </button>
                <button
                  className={clsx("btn-icon", repeat !== "off" && "text-accent")}
                  onClick={cycleRepeat}
                  title={`循环：${repeat}`}
                >
                  {repeat === "one" ? <Repeat1 size={15} /> : <Repeat size={15} />}
                </button>
                <button
                  className={clsx("btn-icon", current.is_favorite && "text-key-rose")}
                  onClick={() =>
                    toggleFavorite.mutate({
                      trackId: current.track_id,
                      favorite: current.is_favorite,
                    })
                  }
                  title={current.is_favorite ? "取消收藏" : "收藏"}
                >
                  <Heart size={15} fill={current.is_favorite ? "currentColor" : "none"} />
                </button>
                <div className="ml-auto hidden items-center gap-2 sm:flex">
                  <button className="btn-icon" onClick={toggleMute} aria-label="静音">
                    <Volume2 size={15} />
                  </button>
                  <input
                    type="range"
                    min={0}
                    max={1}
                    step={0.01}
                    value={muted ? 0 : volume}
                    onChange={(event) => setVolume(Number(event.target.value))}
                    className="w-24"
                    aria-label="音量"
                  />
                </div>
              </div>
              {!assetId && (
                <p className="mt-3 rounded-lg border border-studio-800 bg-studio-950/60 px-3 py-2 text-[11px] text-studio-500">
                  该曲目来自 {current.source_provider}，没有本地音频文件，因此不显示波形。
                  播放请使用来源允许的官方方式。
                </p>
              )}
            </div>
          </div>
        </div>
      </section>

      <section className="panel flex flex-col">
        <div className="panel-header">
          <h3 className="text-sm font-semibold text-white">播放队列</h3>
          <span className="font-mono text-[10px] text-studio-500">
            {queue.length} 首 · {formatDuration(totalDuration)}
          </span>
        </div>
        <div className="max-h-[60vh] flex-1 overflow-y-auto">
          {queue.map((track, position) => (
            <button
              key={`${track.track_id}-${position}`}
              onClick={() => playIndex(position)}
              className={clsx(
                "flex w-full items-center gap-2.5 border-b border-studio-800/50 px-3 py-2 text-left transition",
                position === index ? "bg-accent/10" : "hover:bg-studio-800/50",
              )}
            >
              <span className="w-5 shrink-0 text-center font-mono text-[10px] text-studio-500">
                {position + 1}
              </span>
              <CoverArt src={track.artwork} title={track.title} size={32} />
              <span className="min-w-0 flex-1">
                <span
                  className={clsx(
                    "block truncate text-xs",
                    position === index ? "text-accent" : "text-studio-100",
                  )}
                >
                  {track.title}
                </span>
                <span className="block truncate text-[10px] text-studio-500">{track.artist}</span>
              </span>
              <span className="font-mono text-[10px] text-studio-600">{formatDuration(track.duration)}</span>
            </button>
          ))}
        </div>
        <div className="border-t border-studio-800 px-3 py-2">
          <button
            className="btn-ghost h-8 w-full py-0 text-xs"
            onClick={() => playTrack(queue[index], queue)}
            disabled={shuffle}
            title={shuffle ? "随机模式下队列顺序不固定" : "按队列顺序重新开始"}
          >
            重新开始
          </button>
        </div>
      </section>
    </div>
  );
}

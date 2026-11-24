import clsx from "clsx";

export function Waveform({
  peaks,
  progress = 0,
  height = 64,
  onSeek,
  className,
}: {
  peaks: number[];
  progress?: number;
  height?: number;
  onSeek?: (ratio: number) => void;
  className?: string;
}) {
  if (!peaks.length) {
    return (
      <div
        className={clsx("flex items-center justify-center rounded-lg bg-studio-900 text-[11px] text-studio-600", className)}
        style={{ height }}
      >
        暂无波形数据
      </div>
    );
  }

  const barWidth = 100 / peaks.length;
  return (
    <div
      className={clsx("relative w-full cursor-pointer select-none", className)}
      style={{ height }}
      onClick={(event) => {
        if (!onSeek) return;
        const rect = event.currentTarget.getBoundingClientRect();
        onSeek(Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width)));
      }}
      role="presentation"
    >
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="h-full w-full">
        {peaks.map((peak, index) => {
          const played = index / peaks.length <= progress;
          const barHeight = Math.max(2, peak * 100);
          return (
            <rect
              key={index}
              x={index * barWidth}
              y={(100 - barHeight) / 2}
              width={Math.max(0.2, barWidth * 0.72)}
              height={barHeight}
              fill={played ? "#3ddc97" : "#3a4a67"}
              opacity={played ? 0.95 : 0.55}
            />
          );
        })}
      </svg>
      <div
        className="pointer-events-none absolute inset-y-0 w-px bg-white/70"
        style={{ left: `${Math.min(100, Math.max(0, progress * 100))}%` }}
      />
    </div>
  );
}

import clsx from "clsx";
import { staticUrl } from "../../lib/api";
import type { Provider } from "../../lib/types";
import { Badge } from "../ui/Badge";

const PROVIDER_LABEL: Record<string, string> = {
  local: "本地",
  subsonic: "Navidrome",
  apple_music: "Apple Music",
  spotify: "Spotify",
  netease: "网易云",
  qqmusic: "QQ 音乐",
  unknown: "未知来源",
};

const PROVIDER_TONE: Record<string, "success" | "info" | "violet" | "warning" | "neutral" | "danger"> = {
  local: "success",
  subsonic: "info",
  apple_music: "violet",
  spotify: "success",
  netease: "danger",
  qqmusic: "danger",
  unknown: "neutral",
};

export function providerLabel(provider: Provider | string): string {
  return PROVIDER_LABEL[provider] ?? String(provider);
}

export function SourceBadge({ provider, className }: { provider: Provider | string; className?: string }) {
  return (
    <Badge tone={PROVIDER_TONE[provider] ?? "neutral"} className={className}>
      {providerLabel(provider)}
    </Badge>
  );
}

export function CoverArt({
  src,
  title,
  size = 48,
  className,
  rounded = "rounded-lg",
}: {
  src?: string | null;
  title?: string;
  size?: number;
  className?: string;
  rounded?: string;
}) {
  const url = staticUrl(src);
  const initials = (title ?? "?")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((word) => word[0])
    .join("")
    .toUpperCase();

  if (url) {
    return (
      <img
        src={url}
        alt={title ?? "封面"}
        width={size}
        height={size}
        loading="lazy"
        className={clsx("shrink-0 object-cover", rounded, className)}
        style={{ width: size, height: size }}
        onError={(event) => {
          (event.currentTarget as HTMLImageElement).style.display = "none";
        }}
      />
    );
  }

  return (
    <div
      className={clsx(
        "grid shrink-0 place-items-center bg-gradient-to-br from-studio-700 to-studio-850 font-semibold text-studio-300",
        rounded,
        className,
      )}
      style={{ width: size, height: size, fontSize: Math.max(10, size / 3.2) }}
      aria-hidden
    >
      {initials || "♪"}
    </div>
  );
}

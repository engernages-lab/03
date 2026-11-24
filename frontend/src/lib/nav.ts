import type { LucideIcon } from "lucide-react";
import {
  AudioLines,
  Disc3,
  FolderClock,
  Heart,
  LayoutDashboard,
  Library,
  ListMusic,
  Music4,
  Radio,
  Settings2,
  SlidersHorizontal,
} from "lucide-react";

export interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  /** false -> rendered as a disabled entry with an explicit "not yet available" page. */
  ready: boolean;
  hint?: string;
}

export interface NavGroup {
  title: string;
  items: NavItem[];
}

export const NAV_GROUPS: NavGroup[] = [
  {
    title: "主控",
    items: [
      { to: "/dashboard", label: "工作台", icon: LayoutDashboard, ready: true },
      { to: "/music-player", label: "播放器", icon: Disc3, ready: true },
    ],
  },
  {
    title: "音乐",
    items: [
      { to: "/music-library", label: "音乐资料库", icon: Library, ready: true },
      { to: "/music-favorites", label: "我的收藏", icon: Heart, ready: true },
      { to: "/music-playlists", label: "我的歌单", icon: ListMusic, ready: true },
      { to: "/music-recent", label: "最近播放", icon: FolderClock, ready: true },
      { to: "/music-sources", label: "音乐来源", icon: Radio, ready: true },
    ],
  },
  {
    title: "制谱",
    items: [
      { to: "/transcription", label: "AI 扒谱", icon: AudioLines, ready: true },
      { to: "/scores", label: "我的谱面", icon: Music4, ready: true },
      { to: "/keyboard", label: "键盘设置", icon: SlidersHorizontal, ready: true },
    ],
  },
  {
    title: "系统",
    items: [{ to: "/settings", label: "系统设置", icon: Settings2, ready: true }],
  },
];

export const ALL_NAV_ITEMS: NavItem[] = NAV_GROUPS.flatMap((group) => group.items);

export function navItemFor(pathname: string): NavItem | undefined {
  return ALL_NAV_ITEMS.find(
    (item) => pathname === item.to || pathname.startsWith(`${item.to}/`),
  );
}

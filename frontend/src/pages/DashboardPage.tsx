import { Link } from "react-router-dom";
import {
  Activity,
  AudioLines,
  CheckCircle2,
  CircleSlash,
  Cpu,
  Disc3,
  Heart,
  Library,
  ListMusic,
  Music4,
  Radio,
  SlidersHorizontal,
  TriangleAlert,
} from "lucide-react";
import { useHealth, useReadiness } from "../lib/hooks";
import { useLibraryStats, useSources } from "../lib/resources";
import { usePlayerStore } from "../store/player";
import { Badge, Dot } from "../components/ui/Badge";
import { Skeleton, Spinner } from "../components/ui/Feedback";
import { CoverArt } from "../components/music/CoverArt";
import { formatDate, formatDuration } from "../lib/format";
import type { CapabilityKey } from "../lib/types";

const STAGE_PLAN = [
  { id: "A.1", label: "工程架构", done: true },
  { id: "A.2", label: "六大 Skill", done: true },
  { id: "A.3", label: "MusicDocument", done: true },
  { id: "A.4", label: "自定义键盘", done: true },
  { id: "A.5", label: "MIDI / 音频输入", done: true },
  { id: "A.6", label: "格子谱引擎", done: true },
  { id: "A.7", label: "数字谱与同步", done: true },
  { id: "A.8", label: "音乐中心与播放器", done: true },
  { id: "A.9", label: "测试与部署", done: true },
];

const CAPABILITY_ROWS: { key: CapabilityKey; label: string; required: boolean }[] = [
  { key: "ffmpeg", label: "FFmpeg", required: true },
  { key: "librosa", label: "librosa", required: false },
  { key: "soundfile", label: "soundfile", required: false },
  { key: "mido", label: "mido", required: true },
  { key: "pretty_midi", label: "pretty_midi", required: true },
  { key: "music21", label: "music21", required: false },
  { key: "mutagen", label: "mutagen", required: true },
];

export function DashboardPage() {
  const health = useHealth();
  const readiness = useReadiness();
  const stats = useLibraryStats();
  const sources = useSources();
  const queue = usePlayerStore((state) => state.queue);
  const index = usePlayerStore((state) => state.index);
  const current = index >= 0 ? queue[index] : null;

  if (health.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  if (health.isError) {
    return (
      <div className="panel border-key-rose/30 p-6">
        <div className="flex items-start gap-3">
          <TriangleAlert className="mt-0.5 text-key-rose" size={20} />
          <div className="space-y-1">
            <h2 className="text-sm font-semibold text-white">无法连接后端 API</h2>
            <p className="text-xs leading-relaxed text-studio-400">
              请确认 FastAPI 服务已启动：
              <code className="font-mono text-studio-200">uvicorn app.main:app --port 8000</code>
              （默认 http://127.0.0.1:8000）。前端开发服务器通过 <code className="font-mono">/api</code> 代理访问后端。
            </p>
            <p className="font-mono text-[11px] text-studio-500">{(health.error as Error)?.message}</p>
          </div>
        </div>
      </div>
    );
  }

  const data = health.data!;
  const caps = data.capabilities;
  const checks = readiness.data?.checks;

  const workbench = [
    { to: "/music-library", label: "音乐资料库", value: stats.data?.tracks ?? 0, unit: "首", icon: Library },
    { to: "/music-favorites", label: "我的收藏", value: stats.data?.favorites ?? 0, unit: "首", icon: Heart },
    { to: "/music-playlists", label: "我的歌单", value: stats.data?.playlists ?? 0, unit: "个", icon: ListMusic },
    { to: "/music-sources", label: "音乐来源", value: sources.data?.length ?? 0, unit: "个", icon: Radio },
    { to: "/scores", label: "我的谱面", value: stats.data?.transcription_jobs ?? 0, unit: "个作业", icon: Music4 },
    { to: "/keyboard", label: "键盘设置", value: "布局", unit: "", icon: SlidersHorizontal },
  ];

  return (
    <div className="space-y-5">
      <section className="panel relative overflow-hidden p-6">
        <div className="pointer-events-none absolute -right-24 -top-24 h-64 w-64 rounded-full bg-accent/10 blur-3xl" />
        <div className="relative flex flex-wrap items-start justify-between gap-4">
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <Badge tone="success">
                <Dot tone="success" pulse /> {data.status.toUpperCase()}
              </Badge>
              <Badge tone="info">{data.stage}</Badge>
              <Badge>{data.environment}</Badge>
            </div>
            <h2 className="text-2xl font-semibold tracking-tight text-white">
              {data.name} <span className="font-mono text-base text-studio-400">v{data.version}</span>
            </h2>
            <p className="max-w-2xl text-sm leading-relaxed text-studio-400">
              多音源统一曲库 + 完整播放器 + AI 扒谱输入管线 + 自定义口袋键盘 + 格子谱 / 数字谱双引擎。
              所有数值都来自真实接口，未实现的平台会明确标注原因。
            </p>
          </div>
          <div className="flex flex-col items-end gap-1 text-right">
            <span className="text-[11px] uppercase tracking-wider text-studio-500">服务时间</span>
            <span className="font-mono text-xs text-studio-300">{formatDate(data.timestamp)}</span>
            <span className="font-mono text-[11px] text-studio-500">Python {caps.python}</span>
          </div>
        </div>

        <div className="relative mt-5 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
          {workbench.map((item) => {
            const Icon = item.icon;
            return (
              <Link
                key={item.to}
                to={item.to}
                className="group rounded-xl border border-studio-800 bg-studio-950/50 px-3 py-3 transition hover:border-accent/40 hover:bg-studio-900"
              >
                <Icon size={15} className="text-studio-400 transition group-hover:text-accent" />
                <p className="mt-2 font-mono text-lg font-semibold text-white">
                  {item.value}
                  <span className="ml-1 text-[10px] font-normal text-studio-500">{item.unit}</span>
                </p>
                <p className="text-[11px] text-studio-400">{item.label}</p>
              </Link>
            );
          })}
        </div>
      </section>

      <div className="grid gap-5 lg:grid-cols-3">
        <section className="panel lg:col-span-2">
          <div className="panel-header">
            <div className="flex items-center gap-2">
              <Cpu size={15} className="text-accent" />
              <h3 className="text-sm font-semibold text-white">运行时能力探测</h3>
            </div>
            {readiness.isFetching && <Spinner label="检查中" />}
          </div>
          <div className="divide-y divide-studio-800/60">
            {CAPABILITY_ROWS.map((row) => {
              const cap = caps[row.key];
              const ok = cap?.available;
              return (
                <div key={row.key} className="flex items-center justify-between gap-3 px-5 py-2.5">
                  <div className="flex min-w-0 items-center gap-2">
                    {ok ? (
                      <CheckCircle2 size={14} className="shrink-0 text-accent" />
                    ) : (
                      <CircleSlash size={14} className="shrink-0 text-key-rose" />
                    )}
                    <span className="text-sm text-studio-200">{row.label}</span>
                    {!row.required && <Badge tone="neutral">可选</Badge>}
                  </div>
                  <div className="flex min-w-0 items-center gap-2">
                    {ok ? (
                      <>
                        <span className="max-w-[220px] truncate font-mono text-[11px] text-studio-500">
                          {cap.version ?? "installed"}
                        </span>
                        <Badge tone="success">可用</Badge>
                      </>
                    ) : (
                      <Badge tone="danger">{row.required ? "缺失 · 阻塞" : "缺失 · 降级"}</Badge>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </section>

        <section className="panel">
          <div className="panel-header">
            <h3 className="text-sm font-semibold text-white">继续工作</h3>
          </div>
          <div className="space-y-2 p-3">
            {current ? (
              <div className="flex items-center gap-3 rounded-lg border border-studio-800 bg-studio-950/60 p-2.5">
                <CoverArt src={current.artwork} title={current.title} size={40} />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-xs font-medium text-white">{current.title}</p>
                  <p className="truncate text-[10px] text-studio-500">{current.artist}</p>
                </div>
                <Link to="/music-player" className="btn-icon h-7 w-7" title="打开播放器">
                  <Disc3 size={13} />
                </Link>
              </div>
            ) : (
              <p className="rounded-lg border border-studio-800 bg-studio-950/60 px-3 py-3 text-[11px] text-studio-500">
                播放队列为空。从音乐资料库选择一首开始。
              </p>
            )}
            <Link to="/transcription" className="btn-ghost w-full justify-start">
              <AudioLines size={14} /> AI 扒谱 / MIDI 导入
            </Link>
            <Link to="/scores" className="btn-ghost w-full justify-start">
              <Music4 size={14} /> 我的谱面
            </Link>
            <Link to="/music-sources" className="btn-ghost w-full justify-start">
              <Radio size={14} /> 连接音乐来源
            </Link>
            <div className="rounded-lg border border-studio-800 bg-studio-950/60 p-2.5">
              <p className="mb-1 text-[10px] uppercase tracking-wider text-studio-500">阶段进度</p>
              <div className="flex flex-wrap gap-1">
                {STAGE_PLAN.map((stage) => (
                  <span
                    key={stage.id}
                    title={stage.label}
                    className={`rounded px-1.5 py-0.5 font-mono text-[9px] ${
                      stage.done ? "bg-accent/15 text-accent" : "bg-studio-800 text-studio-500"
                    }`}
                  >
                    {stage.id}
                  </span>
                ))}
              </div>
            </div>
          </div>
        </section>
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <section className="panel">
          <div className="panel-header">
            <div className="flex items-center gap-2">
              <Activity size={15} className="text-key-violet" />
              <h3 className="text-sm font-semibold text-white">就绪检查</h3>
            </div>
            <Badge tone={readiness.data?.status === "ready" ? "success" : "warning"}>
              {readiness.data?.status ?? "…"}
            </Badge>
          </div>
          <div className="space-y-2 px-5 py-4">
            {checks
              ? Object.entries(checks).map(([name, check]) => (
                  <div key={name} className="flex items-center justify-between text-sm">
                    <span className="text-studio-300">{name}</span>
                    <span className="flex items-center gap-2">
                      {check.optional && <Badge tone="neutral">可选</Badge>}
                      <Badge tone={check.ok ? "success" : check.optional ? "warning" : "danger"}>
                        {check.ok ? "通过" : "未通过"}
                      </Badge>
                    </span>
                  </div>
                ))
              : Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-5 w-full" />)}
          </div>
        </section>

        <section className="panel">
          <div className="panel-header">
            <h3 className="text-sm font-semibold text-white">资料库概况</h3>
            <Badge tone="neutral">{formatDuration(stats.data?.total_duration ?? 0)}</Badge>
          </div>
          <div className="space-y-2 px-5 py-4 text-sm">
            {sources.data?.map((source) => (
              <div key={source.source_id} className="flex items-center justify-between gap-2">
                <span className="flex min-w-0 items-center gap-2">
                  <Dot tone={source.status === "connected" ? "success" : source.status === "error" ? "danger" : "neutral"} />
                  <span className="truncate text-studio-300">{source.display_name}</span>
                </span>
                <Badge
                  tone={
                    source.status === "connected"
                      ? "success"
                      : source.status === "unsupported"
                        ? "danger"
                        : "neutral"
                  }
                >
                  {source.status}
                </Badge>
              </div>
            ))}
            {sources.data?.length === 0 && (
              <p className="text-[11px] text-studio-500">尚未配置任何音乐来源。</p>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}

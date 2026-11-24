import { useState } from "react";
import { Check, Copy, Database, HardDrive, Server, ShieldCheck } from "lucide-react";
import { useHealth, useReadiness } from "../lib/hooks";
import { API_BASE, API_V1 } from "../lib/api";
import { Badge } from "../components/ui/Badge";
import { Skeleton } from "../components/ui/Feedback";
import { formatDate } from "../lib/format";

function CopyRow({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="flex items-center justify-between gap-3 border-b border-studio-800/60 px-5 py-2.5 last:border-0">
      <span className="shrink-0 text-xs text-studio-400">{label}</span>
      <div className="flex min-w-0 items-center gap-2">
        <code className="truncate font-mono text-xs text-studio-200">{value}</code>
        <button
          className="btn-icon h-7 w-7 shrink-0"
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(value);
              setCopied(true);
              setTimeout(() => setCopied(false), 1200);
            } catch {
              /* clipboard unavailable */
            }
          }}
          aria-label={`复制 ${label}`}
        >
          {copied ? <Check size={13} className="text-accent" /> : <Copy size={13} />}
        </button>
      </div>
    </div>
  );
}

export function SettingsPage() {
  const health = useHealth();
  const readiness = useReadiness();

  if (health.isLoading) return <Skeleton className="h-64 w-full" />;

  const data = health.data;
  const caps = data?.capabilities;

  return (
    <div className="space-y-5">
      <section className="panel">
        <div className="panel-header">
          <div className="flex items-center gap-2">
            <Server size={15} className="text-accent" />
            <h3 className="text-sm font-semibold text-white">连接信息</h3>
          </div>
          <Badge tone={health.isError ? "danger" : "success"}>{health.isError ? "离线" : "在线"}</Badge>
        </div>
        <CopyRow label="API 根地址" value={API_BASE || window.location.origin} />
        <CopyRow label="API v1 前缀" value={API_V1} />
        <CopyRow label="健康检查" value={`${API_V1}/health`} />
        <CopyRow label="接口文档" value={`${API_BASE || window.location.origin}/docs`} />
        <CopyRow label="构建阶段" value={data?.stage ?? "V1.0-A"} />
        <CopyRow label="前端版本" value="1.0.0-a" />
        <CopyRow label="后端版本" value={data?.version ?? "—"} />
      </section>

      <div className="grid gap-5 lg:grid-cols-2">
        <section className="panel">
          <div className="panel-header">
            <div className="flex items-center gap-2">
              <HardDrive size={15} className="text-key-cyan" />
              <h3 className="text-sm font-semibold text-white">运行环境</h3>
            </div>
          </div>
          <div className="space-y-2 px-5 py-4 text-sm">
            <div className="flex justify-between">
              <span className="text-studio-400">Python</span>
              <span className="font-mono text-studio-200">{caps?.python ?? "—"}</span>
            </div>
            <div className="flex justify-between gap-4">
              <span className="shrink-0 text-studio-400">平台</span>
              <span className="truncate text-right font-mono text-[11px] text-studio-300">
                {caps?.platform ?? "—"}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-studio-400">服务时间</span>
              <span className="font-mono text-xs text-studio-300">{formatDate(data?.timestamp)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-studio-400">FFmpeg</span>
              <Badge tone={caps?.ffmpeg.available ? "success" : "danger"}>
                {caps?.ffmpeg.available ? "已就绪" : "缺失"}
              </Badge>
            </div>
          </div>
        </section>

        <section className="panel">
          <div className="panel-header">
            <div className="flex items-center gap-2">
              <Database size={15} className="text-key-violet" />
              <h3 className="text-sm font-semibold text-white">数据与存储</h3>
            </div>
          </div>
          <div className="space-y-2 px-5 py-4 text-sm">
            <div className="flex justify-between">
              <span className="text-studio-400">数据库</span>
              <span className="font-mono text-xs text-studio-200">SQLite (WAL)</span>
            </div>
            <div className="flex justify-between">
              <span className="text-studio-400">就绪状态</span>
              <Badge tone={readiness.data?.status === "ready" ? "success" : "warning"}>
                {readiness.data?.status ?? "—"}
              </Badge>
            </div>
            <div className="flex justify-between">
              <span className="text-studio-400">迁移工具</span>
              <span className="font-mono text-xs text-studio-200">Alembic</span>
            </div>
            <div className="flex justify-between">
              <span className="text-studio-400">音频资产</span>
              <span className="font-mono text-xs text-studio-200">backend/data/storage</span>
            </div>
          </div>
        </section>
      </div>

      <section className="panel">
        <div className="panel-header">
          <div className="flex items-center gap-2">
            <ShieldCheck size={15} className="text-accent" />
            <h3 className="text-sm font-semibold text-white">安全与合规策略</h3>
          </div>
        </div>
        <ul className="space-y-2 px-5 py-4 text-xs leading-relaxed text-studio-400">
          <li>• 第三方账号令牌使用 Fernet 对称加密后落库，任何接口都不会回传明文令牌。</li>
          <li>• Spotify 内容标记为 PROVIDER_RESTRICTED，永远不进入 AI 扒谱音频链路。</li>
          <li>• Apple Music 仅通过 MusicKit 官方授权播放，不下载、不转存音频流。</li>
          <li>• 本地音乐必须由用户显式选择或授权目录后才会上传/索引，不上传未经同意的文件。</li>
          <li>• 所有音源服务器地址经过 SSRF 校验（协议白名单 + 私网策略 + DNS 解析复核）。</li>
        </ul>
      </section>
    </div>
  );
}

import { useEffect, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  ExternalLink,
  Link2,
  Plug,
  RefreshCw,
  ShieldCheck,
  Trash2,
  Unplug,
} from "lucide-react";
import clsx from "clsx";
import {
  useCreateSource,
  useDeleteSource,
  useProviders,
  useSourcePermissions,
  useSources,
  useSyncSource,
  useTestSource,
  useUpdateSourcePermissions,
} from "../lib/resources";
import { Badge } from "../components/ui/Badge";
import { Spinner } from "../components/ui/Feedback";
import type { MusicSource, Provider } from "../lib/types";
import { formatRelative } from "../lib/format";

const STATUS_TONE: Record<string, "success" | "warning" | "danger" | "neutral"> = {
  connected: "success",
  disconnected: "neutral",
  not_configured: "warning",
  needs_authorization: "warning",
  unsupported: "danger",
  error: "danger",
};

function PermissionToggles({ source }: { source: MusicSource }) {
  const permissions = useSourcePermissions(source.source_id);
  const update = useUpdateSourcePermissions(source.source_id);
  // Optimistic overrides so the checkbox reacts immediately; the server value
  // replaces them as soon as the query refetches.
  const [local, setLocal] = useState<Record<string, boolean>>({});

  useEffect(() => {
    setLocal({});
  }, [permissions.data]);

  const rows: { key: string; label: string; hint: string; locked?: boolean }[] = [
    { key: "metadata_access", label: "元数据访问", hint: "读取曲名/艺人/专辑" },
    { key: "playback_access", label: "播放权限", hint: "通过官方方式播放" },
    { key: "audio_read_access", label: "音频读取", hint: "可读取原始音频字节" },
    { key: "ai_processing_permission", label: "AI 处理授权", hint: "允许送入扒谱管线" },
    { key: "model_training_permission", label: "模型训练授权", hint: "与单次处理分离" },
  ];

  const restricted = source.provider === "spotify";
  const unsupported = ["netease", "qqmusic"].includes(source.provider);

  return (
    <div className="mt-3 space-y-1.5 rounded-lg border border-studio-800 bg-studio-950/50 p-3">
      <div className="mb-1 flex items-center gap-1.5 text-[11px] font-medium text-studio-300">
        <ShieldCheck size={12} /> 五项权限（独立判断）
      </div>
      {rows.map((row) => {
        const value = local[row.key] ?? Boolean(permissions.data?.[row.key]);
        const locked = restricted || unsupported;
        return (
          <label
            key={row.key}
            className={clsx(
              "flex items-center justify-between gap-2 text-[11px]",
              locked ? "text-studio-600" : "text-studio-400",
            )}
          >
            <span className="flex items-center gap-2">
              <input
                type="checkbox"
                className="h-3.5 w-3.5 accent-[#3ddc97]"
                checked={value}
                disabled={locked || update.isPending}
                onChange={(event) => {
                  const next = event.target.checked;
                  setLocal((current) => ({ ...current, [row.key]: next }));
                  update.mutate({ [row.key]: next });
                }}
              />
              {row.label}
              <span className="text-studio-600">· {row.hint}</span>
            </span>
            {locked && <span className="font-mono text-[10px] text-key-rose">策略锁定</span>}
          </label>
        );
      })}
      {restricted && (
        <p className="pt-1 text-[10px] leading-relaxed text-key-rose">
          Spotify 内容受平台政策限制，永久不可用于 AI 分析或模型训练。
        </p>
      )}
    </div>
  );
}

function SourceCard({ source }: { source: MusicSource }) {
  const test = useTestSource();
  const sync = useSyncSource();
  const remove = useDeleteSource();
  const [feedback, setFeedback] = useState<string | null>(null);

  return (
    <div className="panel p-4">
      <div className="flex flex-wrap items-start gap-3">
        <div className="grid h-10 w-10 place-items-center rounded-xl bg-studio-800 text-accent">
          {source.status === "connected" ? <CheckCircle2 size={18} /> : <Unplug size={18} />}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-sm font-semibold text-white">{source.display_name}</h3>
            <Badge tone={STATUS_TONE[source.status] ?? "neutral"}>{source.status}</Badge>
            {source.account_name && <Badge tone="info">{source.account_name}</Badge>}
            {source.is_local && <Badge tone="success">本地</Badge>}
          </div>
          <p className="mt-1 text-[11px] leading-relaxed text-studio-500">{source.policy_note}</p>
          {source.connected_at && (
            <p className="text-[10px] text-studio-600">连接于 {formatRelative(source.connected_at)}</p>
          )}
          {source.last_error && (
            <p className="mt-1 flex items-center gap-1 text-[11px] text-key-rose">
              <AlertCircle size={11} /> {source.last_error}
            </p>
          )}
        </div>
        <div className="flex items-center gap-1.5">
          <button
            className="btn-ghost h-8 py-0 text-xs"
            onClick={async () => {
              const result = await test.mutateAsync(source.source_id);
              setFeedback(result.message);
            }}
            disabled={test.isPending}
          >
            <Plug size={13} /> 测试连接
          </button>
          {source.capabilities.metadata && !source.is_local && (
            <button
              className="btn-ghost h-8 py-0 text-xs"
              onClick={async () => {
                const result = await sync.mutateAsync(source.source_id);
                setFeedback(result.message);
              }}
              disabled={sync.isPending}
            >
              <RefreshCw size={13} className={clsx(sync.isPending && "animate-spin")} /> 同步曲库
            </button>
          )}
          {!source.is_local && (
            <button
              className="btn-icon h-8 w-8 text-key-rose/70 hover:text-key-rose"
              onClick={() => {
                if (window.confirm(`断开并删除来源《${source.display_name}》？`)) {
                  remove.mutate(source.source_id);
                }
              }}
              title="删除来源"
            >
              <Trash2 size={13} />
            </button>
          )}
        </div>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-1.5 sm:grid-cols-5">
        {[
          ["元数据", source.capabilities.metadata],
          ["播放", source.capabilities.playback],
          ["音频读取", source.capabilities.audio_read],
          ["AI 处理", source.capabilities.ai_processing],
          ["模型训练", source.capabilities.model_training],
        ].map(([label, value]) => (
          <div
            key={String(label)}
            className={clsx(
              "rounded-md border px-2 py-1 text-center text-[10px]",
              value ? "border-accent/20 bg-accent/5 text-accent" : "border-studio-800 text-studio-600",
            )}
          >
            {label}
            <span className="ml-1 font-mono">{value ? "✓" : "—"}</span>
          </div>
        ))}
      </div>

      {feedback && <p className="mt-2 text-[11px] text-studio-300">{feedback}</p>}
      <PermissionToggles source={source} />
    </div>
  );
}

function ConnectForm({ provider }: { provider: Provider }) {
  const create = useCreateSource();
  const [form, setForm] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);

  const fields: { key: string; label: string; placeholder?: string; type?: string }[] =
    provider === "subsonic"
      ? [
          { key: "server_url", label: "服务器地址", placeholder: "https://music.example.com" },
          { key: "username", label: "用户名" },
          { key: "password", label: "密码 / 令牌", type: "password" },
        ]
      : provider === "apple_music"
        ? [
            { key: "team_id", label: "Team ID" },
            { key: "key_id", label: "Key ID" },
            { key: "private_key_path", label: ".p8 私钥路径", placeholder: "C:\\keys\\AuthKey.p8" },
            { key: "storefront", label: "Storefront", placeholder: "us / cn" },
          ]
        : provider === "spotify"
          ? [
              { key: "client_id", label: "Client ID" },
              { key: "client_secret", label: "Client Secret", type: "password" },
              { key: "redirect_uri", label: "回调地址", placeholder: "http://127.0.0.1:8000/api/v1/sources/spotify/callback" },
            ]
          : [];

  const submit = async () => {
    setError(null);
    setOk(null);
    try {
      const created = await create.mutateAsync({ provider, ...form });
      setOk(`已创建来源 ${created.display_name}，点击“测试连接”完成验证。`);
      setForm({});
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : "创建失败");
    }
  };

  if (!fields.length) {
    return (
      <div className="rounded-lg border border-studio-800 bg-studio-950/50 p-3 text-[11px] leading-relaxed text-studio-500">
        <p className="mb-1 flex items-center gap-1 text-key-amber">
          <AlertCircle size={12} /> 该平台暂无官方第三方接口
        </p>
        为保证合规，PocketScore 不会使用模拟登录、Cookie 注入或逆向接口。
      </div>
    );
  }

  return (
    <div className="mt-3 space-y-2 rounded-lg border border-studio-800 bg-studio-950/50 p-3">
      {fields.map((field) => (
        <label key={field.key} className="block">
          <span className="label mb-1 text-[10px]">{field.label}</span>
          <input
            className="input h-8 py-0 text-xs"
            type={field.type ?? "text"}
            placeholder={field.placeholder}
            value={form[field.key] ?? ""}
            onChange={(event) => setForm({ ...form, [field.key]: event.target.value })}
          />
        </label>
      ))}
      <button className="btn-primary h-8 w-full py-0 text-xs" onClick={submit} disabled={create.isPending}>
        <Link2 size={13} /> 创建连接
      </button>
      {error && <p className="text-[11px] text-key-rose">{error}</p>}
      {ok && <p className="text-[11px] text-accent">{ok}</p>}
    </div>
  );
}

export function MusicSourcesPage() {
  const providers = useProviders();
  const sources = useSources();
  const [openProvider, setOpenProvider] = useState<string | null>(null);

  return (
    <div className="space-y-5">
      <section className="panel">
        <div className="panel-header">
          <div>
            <h3 className="text-sm font-semibold text-white">已连接的音乐来源</h3>
            <p className="text-[11px] text-studio-500">
              每个来源的权限独立判断；播放能力不等于扒谱能力。
            </p>
          </div>
          <Badge tone="neutral">{sources.data?.length ?? 0} 个</Badge>
        </div>
        <div className="space-y-3 p-3">
          {sources.isLoading && <Spinner label="加载中" />}
          {sources.data?.map((source) => <SourceCard key={source.source_id} source={source} />)}
        </div>
      </section>

      <section>
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-studio-400">
          可接入的平台
        </h3>
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {providers.data?.items
            .filter((provider) => provider.provider !== "local")
            .map((provider) => (
              <div key={provider.provider} className="panel flex flex-col p-4">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <h4 className="text-sm font-semibold text-white">{provider.display_name}</h4>
                    <p className="mt-1 text-[11px] leading-relaxed text-studio-500">{provider.description}</p>
                  </div>
                  <Badge
                    tone={
                      provider.capabilities.metadata
                        ? provider.capabilities.ai_processing
                          ? "success"
                          : "info"
                        : "danger"
                    }
                  >
                    {provider.capabilities.metadata ? "可接入" : "不可用"}
                  </Badge>
                </div>

                <p className="mt-2 rounded-md bg-studio-950/60 px-2 py-1.5 text-[10px] leading-relaxed text-studio-500">
                  {provider.policy_note}
                </p>

                <div className="mt-2 flex flex-wrap gap-1">
                  {provider.docs.map((doc) => (
                    <a
                      key={doc}
                      href={doc}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1 rounded border border-studio-700 px-1.5 py-0.5 text-[10px] text-studio-400 hover:text-accent"
                    >
                      <ExternalLink size={9} /> 官方文档
                    </a>
                  ))}
                </div>

                <button
                  className="btn-ghost mt-3 h-8 py-0 text-xs"
                  onClick={() => setOpenProvider(openProvider === provider.provider ? null : provider.provider)}
                >
                  {openProvider === provider.provider ? "收起" : "添加连接"}
                </button>
                {openProvider === provider.provider && <ConnectForm provider={provider.provider} />}
              </div>
            ))}
        </div>
      </section>
    </div>
  );
}

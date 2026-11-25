import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  AlertTriangle,
  AudioLines,
  Ban,
  CheckCircle2,
  FileMusic,
  RotateCcw,
  Gauge,
  Play,
  ShieldQuestion,
  Upload,
} from "lucide-react";
import clsx from "clsx";
import {
  useCreateTranscriptionJob,
  useEligibility,
  useImportMidi,
  useInspectMidi,
  useLibraryStats,
  useCancelTranscriptionJob,
  useRunTranscriptionJob,
  useTranscriptionCapabilities,
  useTracks,
  useTranscriptionJobs,
  useTranscriptionModels,
  useUploadAudio,
} from "../lib/resources";
import { Badge } from "../components/ui/Badge";
import { EmptyState, Spinner } from "../components/ui/Feedback";
import { formatDuration, formatRelative } from "../lib/format";
import type { EligibilityStatus, TranscriptionJob } from "../lib/types";

const STATUS_TONE: Record<EligibilityStatus, "success" | "warning" | "danger" | "neutral" | "info"> = {
  ELIGIBLE: "success",
  REQUIRES_PERMISSION: "warning",
  REQUIRES_USER_UPLOAD: "warning",
  INELIGIBLE: "danger",
  PROVIDER_RESTRICTED: "danger",
  UNKNOWN: "neutral",
};

const STATUS_LABEL: Record<EligibilityStatus, string> = {
  ELIGIBLE: "可以扒谱",
  REQUIRES_PERMISSION: "需要授权",
  REQUIRES_USER_UPLOAD: "需要上传音频",
  INELIGIBLE: "不可扒谱",
  PROVIDER_RESTRICTED: "平台政策禁止",
  UNKNOWN: "未知",
};

const JOB_TONE: Record<string, "success" | "warning" | "danger" | "info" | "neutral"> = {
  analysis_only: "warning",
  completed: "success",
  failed: "danger",
  cancelled: "neutral",
  queued: "info",
  validating: "info",
  preprocessing: "info",
  transcribing: "info",
  postprocessing: "info",
  analyzing: "info",
};

const STAGE_LABEL: Record<string, string> = {
  queued: "排队中",
  validating: "校验文件",
  preprocessing: "音频预处理",
  transcribing: "AI 识别音符",
  postprocessing: "生成谱面",
  completed: "已完成",
  analysis_only: "仅信号分析",
  failed: "失败",
  cancelled: "已取消",
};

const ACTIVE_STATES = [
  "queued",
  "validating",
  "preprocessing",
  "transcribing",
  "postprocessing",
  "analyzing",
];

function JobCard({ job }: { job: TranscriptionJob }) {
  const run = useRunTranscriptionJob();
  const cancel = useCancelTranscriptionJob();
  const navigate = useNavigate();
  const active = ACTIVE_STATES.includes(job.status);
  return (
    <div data-testid="job-card" className="rounded-lg border border-studio-800 bg-studio-950/40 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span data-testid="job-status" className="sr-only">{job.status}</span>
        <Badge tone={JOB_TONE[job.status] ?? "neutral"}>{job.status}</Badge>        <span className="text-[11px] text-studio-300">{STAGE_LABEL[job.status] ?? job.status}</span>
        <span className="font-mono text-[10px] text-studio-500">{job.job_id}</span>
        <span className="text-[11px] text-studio-400">
          {job.source_kind === "music_source" ? "来自曲库" : "本地音频"}
        </span>
        <span className="ml-auto text-[10px] text-studio-600">{formatRelative(job.created_at)}</span>
      </div>

      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-studio-800">
        <div
          className={clsx(
            "h-full rounded-full transition-all",
            job.status === "failed"
              ? "bg-key-rose"
              : job.status === "analysis_only"
                ? "bg-key-amber"
                : job.status === "completed"
                  ? "bg-accent"
                  : "bg-key-cyan",
          )}
          style={{ width: `${job.progress}%` }}
        />
      </div>
      <p className="mt-1 text-[10px] text-studio-500">
        进度 {job.progress}%{active ? " · 后端正在处理，可以离开本页稍后回来查看" : ""}
      </p>

      {job.analysis && (
        <div className="mt-2 grid grid-cols-2 gap-1.5 text-[10px] text-studio-400 sm:grid-cols-4">
          <span>时长 {formatDuration(job.analysis.duration)}</span>
          <span>BPM {job.analysis.bpm ?? "—"}</span>
          <span>起音 {job.analysis.onsets}</span>
          <span>采样率 {job.analysis.sample_rate}</span>
        </div>
      )}

      {job.warnings.length > 0 && (
        <p className="mt-2 flex items-start gap-1 text-[10px] leading-relaxed text-key-amber">
          <AlertTriangle size={11} className="mt-0.5 shrink-0" />
          {job.warnings[job.warnings.length - 1]}
        </p>
      )}
      {job.error && <p className="mt-1 text-[10px] text-key-rose">{job.error}</p>}

      <div className="mt-2 flex flex-wrap items-center gap-2">
        {job.status === "completed" && job.document_id && (
          <button
            className="btn-primary h-7 py-0 text-[11px]"
            onClick={() => navigate(`/scores/${job.document_id}`)}
          >
            <FileMusic size={12} /> 打开谱面
          </button>
        )}
        {job.status === "queued" && (
          <button
            className="btn-ghost h-7 py-0 text-[11px]"
            onClick={() => run.mutate(job.job_id)}
            disabled={run.isPending}
          >
            立即执行
          </button>
        )}
        {job.status === "failed" && (
          <button
            className="btn-ghost h-7 py-0 text-[11px]"
            onClick={() => run.mutate(job.job_id)}
            disabled={run.isPending}
          >
            <RotateCcw size={12} /> 重新尝试
          </button>
        )}
        {active && (
          <button
            className="btn-ghost h-7 py-0 text-[11px]"
            onClick={() => cancel.mutate(job.job_id)}
            disabled={cancel.isPending}
          >
            取消
          </button>
        )}
      </div>
      <p className="mt-1.5 text-[10px] text-studio-600">
        生成音符 {job.events_produced} 个 · 方法 {job.method ?? "—"} · 置信度{" "}
        {Math.round(job.confidence * 100)}%
      </p>
    </div>
  );
}

export function TranscriptionPage() {
  const navigate = useNavigate();
  const models = useTranscriptionModels();
  const capabilities = useTranscriptionCapabilities();
  const jobs = useTranscriptionJobs();
  const stats = useLibraryStats();
  const tracks = useTracks({ limit: 100 });
  const uploadAudio = useUploadAudio();
  const createJob = useCreateTranscriptionJob();
  const importMidi = useImportMidi();
  const inspectMidi = useInspectMidi();

  const [selectedTrackId, setSelectedTrackId] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const audioInput = useRef<HTMLInputElement | null>(null);
  const midiInput = useRef<HTMLInputElement | null>(null);

  const eligibility = useEligibility(selectedTrackId ?? undefined);
  const selectedTrack = tracks.data?.items.find((track) => track.track_id === selectedTrackId) ?? null;
  const modelReady = Boolean(models.data?.note_extraction.available);

  const handleAudioUpload = async (file: File) => {
    setMessage(null);
    try {
      const asset = await uploadAudio.mutateAsync((() => {
        const form = new FormData();
        form.append("file", file);
        return form;
      })());
      const job = await createJob.mutateAsync({ asset_id: asset.asset_id });
      setMessage(
        modelReady
          ? `已开始 AI 扒谱：${file.name}（${formatDuration(asset.duration)}）· 作业 ${job.job_id}，完成后点「打开谱面」`
          : `已创建分析作业 ${job.job_id}（未安装模型，只做信号分析，不会生成音符）`,
      );
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "上传失败");
    }
  };

  const handleMidi = async (file: File) => {
    setMessage(null);
    try {
      const info = await inspectMidi.mutateAsync(file);
      const document = await importMidi.mutateAsync({ file, title: file.name.replace(/\.(mid|midi)$/i, "") });
      setMessage(
        `MIDI 已解析：${info.notes} 个音符 / ${info.tracks} 轨 / ${info.tempo} BPM，正在打开谱面…`,
      );
      navigate(`/scores/${document.document_id}`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "MIDI 导入失败");
    }
  };

  return (
    <div className="space-y-5">
      {/* model status */}
      <section className="panel p-4">
        <div className="flex flex-wrap items-start gap-3">
          <div
            className={clsx(
              "grid h-10 w-10 place-items-center rounded-xl",
              modelReady ? "bg-accent/15 text-accent" : "bg-key-amber/15 text-key-amber",
            )}
          >
            {modelReady ? <CheckCircle2 size={18} /> : <ShieldQuestion size={18} />}
          </div>
          <div className="min-w-0 flex-1">
            <h3 className="text-sm font-semibold text-white">
              {modelReady ? "AI 扒谱模型已就绪" : "扒谱模型未就绪"}
            </h3>
            {modelReady ? (
              <p className="mt-1 text-[11px] leading-relaxed text-studio-400">
                已接入 <b>{models.data?.note_extraction.name}</b>{" "}
                {models.data?.note_extraction.version}（{models.data?.note_extraction.license}，
                {models.data?.note_extraction.runtime ?? "onnxruntime"}）。上传音频后会真实解码并识别
                音高、起止时间与力度，结果写入同一份 MusicDocument，可直接进入格子谱 / 数字谱编辑。
                复音与多乐器精度有限，请人工校对。
              </p>
            ) : (
              <p className="mt-1 text-[11px] leading-relaxed text-studio-400">
                未检测到可用的扒谱模型，音频只会做信号分析（节拍/起音/能量），<b>不会生成任何音符</b>。
                安装方式：<code className="font-mono">pip install basic-pitch</code>
                （Windows + Python&lt;3.11 会自动使用 onnxruntime）。
                {models.data?.note_extraction.reason ? ` ${models.data.note_extraction.reason}` : ""}
              </p>
            )}
            <div className="mt-2 flex flex-wrap gap-2">
              <Badge tone={modelReady ? "success" : "danger"}>
                音符识别：{modelReady ? `${models.data?.note_extraction.name}` : "不可用（REQUIRES_MODEL）"}
              </Badge>
              <Badge tone="info">
                信号分析：{models.data?.signal_analysis.method ?? "librosa"}
              </Badge>
              <Badge tone="success">MIDI 导入：可用且生成音符</Badge>
              {models.data?.note_extraction.capabilities.polyphonic && (
                <Badge tone="info">复音识别：支持</Badge>
              )}
            </div>
          </div>
        </div>
      </section>

      <div className="grid gap-4 lg:grid-cols-2">
        {/* path 1: MIDI */}
        <section className="panel p-4">
          <div className="flex items-center gap-2">
            <FileMusic size={15} className="text-accent" />
            <h3 className="text-sm font-semibold text-white">导入 MIDI（可生成音符）</h3>
          </div>
          <p className="mt-1 text-[11px] leading-relaxed text-studio-500">
            解析 .mid / .midi 的音符起点、时值、音高、力度、轨道、通道、拍号与速度，生成 MusicDocument。
          </p>
          <input
            ref={midiInput}
            type="file"
            accept=".mid,.midi"
            className="hidden"
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) void handleMidi(file);
              event.target.value = "";
            }}
          />
          <button
            className="btn-primary mt-3 w-full"
            onClick={() => midiInput.current?.click()}
            disabled={importMidi.isPending}
          >
            <Upload size={14} /> {importMidi.isPending ? "解析并生成谱面…" : "选择 MIDI 文件"}
          </button>
        </section>

        {/* path 2: audio transcription */}
        <section className="panel p-4">
          <div className="flex items-center gap-2">
            <AudioLines size={15} className="text-key-cyan" />
            <h3 className="text-sm font-semibold text-white">
              {modelReady ? "上传音频，AI 识别成谱" : "上传音频（仅信号分析）"}
            </h3>
          </div>
          <p className="mt-1 text-[11px] leading-relaxed text-studio-500">
            {modelReady
              ? "支持 MP3 / WAV / FLAC / M4A / AAC / OGG / OPUS。后端用 FFmpeg 真实解码并校验（不信任扩展名），再用模型识别音高、起止与力度，写入 MusicDocument。"
              : "支持 MP3 / WAV / FLAC / M4A / AAC / OGG / OPUS。未安装模型时只做标准化、节拍估计、起音检测与能量统计，不生成音符。"}
          </p>
          <input
            ref={audioInput}
            type="file"
            accept=".mp3,.wav,.flac,.m4a,.aac,.ogg,.opus"
            className="hidden"
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) void handleAudioUpload(file);
              event.target.value = "";
            }}
          />
          <button
            className="btn-primary mt-3 w-full"
            onClick={() => audioInput.current?.click()}
            disabled={uploadAudio.isPending || createJob.isPending}
          >
            <Gauge size={14} />
            {uploadAudio.isPending
              ? "上传并解码中…"
              : createJob.isPending
                ? "创建识别作业…"
                : modelReady
                  ? "选择音频并开始 AI 扒谱"
                  : "上传音频并创建分析作业"}
          </button>
          <p className="mt-2 text-[10px] text-studio-600">
            单文件 ≤ {capabilities.data?.max_upload_mb ?? "—"} MB · 时长 ≤{" "}
            {Math.round((capabilities.data?.max_duration_seconds ?? 0) / 60) || "—"} 分钟 · 当前曲库{" "}
            {stats.data?.tracks ?? 0} 首 · 分析作业 {stats.data?.transcription_jobs ?? 0} 个
          </p>
        </section>
      </div>

      {message && (
        <p className="rounded-lg border border-studio-700 bg-studio-900 px-4 py-2 text-xs text-studio-300">
          {message}
        </p>
      )}

      {/* eligibility */}
      <section className="panel">
        <div className="panel-header">
          <div>
            <h3 className="text-sm font-semibold text-white">扒谱资格检查</h3>
            <p className="text-[11px] text-studio-500">五项权限独立判断，平台政策优先。</p>
          </div>
          <Badge tone="neutral">{tracks.data?.total ?? 0} 首可选</Badge>
        </div>
        <div className="grid gap-3 p-3 md:grid-cols-[280px_1fr]">
          <select
            className="input h-9"
            value={selectedTrackId ?? ""}
            onChange={(event) => setSelectedTrackId(event.target.value || null)}
          >
            <option value="">选择一首曲目…</option>
            {tracks.data?.items.map((track) => (
              <option key={track.track_id} value={track.track_id}>
                {track.title} — {track.artist} ({track.source_provider})
              </option>
            ))}
          </select>

          {!selectedTrackId && (
            <p className="text-[11px] text-studio-500">选择曲目后显示逐项权限与判定结论。</p>
          )}

          {eligibility.isLoading && <Spinner label="判定中" />}

          {eligibility.data && (
            <div className="space-y-2">
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone={STATUS_TONE[eligibility.data.status]}>
                  {eligibility.data.status} · {STATUS_LABEL[eligibility.data.status]}
                </Badge>
                <span className="text-[11px] text-studio-400">
                  {selectedTrack?.title} · {selectedTrack?.source_provider}
                </span>
                {eligibility.data.status === "ELIGIBLE" ? (
                  <CheckCircle2 size={13} className="text-accent" />
                ) : (
                  <Ban size={13} className="text-key-rose" />
                )}
              </div>
              <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-5">
                {Object.entries(eligibility.data.permissions).map(([key, value]) => (
                  <div
                    key={key}
                    className={clsx(
                      "rounded border px-2 py-1 text-center text-[10px]",
                      value
                        ? "border-accent/20 bg-accent/5 text-accent"
                        : "border-studio-800 text-studio-600",
                    )}
                  >
                    {key.replace(/_/g, " ")}
                    <div className="font-mono">{value ? "允许" : "禁止"}</div>
                  </div>
                ))}
              </div>
              <ul className="space-y-1 text-[11px] leading-relaxed text-studio-400">
                {eligibility.data.reasons.map((reason) => (
                  <li key={reason} className="flex gap-1.5">
                    <span className="text-studio-600">·</span>
                    {reason}
                  </li>
                ))}
              </ul>
              {eligibility.data.ai_allowed && (
                <button
                  className="btn-primary h-8 py-0 text-xs"
                  onClick={async () => {
                    if (!selectedTrackId) return;
                    try {
                      await createJob.mutateAsync({
                        track_id: selectedTrackId,
                        confirm_rights: true,
                      });
                      setMessage("已创建分析作业。注意：本版本不会生成音符。");
                    } catch (error) {
                      setMessage(error instanceof Error ? error.message : "创建作业失败");
                    }
                  }}
                >
                  <Play size={13} /> 创建分析作业
                </button>
              )}
            </div>
          )}
        </div>
      </section>

      {/* jobs */}
      <section className="panel">
        <div className="panel-header">
          <h3 className="text-sm font-semibold text-white">作业记录</h3>
          <Badge tone="neutral">{jobs.data?.total ?? 0}</Badge>
        </div>
        <div className="space-y-2 p-3">
          {jobs.data?.items.length === 0 && (
            <EmptyState title="还没有作业" description="上传音频或从曲库创建分析作业后会出现在这里。" />
          )}
          {jobs.data?.items.map((job) => (
            <JobCard key={job.job_id} job={job} />
          ))}
        </div>
      </section>
    </div>
  );
}

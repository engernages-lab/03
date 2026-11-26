# V1.1-C.2 · 02 实施报告（Implementation Report）

- **日期**：2026-11-26
- **范围**：C.2-02 至 C.2-06（Dockerfile、Railway 配置、模型单例、并发与超时、环境变量与安全、前端配置、上传保护）

---

## 1. 修改文件清单

| 文件 | 类型 | 修改内容 | 原因 | 影响现有功能 |
| --- | --- | --- | --- | --- |
| `backend/Dockerfile` | 改 | `CMD` 改为 `sh -c exec uvicorn ... --port ${PORT:-8000}`；加 `--timeout-graceful-shutdown 25 --proxy-headers`；`HEALTHCHECK` 用 `$PORT` 并探 `/health`；`start-period` 90s；`POCKETSCORE_MODEL_PRELOAD=true` | Railway 注入 `PORT`；优雅退出；预热 | 否 |
| `railway.json`（仓库根，单个文件） | 新增 | `builder: DOCKERFILE` + `dockerfilePath: backend/Dockerfile`；`healthcheckPath: /health`，`healthcheckTimeout: 180`；`restartPolicyType: ON_FAILURE`，`maxRetries 5`；`numReplicas: 1` | Railway 默认找不到 `backend/Dockerfile` | ✔ | 否 |
| `.github/workflows/docker-verify.yml` | 新增 | ubuntu runner 构建镜像 → 注入 `PORT` + staging 变量与卷 → `/health` `/ready` → 真实扒谱 → 拒绝非法上传 → 重启验卷 → `docker stop` 验优雅退出 | 本机无 Docker，用 CI 关门禁 | ✔ | 否（尚未执行，需推送触发） |
| `backend/app/core/config.py` | 改 | 新增 `max_concurrent_inferences`、`inference_queue_timeout_seconds`、`inference_timeout_seconds`、`model_preload`；`max_upload_mb` 200→100；`is_staging` / `requires_hardened_secrets` / `validate_hardened_secrets()`；`settings_customise_sources` + CSV 源 | 并发/超时/体积可配；生产密钥强校验；修复 CORS 崩溃 | 否（新增可选字段） |
| `backend/app/services/audio/model_manager.py` | 新增 | 进程级模型单例：`load()`/`warmup()`/`get()`/`status()`，线程安全，记录加载与预热耗时 | 消除每请求重建模型 | 否 |
| `backend/app/services/audio/inference_limiter.py` | 新增 | 有界并发槽（默认 1）+ 队列等待超时 + 计数统计；超时任务不提前放行 | 并发可控 | 否 |
| `backend/app/services/audio/transcription/inference.py` | 改 | `predict(str(path), model_manager.get(), ...)` | 传实例而非路径 | 否 |
| `backend/app/services/transcription.py` | 改 | 推理包在 `limiter.slot(...)` 中；记录 `inference_seconds`/`queue_wait_seconds`/`model_load_seconds`；`INFERENCE_BUSY`/`INFERENCE_TIMEOUT` 分支 | 并发与超时可观测 | 否 |
| `backend/app/api/v1/transcription.py` | 改 | `INFERENCE_BUSY`→503、`INFERENCE_TIMEOUT`→504 | 明确服务繁忙状态 | 否 |
| `backend/app/core/errors.py` | 改 | 新增 `ServiceBusyError`(503) / `InferenceTimeoutError`(504) | 同上 | 否 |
| `backend/app/main.py` | 改 | 启动校验 `validate_hardened_secrets()`（失败即拒绝启动）；`MODEL_PRELOAD` 时加载 + 预热；根级 `/health`、`/ready` | 生产安全与容器探针 | 否 |
| `backend/app/main.py` | 改 | 根级探针**先于 SPA 兜底注册**（否则 `/health` 返回 index.html） | 实测发现的真 bug | 否 |
| `backend/app/api/v1/health.py` | 改 | 抽出 `readiness_payload()`：DB/存储可写/FFmpeg/MIDI/**模型状态**/推理槽；`/ready` 在必要项失败时 503 | 容器就绪语义 | 否（`/api/v1/health/ready` 兼容） |
| `backend/app/api/v1/audio.py` | 改 | 上传改为 256 KB 分块落盘 + 运行中体积上限 + `Content-Length` 预检；`/probe` 同样分块 | 不再全量入内存 | 否（响应结构不变） |
| `backend/app/services/audio/assets.py` | 改 | 新增 `ingest_audio_from_path()` + `_sha256_file()` + `_finalise_asset()`；保留 `ingest_audio(bytes)` | 流式上传入库 | 否 |
| `backend/.env.example` | 改 | 补齐全部变量（含推理/安全项），标注 staging/production 必填 | 部署文档化 | 否 |
| `frontend/.env.example` | 新增 | `VITE_API_BASE_URL` / `VITE_DEV_API_TARGET` / `VITE_BASE_PATH` 说明 | 前端配置文档化 | 否 |
| `frontend/vite.config.ts` | 改 | `sourcemap: mode !== "production"` | 生产不发布 .map | 否 |
| `frontend/src/lib/api.ts` | 改 | 新增 `API_CONFIG`：`absolute`/`same-origin`/`misconfigured` 三态 + 明确提示文案 | API 缺失不静默 | 否 |
| `frontend/src/components/layout/AppShell.tsx` | 改 | `misconfigured` 时顶部横幅 | 用户可见的配置错误 | 否 |
| `scripts/smoke_deployment.py` | 新增 | 以容器等价语义启动、探活、真实扒谱、SIGTERM、重启验证持久化 | 无 Docker 时的真实验证 | 否 |
| `tests/e2e/staging-smoke.spec.ts` | 新增 | `PSC_STAGING_URL` 存在时对真实远端跑健康/上传/扒谱/拒绝非法扩展名 | 云端冒烟 | 否（无变量则跳过） |

新增测试：`tests/test_model_manager.py`(7)、`tests/test_inference_limiter.py`(8)、
`tests/test_production_config.py`(10)、`tests/test_upload_limits.py`(7)、
`frontend/src/lib/apiConfig.test.ts`(4)。

---

## 2. 实测发现并修复的三个真实缺陷

### 2.1 CORS 环境变量导致进程无法启动（P0）

```text
pydantic_settings.sources.SettingsError: error parsing value for field "cors_origins"
  ← json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)
```

pydantic-settings **2.2.1** 在调用字段校验器之前会对 `List[str]` 做 JSON 解析，
而运维写法是 `a,b`。修复：自定义 `_CsvEnvSource` / `_CsvDotEnvSource` 覆写
`prepare_field_value`，把这 3 个字段原样交给 `_split_csv`（同时仍兼容 JSON 数组写法）。
验证：`POCKETSCORE_CORS_ORIGINS="a,b"` → `['a', 'b']`，无异常。

### 2.2 `/health` 被 SPA 兜底路由劫持（P0）

`@app.get("/{full_path:path}")` 注册在根级探针之前，导致 `/health` 返回 `index.html`
（实测：`json.JSONDecodeError`，因为拿到的是 HTML）。修复：探针在 `include_router` 之后、
SPA 之前注册，并把 `health`/`ready` 加入兜底排除列表。

### 2.3 上传把整个文件读入内存（P1）

改为分块（256 KB）写临时文件，边写边计体积；超限立刻 413 并删除临时目录；
`Content-Length` 声明超限时在读取前直接拒绝。

---

## 3. 模型单例与预热

- `ModelManager.load()` 在锁内只构造一次 `basic_pitch.inference.Model`；
  并发 8 线程同时调用实测只构造 1 个实例（有测试）。
- `warmup()` 用 1 s 静音 WAV 跑一次 `predict`，把 numba JIT 与 ORT 预热从"首个用户请求"
  挪到"进程启动"。
- 实测（staging 模式启动，`MODEL_PRELOAD=true`）：
  **model load 2.663 s，warmup 2.044 s，进程到 `/health` 200 共 9.04 s**。
- 加载失败时不伪造成功：`status=failed` + 明确 error，`get()` 抛错，`/ready` 返回非就绪。

## 4. 并发与超时

| 配置 | 默认值 | 行为 |
| --- | --- | --- |
| `MAX_CONCURRENT_INFERENCES` | 1 | 超出后排队，等待超过 `INFERENCE_QUEUE_TIMEOUT_SECONDS` 返回 503 `INFERENCE_BUSY` |
| `INFERENCE_QUEUE_TIMEOUT_SECONDS` | 30 | 排队上限 |
| `INFERENCE_TIMEOUT_SECONDS` | 300 | 完成但超预算 → 任务 `failed(INFERENCE_TIMEOUT)`，HTTP 504 |

**诚实的限制**：Python 线程中的 ONNX 推理**不可中断**。超时后不会提前释放并发令牌
（否则第二个任务会在第一个仍占用 262 MB 时启动），而是标记失败、等底层调用返回后再释放。
该限制已写入代码注释与报告，未用 `asyncio.wait_for` 假装能杀线程。

## 5. 生产密钥与 CORS

`validate_hardened_secrets()` 在 staging/production 启动时检查：

1. `SESSION_SECRET` 非默认值且 ≥32 字符；
2. `TOKEN_ENCRYPTION_KEY` 必须显式设置（否则容器重建后令牌不可解密）；
3. `CORS_ORIGINS` 不允许 `*`；
4. `ALLOW_PRIVATE_NETWORK_SOURCES` 必须为 false。

任一不满足 → 启动抛 `RuntimeError`，日志逐条列出问题，**不静默降级**。

## 6. 前端

- 生产构建 `sourcemap: false`：实测产物 **0 个 `.map`**（此前发布 1.5 MB）。
- `API_CONFIG.mode === "misconfigured"`（如 `*.github.io` 且无 `VITE_API_BASE_URL`）时，
  顶部显示横幅并说明"上传与扒谱请求会失败"；**没有任何 mock 回退**。

## 7. 未做（明确）

| 项 | 原因 |
| --- | --- |
| Docker 镜像构建 | 本机无 Docker（见 01 报告 §6） |
| Railway 部署 | 未授权 + 无 CLI |
| PostgreSQL 迁移 | 属于 C.3，本阶段禁止 |
| 用户认证 / 限流 | 属于 C.5 |
| 优雅退出实测 | Windows 无法向无控制台子进程发送 SIGTERM（见 03 报告） |

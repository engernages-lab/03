# PocketScore AI V1.1-C.2 · Railway Production Deployment & Backend Launch Report

---

## 1. 阶段信息

| 项 | 值 |
| --- | --- |
| 项目名称 | PocketScore AI |
| 阶段名称 | V1.1-C.2 · Railway Production Deployment & Backend Launch |
| 开发日期 | 2026-11-26 |
| 当前 Git 分支 | `pocketscore-v1.1-b` |
| 开始时 HEAD | `8ae2b28`（C.1 审计报告提交） |
| 完成时 HEAD | 本次提交（见 §12，提交后由 `git log -1` 确认） |
| 是否有未提交修改 | 否（提交后工作区干净） |
| **最终验收结论** | **BLOCKED**（依据见 §13） |

---

## 2. 实际修改文件清单

| 文件 | 修改内容 | 原因 | 新增 | 影响现有功能 |
| --- | --- | --- | --- | --- |
| `backend/Dockerfile` | CMD 读 `$PORT`、`exec`、`--timeout-graceful-shutdown 25`、HEALTHCHECK 用 `$PORT` 探 `/health`、`MODEL_PRELOAD=true` | Railway 端口注入与优雅退出 | 否 | 否 |
| `railway.json`（根） | DOCKERFILE builder + `backend/Dockerfile`、healthcheck `/health` 180s、ON_FAILURE 重试 5 次、单副本 | Railway 默认找不到 Dockerfile | ✔ | 否 |
| `backend/app/core/config.py` | 新增推理并发/队列超时/推理超时/预热开关；上传上限 200→100；`is_staging`、`validate_hardened_secrets()`；自定义 CSV 环境源 | 生产安全与容量可配；修复 CORS 崩溃 | 否 | 否（新增可选字段） |
| `backend/app/services/audio/model_manager.py` | 模型单例（load/warmup/get/status，线程安全，计时） | 消除每请求重建模型 | ✔ | 否 |
| `backend/app/services/audio/inference_limiter.py` | 有界并发 + 队列等待超时 + 统计 | 并发可控 | ✔ | 否 |
| `backend/app/services/audio/transcription/inference.py` | `predict(path, model_manager.get(), ...)` | 传实例 | 否 | 否 |
| `backend/app/services/transcription.py` | 推理包在限流槽中；记录 queue/inference/model-load 耗时；BUSY/TIMEOUT 分支 | 容量问题可诊断 | 否 | 否（作业多 3 个分析字段） |
| `backend/app/api/v1/transcription.py` | BUSY→503、TIMEOUT→504 | 明确的繁忙状态 | 否 | 否 |
| `backend/app/core/errors.py` | `ServiceBusyError`(503)、`InferenceTimeoutError`(504) | 同上 | 否 | 否 |
| `backend/app/main.py` | 启动密钥校验（失败拒绝启动）、模型预热、根级 `/health` `/ready`、探针先于 SPA 注册 | 生产安全 + 容器探针 | 否 | 否 |
| `backend/app/api/v1/health.py` | `readiness_payload()`：DB/存储/FFmpeg/MIDI/模型/推理槽；`/ready` 失败 503 | 就绪语义 | 否 | 否（旧路径保留） |
| `backend/app/api/v1/audio.py` | 上传分块落盘 + 运行中体积上限 + Content-Length 预检；`/probe` 同改 | 不再全量入内存 | 否 | 否（响应结构不变） |
| `backend/app/services/audio/assets.py` | `ingest_audio_from_path()`、`_sha256_file()`、`_finalise_asset()`；保留 bytes 入口 | 流式入库 | 否 | 否 |
| `backend/.env.example` | 补齐全部变量与必填标记 | 部署文档化 | 否 | 否 |
| `frontend/.env.example` | 新增前端变量说明 | 同上 | ✔ | 否 |
| `frontend/vite.config.ts` | `sourcemap: mode !== "production"` | 生产不发布源码 | 否 | 否 |
| `frontend/src/lib/api.ts` | `API_CONFIG` 三态 + 明确提示 | API 缺失不静默 | 否 | 否 |
| `frontend/src/components/layout/AppShell.tsx` | 配置错误横幅 | 用户可见 | 否 | 否 |
| `scripts/smoke_deployment.py` | 容器语义冒烟脚本 | 无 Docker 时的真实验证 | ✔ | 否 |
| `tests/e2e/staging-smoke.spec.ts` | 云端冒烟（需 `PSC_STAGING_URL`） | 部署后一键验收 | ✔ | 否（无变量则 skip） |
| `backend/tests/test_model_manager.py` | 7 项 | 单例契约 | ✔ | — |
| `backend/tests/test_inference_limiter.py` | 8 项 | 并发契约 | ✔ | — |
| `backend/tests/test_production_config.py` | 10 项 | 生产密钥规则 | ✔ | — |
| `backend/tests/test_upload_limits.py` | 7 项 | 上传安全 | ✔ | — |
| `frontend/src/lib/apiConfig.test.ts` | 4 项 | API 配置三态 | ✔ | — |

---

## 3. Docker 部署配置

| 项 | 内容 |
| --- | --- |
| Dockerfile 修改 | CMD → `sh -c exec python -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --timeout-graceful-shutdown 25 --proxy-headers --forwarded-allow-ips='*'` |
| PORT 读取 | 平台注入 `PORT`；无则回退 8000；`exec` 使 uvicorn 成为 PID 1，信号直达 |
| Railway 配置 | `railway.json`：`dockerfilePath=backend/Dockerfile`、`healthcheckPath=/health`、`healthcheckTimeout=180`、`ON_FAILURE` 最多 5 次、`numReplicas=1` |
| 健康检查 | `/health`（轻量，不加载模型）与 `/ready`（DB/存储/FFmpeg/MIDI/模型/推理槽） |
| Volume 路径 | `/data`：`pocketscore.db` + `storage/audio|midi|artwork` |
| 优雅退出 | `--timeout-graceful-shutdown 25`；**容器内未实测**（见 §7） |

---

## 4. AI 模型优化

| 项 | 结果 |
| --- | --- |
| 重复初始化问题 | ✅ 已解决。上游 `run_inference` 在收到路径时才重建 `Model`；现改为传 `ModelManager` 的单例实例 |
| 单例实现 | `ModelManager` + `threading.Lock`；8 线程并发调用实测只构造 1 个实例（`test_concurrent_load_only_builds_one_model`） |
| 预热 | `MODEL_PRELOAD=true` 时启动加载并跑 1 s 静音推理 |
| 初始化耗时（实测） | 模型加载 **2.663 s**，预热 **2.044 s**；进程到 `/health` 200 共 **9.04 s** |
| 并发限制 | `MAX_CONCURRENT_INFERENCES=1`；超出排队，超 `INFERENCE_QUEUE_TIMEOUT_SECONDS=30` → 503 `INFERENCE_BUSY` |
| 超时处理 | `INFERENCE_TIMEOUT_SECONDS=300`；超预算任务标记 `failed(INFERENCE_TIMEOUT)`，HTTP 504 |
| 已知限制 | ONNX 推理线程**不可中断**；超时后不提前释放令牌（否则内存翻倍），等底层返回再释放。已写入代码注释 |
| 失败处理 | 模型加载失败 → `status=failed` + 明确 error；`get()` 抛错；`/ready` 非就绪；**不产生假音符** |

---

## 5. 环境变量

| 变量 | 开发 | Staging | 生产 | 敏感 |
| --- | --- | --- | --- | --- |
| `POCKETSCORE_ENVIRONMENT` | `development` | `staging` | `production` | 否 |
| `POCKETSCORE_DEBUG` | `true` | `false` | `false` | 否 |
| `POCKETSCORE_LOG_JSON` | `false` | `true` | `true` | 否 |
| `POCKETSCORE_SESSION_SECRET` | 可默认 | **必填 ≥32 字符** | **必填** | ✅ 已脱敏 |
| `POCKETSCORE_TOKEN_ENCRYPTION_KEY` | 可缺省 | **必填** | **必填** | ✅ 已脱敏 |
| `POCKETSCORE_CORS_ORIGINS` | localhost | `https://engernages-lab.github.io` | 同左 | 否 |
| `POCKETSCORE_ALLOW_PRIVATE_NETWORK_SOURCES` | `true` | **`false`** | **`false`** | 否 |
| `POCKETSCORE_DATABASE_URL` | `sqlite:///./data/...` | `sqlite:////data/pocketscore.db` | 同左 | 可能含口令 |
| `POCKETSCORE_STORAGE_DIR` | `./data/storage` | `/data/storage` | 同左 | 否 |
| `POCKETSCORE_MAX_UPLOAD_MB` | 100 | 50（建议） | 50 | 否 |
| `POCKETSCORE_MAX_CONCURRENT_INFERENCES` | 1 | 1 | 1 | 否 |
| `POCKETSCORE_INFERENCE_TIMEOUT_SECONDS` | 300 | 300 | 300 | 否 |
| `POCKETSCORE_MODEL_PRELOAD` | false | true | true | 否 |
| `PORT` | — | 平台注入 | 平台注入 | 否 |
| `VITE_API_BASE_URL`（仓库变量） | 空（走代理） | Railway 域名 | 同左 | 否 |

**生产限制（启动时强制）**：4 项任一不满足 → 进程拒绝启动并逐条打印原因；
不会静默回退到 `change-me-in-production`。本报告不含任何真实密钥值。

---

## 6. 前后端连接

| 项 | 状态 |
| --- | --- |
| 前端 API 地址 | 唯一入口 `VITE_API_BASE_URL`（`src/lib/api.ts`），三态 `API_CONFIG` |
| Railway API 地址 | **不存在**（未部署） |
| CORS | 精确来源；`*` 在 staging/production 被拒绝启动 |
| API 连接 | 本地等价环境验证（同源）；云端未验证 |
| 音频上传 | ✅ 本地真实上传（`melody.wav` → 201） |
| 项目保存 | ✅ 文档写入 + 重启后读取（4 事件） |
| Mock 数据 | ❌ 全链路无 mock；`API_CONFIG` 缺失时只提示，不伪造数据 |

---

## 7. Docker 验证报告

**NOT EXECUTED** —— 本机无 Docker / WSL / podman（`03-docker-validation.md` §1）。

替代验证（容器等价语义，真实进程 + 独立卷目录）：

| 项 | 结果 |
| --- | --- |
| 启动（含预热） | 9.04 s |
| `/health` | 200 |
| `/ready` | 200，`ready:true`，model `ready`（2.663 s / warmup 2.044 s） |
| 数据库 | 4 096 B，重启后可读 |
| 存储目录可写 | ✅ `storage/audio/f4/<sha256>.wav` |
| 真实识别 | ✅ 作业 `completed`，4 音符，2.61 s |
| 重启持久化 | ✅ 文档 200 / 4 事件 / 1 资产 |
| 镜像大小 | ⛔ 未知（未构建） |
| 优雅退出 | ⚠️ 未验证（Windows SIGTERM = TerminateProcess） |

---

## 8. Railway 云端部署报告

**Railway Deployment: NOT EXECUTED**

- 理由：未授权 + 无 Railway CLI + Docker 本地验证未通过（阶段门禁第 8–10 步）。
- 已完成：`railway.json`、镜像启动命令、变量清单、卷布局、Staging 访问限制方案（三选一，推荐"暂不公开"）。
- 未编造任何部署 URL、日志或测试结果。

---

## 9. 自动化测试结果

| 项 | 通过 | 失败 | 跳过 |
| --- | --- | --- | --- |
| 后端 pytest | **327** | 0 | 0 |
| 前端 vitest | **103**（12 文件） | 0 | 0 |
| E2E Playwright | **15** | 0 | **4**（3 staging-smoke 无 URL + 1 pages-artifact） |
| TypeScript `tsc --noEmit` | exit 0 | — | — |
| Python `ruff check app tests` | All checks passed | — | — |
| 前端生产构建 | 成功 3.77 s，JS 390.85 kB（gzip 119.81），**0 个 .map** | — | — |
| Docker 验证 | **未执行** | — | — |

新增测试 36 项（后端 32 + 前端 4）；既有 296 项全部保持通过，未修改任何既有断言。

**本轮实测发现并修复的 3 个真 bug**（均由测试/冒烟暴露，非推测）：
CORS 逗号分隔导致启动崩溃、`/health` 被 SPA 兜底劫持、上传全量入内存。

---

## 10. 性能数据（实测）

| 指标 | 值 | 说明 |
| --- | --- | --- |
| 镜像大小 | ⛔ 未测 | 需 Docker |
| 容器启动时间 | 9.04 s（进程等价） | 含模型加载 2.663 s + 预热 2.044 s + 导入 |
| 模型初始化 | 2.663 s | `Model(ICASSP_2022_MODEL_PATH)` |
| 预热 | 2.044 s | 1 s 静音推理（numba JIT 已在此消化） |
| 首次推理（预热后首个真实作业） | 2.61 s | `melody.wav`（≈1.6 s 音频），含解码 + 后处理 |
| 推理峰值内存 | 262 MB（120 s 音频，C.1 实测） | 本次未重建容器内存采样 |
| CPU 使用率 | 未采集（无 psutil / 容器指标） | 单核推理，未测占用率百分比 |
| 并发请求 | 容量 1，超出返回 503（单测覆盖） | 未做云端压测 |
| 容器重启 | 数据存活 ✅ | 进程等价 |

---

## 11. 风险与未解决的问题

| # | 问题 | 等级 | 说明 |
| --- | --- | --- | --- |
| 1 | Docker 镜像未构建 | **P0（验证缺失）** | 无 Docker 运行时；镜像可能因 `frontend/dist` 缺失或系统库差异失败 |
| 2 | Railway 未部署 | P0（未授权） | 无公网地址，云端链路未验证 |
| 3 | 无认证 / 无用户隔离 | **P1** | 任何人都能读写所有项目；不得公开 |
| 4 | 无限流 | P1 | 仅靠并发槽与体积上限缓解 |
| 5 | 优雅退出未验证 | P2 | Windows 无法模拟；Linux 容器待测 |
| 6 | 推理不可中断 | P2 | 超时后仍占用线程与内存直到返回 |
| 7 | SQLite 单实例、无备份 | P1 | 卷丢失即数据丢失（C.3） |
| 8 | 未做跨浏览器验证 | P3 | 仅 Chromium |
| 9 | `frontend/dist` 必须在构建前生成 | P2 | 否则 Dockerfile `COPY` 失败（已写入 04 报告步骤 1） |
| 10 | 容器 Python 3.11 vs 本地 3.9 | P2 | 依赖解析结果可能不同（basic-pitch 会拉 TF 而非 onnxruntime） |

---

## 12. Git 状态

| 项 | 值 |
| --- | --- |
| 当前分支 | `pocketscore-v1.1-b` |
| 新增提交 | 1 个（本报告与代码、测试、脚本） |
| 是否 Commit | ✅ 本地提交 |
| 是否 Push | ❌ 未推送 |
| 是否修改 origin/main | ❌ 否（`origin/main` 仍为 `9e7cd41`） |
| 是否部署 | ❌ 否 |
| 冻结基线 | `5315e3d` 未改动 |

---

## 13. 最终结论

### BLOCKED

依据（对应提示词 §10.3 的 BLOCKED 条件）：

1. **Docker 无法构建**——本机无 Docker Engine / CLI / WSL，镜像构建与容器启动**一次都没有执行**。
   按提示词"不允许只修改配置文件而不执行 Docker 构建"，本阶段无法判 PASS。
2. **云端部署未执行**——即使忽略第 1 点，Railway 也无授权、无 CLI，无法产生任何云端证据。

**不判 CONDITIONAL PASS 的理由**：CONDITIONAL 的适用前提是"Docker 本地验证通过，
但 Railway 尚未获得部署授权"。本阶段连 Docker 验证都没有，因而达不到 CONDITIONAL 的门槛。

**已经真实完成且可复核的部分**（不是"计划"）：

- 部署配置全部就绪（Dockerfile 端口注入、`railway.json`、变量清单、卷布局）；
- 三个会导致"部署后起不来"的真 bug 被修复（CORS 启动崩溃、`/health` 被 SPA 劫持、上传全量入内存）；
- 模型单例 + 预热 + 并发槽 + 超时全部落地，并在 staging 配置下实测跑通
  "上传 → 真实 Basic Pitch 扒谱 → 4 个音符 → 谱面读取 → 重启后数据仍在"；
- 327 后端 / 103 前端 / 15 E2E 全绿，无回归。

**缺的只有一件**：一个能跑 Docker 的环境（或在 CI 上跑构建）。

---

## 14. 下一阶段建议

**C.2 收尾（建议先做，1 次提交即可闭环）**

1. 在 GitHub Actions（ubuntu-latest 自带 Docker）新增 `.github/workflows/docker-verify.yml`：
   `npm run build` → `docker build -f backend/Dockerfile` → `docker run` 注入 `PORT` +
   staging 变量 + 临时卷 → 跑 `/health` `/ready` → 上传 `tests/fixtures/melody.wav` →
   断言 `events_produced > 0` → `docker stop` 验证优雅退出日志。**该 workflow 需推送后才能运行，
   因此需要一次明确的 push 授权。**
2. 或用本机安装 Docker Desktop 后执行 `03-docker-validation.md` §5 的四步。

**C.3（数据可靠性，按依赖顺序）**

1. `psycopg[binary]` + `alembic upgrade head` 在空 PG 上跑通；
2. 存储适配器抽象（本地 / S3 兼容），DB 只存 key；
3. SQLite→PG 一次性迁移脚本 + 行数与校验和比对；
4. 每日备份 + 恢复演练（10 分钟内恢复）；
5. 迁移完成后，Railway 增加 PostgreSQL 服务，Web 服务改连 PG。

**不建议现在做**：Redis / 独立 AI Worker（无认证、无并发压力，属过度设计）、
公开部署（无认证，等于把 AI 算力和全部数据开放给互联网）。

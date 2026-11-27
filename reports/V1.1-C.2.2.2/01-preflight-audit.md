# V1.1-C.2.2.2 · 01 部署前审计（Phase 1）

- **日期**：2026-11-27
- **阶段**：Railway Post-Fix Regression & Production Readiness Gate
- **性质**：只读审计，未修改代码

---

## 1. Git 状态

```text
分支: pocketscore-v1.1-b
HEAD: b1d3ee1b3bf27ae46b4873b54d98c12b9c09ebd4
工作区: 干净（无修改、无未跟踪）
远程: origin git@github.com:engernages-lab/03.git
```

最近提交：

```text
b1d3ee1 docs(V1.1-C.2.2.1): record the post-audit commits in the git audit
bda2cf1 docs(V1.1-C.2.2.1): cloud acceptance PASS with real Railway evidence
4ec2b7c fix(health): readiness must report the gate and actually check SQLite
7e08dfa fix(spa): actually serve the bundled frontend in the container
f31655a fix(docker): drop the VOLUME instruction so Railway accepts the Dockerfile
```

C.2.2.1 五项修复的提交均在祖先链上（`08e55b7` / `f31655a` / `7e08dfa` / `4ec2b7c`）。
**哈希只是线索**，逐项代码核对见 §2。

`origin/main` = `9e7cd41`（V1.0 基线，未合并任何 V1.1 提交）。

## 2. 五项修复的代码核对

| 编号 | 修复 | 代码证据（`backend/Dockerfile`） | 状态 |
| --- | --- | --- | --- |
| F1 | 镜像内构建前端 | L11 `FROM node:20-slim AS frontend`、L17 `RUN npm ci`、L26 `RUN npm run build && test -f dist/index.html`、L65 `COPY --from=frontend /web/dist ./frontend/dist` | ✅ 代码存在 |
| F2 | 基路径 `/` | L24 `ARG VITE_BASE_PATH=/`、L25 `ENV VITE_BASE_PATH=${VITE_BASE_PATH}` | ✅ 代码存在 |
| F3 | 删除 `VOLUME` | 全文无 `VOLUME` 指令（仅 L70-73 注释说明为何删除） | ✅ 代码存在 |
| F4 | SPA 托管 | `config.py` `frontend_dist_path` 三级解析 + `main.py` 在 `dist` 存在时挂载 `/assets` 与 catch-all | ✅ 代码存在 |
| F5 | `/ready` 完整 | `main.py` `/ready` 用 `session_scope()` 传 session；`health.py` 增加 `checks["access_gate"]` | ✅ 代码存在 |

> 代码存在 ≠ 行为正确。F1–F5 的**真实行为证据**见 02/04/05 号报告。

## 3. Dockerfile / 配置审计

| 检查项 | 结果 |
| --- | --- |
| 多阶段前端构建 | ✅ node:20-slim + python:3.11-slim |
| 构建期 `npm ci` / `npm run build` | ✅ |
| `COPY --from=frontend` | ✅ |
| 是否依赖本地 `frontend/dist` | ❌ 不依赖（`.dockerignore` 已排除该目录） |
| `VOLUME` 指令 | ✅ 已删除 |
| `/data/storage` 创建 + 可写 | ✅ `RUN mkdir -p /data/storage && chmod 0777 /data` |
| `POCKETSCORE_FRONTEND_DIST` | ✅ 镜像内 `ENV ...=/app/frontend/dist` |
| `$PORT` 注入 | ✅ `CMD ... --port "${PORT:-8000}"`（shell 展开，非 Settings） |
| HEALTHCHECK | ✅ 指向 `/health` |
| `railway.json` | builder=DOCKERFILE，`dockerfilePath=backend/Dockerfile`，healthcheck `/health`，180 s |

其它文件核对：

- `.dockerignore`：排除 `frontend/dist`、`node_modules`、`.git`、`.env*`、缓存、`tests` 等。
- `frontend/vite.config.ts`：`base = process.env.VITE_BASE_PATH ?? "/"`（可注入）。

## 4. 环境变量审计（只记录名称与状态）

Railway `staging` 环境共有 **15** 个 `POCKETSCORE_` 变量：

| 变量 | 状态 |
| --- | --- |
| POCKETSCORE_ENVIRONMENT | configured（`staging`） |
| POCKETSCORE_SESSION_SECRET | configured |
| POCKETSCORE_TOKEN_ENCRYPTION_KEY | configured |
| POCKETSCORE_ACCESS_GATE_TOKEN | configured |
| POCKETSCORE_ACCESS_GATE_MODE | configured（`token`） |
| POCKETSCORE_CORS_ORIGINS | configured（`https://engernages-lab.github.io`） |
| POCKETSCORE_ALLOW_PRIVATE_NETWORK_SOURCES | configured（`false`） |
| POCKETSCORE_DATABASE_URL | configured（`sqlite:////data/pocketscore.db`，四斜杠绝对路径） |
| POCKETSCORE_STORAGE_DIR | configured（`/data/storage`） |
| POCKETSCORE_MODEL_PRELOAD | configured（`true`） |
| POCKETSCORE_MAX_UPLOAD_MB | configured（`50`） |
| POCKETSCORE_MAX_CONCURRENT_INFERENCES | configured（`1`） |
| POCKETSCORE_INFERENCE_TIMEOUT_SECONDS | configured（`300`） |
| POCKETSCORE_DEBUG | configured（`false`） |
| POCKETSCORE_LOG_JSON | configured（`true`） |
| POCKETSCORE_FRONTEND_DIST | **由镜像 ENV 提供**，不在 Railway 变量中 |
| PORT | 由 Railway 平台注入（非 Settings 前缀变量） |

平台注入变量（Railway 自带）：`RAILWAY_ENVIRONMENT_NAME=staging`、
`RAILWAY_VOLUME_MOUNT_PATH=/data`、`RAILWAY_PUBLIC_DOMAIN` 等。

**未输出任何密钥值。** 本报告只记录"已配置"。

## 5. Railway 目标确认

```text
$ railway status --json
project: pocketscore-ai
services: ['pocketscore-api']
workspace: Engernages's Projects

$ railway environment list --json
      production 29acdce7-7a32-4f99-b2bf-1e18997ad5a3
LINKED staging   72f62640-3e69-46c7-adb5-81c4fa50a4a1
```

| 项 | 值 |
| --- | --- |
| Project | `pocketscore-ai` |
| Environment | **staging（已 link）**；production 存在但无服务 |
| Service | `pocketscore-api` |
| 当前 Deployment | `052a194e-96eb-4cea-a3a1-c4df43c026cc`（SUCCESS） |
| 域名 | `https://pocketscore-api-staging.up.railway.app` |
| Volume | `pocketscore-api-volume` → `/data` |

## 6. 音频格式支持核对（MP3 必测项）

```python
# app/services/audio/probe.py:27
SUPPORTED_EXTENSIONS = {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".opus"}
```

`app/services/audio/assets.py` 对 `.mp3` 有独立分支（时长探测）。→ MP3 在支持列表内。

MP3 测试素材：由 `tests/fixtures/melody.wav` 用镜像同源 FFmpeg（`imageio-ffmpeg` 4.2.2）
转码生成，**不是改扩展名**：

```text
ffmpeg -i melody.wav -codec:a libmp3lame -q:a 2 melody.mp3
Duration: 00:00:01.85  Stream: mp3, 22050 Hz, mono, 48 kb/s
文件大小: 11 385 字节
```

## 7. 授权与边界

| 项 | 状态 |
| --- | --- |
| 用户是否授权部署 Staging | ✅ 本阶段提示词即执行授权，且明确"只允许现有 Staging" |
| 是否触碰 Production | ❌ 否 |
| 是否删除 Volume | ❌ 否 |
| 是否清空数据库 | ❌ 否 |
| 是否修改 main | ❌ 否 |

## 8. 结论

代码与配置满足阶段要求，可以进入 Phase 2（干净上下文构建）与 Phase 3（部署验证）。

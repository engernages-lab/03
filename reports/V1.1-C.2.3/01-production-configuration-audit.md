# PocketScore AI V1.1-C.2.3.1 · Production Configuration Audit Report

> **结论：BLOCKED**
> 原因：**Production 环境尚未配置** —— 无服务实例、无环境变量、无 Volume、无域名、无部署记录。
> 因此"Production 配置完整性"这一审计对象不存在可审计的证据，只能确认其**缺失**并列出上线阻塞项。
> 关键配置项（Secrets 差异、CORS、数据库隔离、Volume 隔离）在 Production 侧一律为 **NOT CONFIGURED**，
> 按本阶段规则不得当作通过，也不能用 Staging 的配置推断 Production。

---

## 1. 项目与审计信息

| 项 | 值 |
| --- | --- |
| 项目 | PocketScore AI |
| 版本 / 阶段 | V1.1 / C.2.3.1 · Production Configuration Audit |
| 审计类型 | Railway Production + Staging **只读**审计 |
| 审计时间 | 2026-11-28（Asia/Shanghai） |
| Railway 账号 | `Engernages`（已登录，可读） |
| Project | `pocketscore-ai`（`286a8f6c-86ff-45f0-97e2-28ba955799d4`） |
| 分支 / HEAD | `pocketscore-v1.1-b` / `ef6a18df717a9c1f29a130536c8c06442b81a3e1` |
| 工作区 | 干净（0 修改、0 未跟踪） |
| 远程 | `origin/pocketscore-v1.1-b` = `a94dfb9`；`origin/main` = `9e7cd41` |

## 2. 审计方法

| 来源 | 用途 |
| --- | --- |
| `railway status/environment/volume/domain/deployment list --json` | 资源元数据（只读命令） |
| `railway variables --json` → **进程内分析** | 变量名、长度、格式、跨环境比较（值不落终端，原始 dump 用完即删） |
| `GET /health`、`GET /ready` | 线上只读探针 |
| 仓库源码 / 配置 | 认证、隔离、SSRF、上传、限流 |

## 3. Railway 资源结构

### 3.1 Project / Environment

| 项 | 值 |
| --- | --- |
| Project | `pocketscore-ai` |
| Environment | `production`（`29acdce7-7a32-4f99-b2bf-1e18997ad5a3`）、`staging`（`72f62640-3e69-46c7-adb5-81c4fa50a4a1`） |
| 同属一个 Project | ✅ 是（共用服务定义与卷命名空间） |
| 当前 link | `staging` |

### 3.2 Service

| 项 | Staging | Production |
| --- | --- | --- |
| Service 名称 | `pocketscore-api` | 同一定义（项目级唯一服务） |
| Service ID | `28d3b430-6b62-4492-b49a-1f29ef2026c2` | 同 |
| Source 类型 | **CLI 上传**（`railway up`），无 GitHub 仓库绑定 | 未部署 |
| 自动部署 | ❌ 无（未连接 repo，push 不会自动部署） | ❌ 无 |
| Root Directory | 仓库根（`None` = 根） | — |
| Builder | `DOCKERFILE` | — |
| Dockerfile | `backend/Dockerfile` | — |
| Healthcheck | `/health` | — |
| 最近部署 | `d1179a20-5913-4d11-914d-b927e2eb6f25`（SUCCESS，2026-11-27T12:12Z） | **无** |

依据：`railway deployment list` 的 `meta` 含 `cliCaller=agent_unknown:node`、`cliAgentSessionId`、
`reason=redeploy`，且无 `repo`/`branch`/`commitHash` 字段 → 部署来自 CLI 上传快照，**不是 Git 集成**。

### 3.3 域名

| 项 | Staging | Production |
| --- | --- | --- |
| Railway 域名 | `pocketscore-api-staging.up.railway.app`（`syncStatus: ACTIVE`） | **无**（`domains: []`） |
| 自定义域名 | 无 | 无 |
| HTTPS | ✅ Railway 默认 TLS（HTTP 探针 200） | 不适用 |

`production` 的域名列表为空 → `NOT CONFIGURED`。
前端正式域名仍为 GitHub Pages `https://engernages-lab.github.io`（见 CORS 配置）。

### 3.4 Volume

| 项 | Staging | Production |
| --- | --- | --- |
| Volume | `pocketscore-api-volume`（`a578a81a-…`） | **无**（`volumes: []`） |
| 挂载路径 | `/data` | — |
| 状态 | `Ready` | — |
| 容量 / 已用 | 500 MB / **40.2 MB** | — |
| 是否跨环境共享 | ❌ 否（仅绑定 staging 的 `pocketscore-api`） | — |

**同卷风险：VERIFIED 无** —— Production 侧不存在任何 Volume，不存在"两环境共用一块盘"的情况。

## 4. 环境变量与 Secrets

### 4.1 Staging（15 个 `POCKETSCORE_*`，全部存在）

| 变量 | 状态 | 元数据（不含值） |
| --- | --- | --- |
| `POCKETSCORE_ENVIRONMENT` | ✅ | `staging` |
| `POCKETSCORE_DEBUG` | ✅ | `false` |
| `POCKETSCORE_LOG_JSON` | ✅ | `true` |
| `POCKETSCORE_SESSION_SECRET` | ✅ SECRET | len=96，非占位值，≥32 ✅ |
| `POCKETSCORE_TOKEN_ENCRYPTION_KEY` | ✅ SECRET | len=44，Fernet 格式校验 ✅，非占位值 |
| `POCKETSCORE_ACCESS_GATE_TOKEN` | ✅ SECRET | len=48，非占位值，≥16 ✅ |
| `POCKETSCORE_ACCESS_GATE_MODE` | ✅ | `token` |
| `POCKETSCORE_CORS_ORIGINS` | ✅ | `https://engernages-lab.github.io`（无通配符、无 localhost、无 http） |
| `POCKETSCORE_ALLOW_PRIVATE_NETWORK_SOURCES` | ✅ | `false` |
| `POCKETSCORE_DATABASE_URL` | ✅ | `sqlite`，路径**绝对**，文件名 `pocketscore.db` |
| `POCKETSCORE_STORAGE_DIR` | ✅ | `/data/storage` |
| `POCKETSCORE_MODEL_PRELOAD` | ✅ | `true` |
| `POCKETSCORE_MAX_UPLOAD_MB` | ✅ | `50` |
| `POCKETSCORE_MAX_CONCURRENT_INFERENCES` | ✅ | `1` |
| `POCKETSCORE_INFERENCE_TIMEOUT_SECONDS` | ✅ | `300` |

平台注入（`RAILWAY_*`）14 个：`RAILWAY_ENVIRONMENT_NAME`、`RAILWAY_VOLUME_MOUNT_PATH=/data`、
`RAILWAY_PUBLIC_DOMAIN` 等。

### 4.2 Production（**0** 个 `POCKETSCORE_*`）

```text
pocketscore vars: 0 | platform vars: 7   → NOT CONFIGURED
```

平台变量存在（Railway 自动注入），但**项目自身配置一个都没有**。
按规则：不得把 Staging 的值推断为 Production 的值。

### 4.3 双环境 Secret 差异

| 检查项 | 结果 |
| --- | --- |
| Session Secret 是否相同 | **NOT VERIFIABLE**（Production 无该变量） |
| Token Encryption Key 是否相同 | **NOT VERIFIABLE** |
| Access Gate Token 是否相同 | **NOT VERIFIABLE** |

比较方法：两环境各取长度与值在**进程内**比较，未输出任何值、哈希或截断串。
Production 无变量 → 无法比较，标记 NOT VERIFIABLE 而非 PASS。

## 5. Secrets 安全检查结论

| 检查 | Staging | Production |
| --- | --- | --- |
| 是否存在占位符（`change-me-in-production`） | ❌ 无 | 不适用（无变量） |
| 长度是否达标 | ✅ Session 96 / Gate 48 | — |
| Fernet 格式 | ✅ 通过 `cryptography.Fernet` 校验 | — |
| 是否与其他 Secret 复用同值 | ✅ 未发现（长度互不相同且格式互斥） | — |
| 是否已泄露到仓库/前端 | ✅ 无（历史扫描与 bundle 扫描均干净） | — |

> 格式校验 ≠ 证明能解密既有数据。本阶段未做任何加解密调用。

## 6. Volume 与数据路径

| 数据类型 | 路径 | 持久化 | 依据 |
| --- | --- | --- | --- |
| SQLite 数据库 | `/data/pocketscore.db` | ✅ Volume | `POCKETSCORE_DATABASE_URL` + `RAILWAY_VOLUME_MOUNT_PATH=/data` |
| 音频存储 | `/data/storage/audio/…` | ✅ Volume | `POCKETSCORE_STORAGE_DIR` |
| 导出/临时 | 容器内 `/tmp`、`tempfile.mkdtemp` | ❌ 临时（设计如此） | `app/api/v1/audio.py` 上传临时目录 |
| 模型文件 | 镜像内 site-packages（`nmp.onnx`） | 只读，可重建 | Dockerfile |
| Production | **无任何持久化路径** | ⛔ 无 Volume | `volumes: []` |

风险判断：Staging 不会把业务数据写进容器临时层（数据库与存储都在 `/data`）；
但 **Production 目前根本没有 Volume**，一旦按现状部署，重启即丢失全部数据。

## 7. Access Gate 审计

| 检查 | 结果 | 依据 |
| --- | --- | --- |
| 是否启用 | ✅ `mode=token`、`enabled=true` | `/ready.checks.access_gate`（线上 200 响应） |
| Token 是否配置 | ✅ `token_configured=true` | 同上 |
| `/health` `/ready` 放行 | ✅ 200（匿名） | 线上 HTTP 探针 |
| SPA 首页受保护 | ✅ 匿名 401 | CI 步骤 20 断言 + 线上 curl 历史证据 |
| JS/CSS 受保护 | ✅ 匿名 401 | CI 步骤 20 |
| API 受保护 | ✅ 匿名 401 | CI 步骤 19 |
| OPTIONS 预检 | ✅ 放行（CORS 中间件优先） | 代码 + CI |
| 失败限流 | ✅ 20 次/60s → 429（**进程内存**，重启清零、多副本不共享） | `access_gate.py:45` |
| 是否存在绕过入口 | 未发现（门禁为全局中间件，仅豁免两探针与 OPTIONS） | `access_gate.py` |

## 8. 用户认证能力审计

```text
SHARED ACCESS TOKEN IS NOT USER AUTHENTICATION
```

| # | 问题 | 结论 | 证据 |
| --- | --- | --- | --- |
| 1 | 独立用户注册系统 | ❌ 不存在 | 全仓库无 `user` 模型 / 注册路由 |
| 2 | 用户登录系统 | ❌ 不存在 | 无 `login`/`authenticate`/`password_hash`（grep 命中仅 2 处 `WWW-Authenticate` 头） |
| 3 | 用户身份标识 | ❌ 不存在 | 无 `user_id`/`owner_id`/`account_id` 字段 |
| 4 | Session 与用户绑定 | ❌ 不存在 | 无会话表 / Cookie 认证 |
| 5 | 用户权限模型 | ❌ 不存在 | 无 role/scope 定义 |
| 6 | 用户级数据隔离 | ❌ 不存在 | 见 §9 |
| 7 | MusicDocument 关联用户 | ❌ 无 | `app/models/music.py` 无 user 外键 |
| 8 | 音频文件归属 | ❌ 无 | `app/models/audio.py` 无 user 外键 |
| 9 | 乐谱项目归属 | ❌ 无 | 同上 |
| 10 | 用户级访问控制 | ❌ 无 | 无所有权校验依赖 |
| 11 | 管理员机制 | ❌ 无 | — |
| 12 | 防止跨用户访问的服务端校验 | ❌ 无 | 无所有权检查可做 |

**影响**：任何持有共享 Token 的访问者可见/可改**全部**项目。这是多用户生产上线的 P0 阻塞项。

## 9. 用户数据隔离审计

| 模型 | 表 | 用户外键 | 隔离 |
| --- | --- | --- | --- |
| `AudioAsset` | `audio_assets` | ❌ | 无 |
| `TranscriptionJob` | `transcription_jobs` | ❌ | 无 |
| `MusicDocument` | `music_documents` | ❌ | 无 |
| `Track` / `Note` | 文档内嵌 | ❌ | 无 |

`GET /api/v1/documents` 返回全部文档（不按调用者过滤），`GET /api/v1/documents/{id}` 只按 ID 查找，
**没有所有权校验**——因为系统里根本没有"所有者"概念。

## 10. 上传安全审计

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| 最大上传 | `50 MB`（Staging 实际值） | 变量 + 线上 413 实测 |
| Content-Length 预检查 | ✅ `> limit*1.05` 早拒绝 | `audio.py:84-90` |
| 流式限制 | ✅ 256 KB 分块累计，`> limit` 抛 413 | `audio.py:99-111` |
| 扩展名白名单 | ✅ 7 种（mp3/wav/flac/m4a/aac/ogg/opus） | `probe.py:27` |
| MIME/真实类型 | ✅ 解码探测（soundfile/ffmpeg/wave）+ `verify_decodable` | `probe.py` |
| 路径穿越 | ✅ 惰性（内容寻址 `storage/audio/<sha2>/<sha256><ext>`） | 云端实测：穿越文件名返回既有资产 |
| 临时文件清理 | ✅ `tempfile.mkdtemp` + 失败清理 | `audio.py` |
| 内存压力 | ✅ 不整文件读入内存（流式写盘） | `audio.py:80` 注释与实现 |

## 11. SSRF 审计

| 检查 | 结果 | 依据 |
| --- | --- | --- |
| `ALLOW_PRIVATE_NETWORK_SOURCES` | Staging `false`（生产未配置） | 变量 |
| scheme 限制 | ✅ 仅 http/https | `ssrf.py:5` |
| 元数据地址阻断 | ✅ 硬编码拒绝 `169.254.169.254`、`instance-data` | `ssrf.py:26-32` |
| 私有网段 | ✅ 默认阻断，需显式开关 | `ssrf.py:_is_blocked_ip` |
| 重定向 | ✅ 适配器不自动跟随 | `ssrf.py:12` 注释 |
| 仅在服务器地址场景使用 | ✅ 用户提交的只读媒体来源；**音频上传路径不涉及外部 URL** | `sources.py:116` |

## 12. 限流与并发

| 项目 | 现状 | 风险 |
| --- | --- | --- |
| 上传请求限流 | ❌ 无独立限流（仅大小限制） | 可被高频小文件耗尽 I/O |
| 登录限流 | 不适用（无登录） | — |
| 推理并发 | ✅ `capacity=1`，超出返回 503 | 单实例上限 |
| 推理超时 | ✅ 300 s | — |
| 门禁失败限流 | ✅ 20/60s → 429，**内存态** | 重启清零、多副本不共享 |
| 恶意请求耗尽资源 | 部分可（无 IP 级 API 限流） | P1 |

## 13. 数据库架构

| 项 | 值 |
| --- | --- |
| 类型 | SQLite（WAL） |
| 路径 | `/data/pocketscore.db`（绝对，Volume 内） |
| ORM | SQLAlchemy 2.0 + Alembic 迁移 |
| PostgreSQL 支持 | ❌ 驱动与迁移均未准备（`DATABASE_URL` 可换但无 psycopg、无迁移脚本） |
| 用户字段 | ❌ 无 |
| 跨用户查询风险 | ⚠️ 无隔离概念 → 任何凭据持有者可见全量 |
| 单写者限制 | ⚠️ SQLite + 单实例；多副本会锁冲突 |

## 14. Docker / Railway 配置审计

| 检查 | 结果 |
| --- | --- |
| 多阶段构建 | ✅ node:20-slim + python:3.11-slim |
| 前端在镜像内构建 | ✅ `npm ci` + `npm run build` |
| 复制 dist | ✅ `COPY --from=frontend /web/dist` |
| `POCKETSCORE_FRONTEND_DIST` | ✅ `/app/frontend/dist`（镜像 ENV） |
| 监听 Railway `$PORT` | ✅ `${PORT:-8000}` |
| SIGTERM | ✅ `exec` + `--timeout-graceful-shutdown 25` |
| `/health` `/ready` | ✅ |
| Volume 挂载 | `/data`（仅 staging） |
| **`railway.json`** | ⚠️ 唯一配置文件；`.railway/railway.ts` **不存在** |
| **弃用状态** | ⚠️ CLI 明确警告：Config as Code 弃用，**现有文件可用至 2026-12-01**（距今 3 天） |

## 15. 双环境差异矩阵

| 审计项目 | Staging 实际 | Production 实际 | 差异 | 风险 |
| --- | --- | --- | --- | --- |
| Railway Project | `pocketscore-ai` | 同一 Project | 无 | — |
| Environment | `staging`（linked） | `production`（存在，空） | 环境已建、内容为空 | P1 |
| Service | `pocketscore-api` 已部署 | 无部署实例 | **缺失** | P0（上线阻塞） |
| Git 分支 | CLI 上传快照（`a94dfb9` 时期） | 无 | 无来源绑定 | P1 |
| Deployment | `d1179a20` SUCCESS | 无 | **缺失** | P0 |
| Domain | `pocketscore-api-staging.up.railway.app` ACTIVE | 无 | **缺失** | P0 |
| Session Secret | 已配置（96，达标） | 未配置 | **缺失** | P0 |
| Encryption Key | 已配置（Fernet 合法） | 未配置 | **缺失** | P0 |
| Access Gate Token | 已配置（48） | 未配置 | **缺失** | P0 |
| Access Gate Mode | `token` | 未配置 | **缺失** | P0 |
| CORS | 精确 Pages 源 | 未配置 | **缺失** | P0 |
| Database | SQLite `/data/pocketscore.db` | 未配置 | **缺失** | P0 |
| Volume | 500 MB / 已用 40.2 MB / `/data` | **无** | **缺失** | P0（数据丢失风险） |
| Storage Path | `/data/storage` | 未配置 | **缺失** | P0 |
| Upload Limit | 50 MB | 未配置（将回落到代码默认 100） | 不一致风险 | P1 |
| Debug | `false` | 未配置（默认 `true`） | **危险默认** | P0 |
| Private Network | `false` | 未配置（默认 `true`） | **危险默认** | P0 |
| Model Preload | `true` | 未配置（默认 `false`） | 冷启动慢 | P2 |
| 用户认证 | 共享 Token | 共享 Token（同样没有） | 均缺失 | P0 |
| 用户数据隔离 | 无 | 无 | 均缺失 | P0 |
| 备份配置 | 无 | 无 | 均缺失 | P1 |
| 资源配置 | 单副本、内存 1 GB | 未配置 | 缺失 | P1 |

**关键推论（不推断、只陈述）**：Production 环境虽然存在，但**没有任何 `POCKETSCORE_*` 变量**。
而代码在 `staging`/`production` 下会执行 `validate_hardened_secrets()` ——
缺 Session Secret、缺加密密钥、缺门禁凭据、`DEBUG` 默认 `true`、`ALLOW_PRIVATE_NETWORK_SOURCES` 默认 `true`。
按代码逻辑，**Production 现状若直接部署会启动失败**（这是保护机制生效，而非故障）；
但反过来说明"分类为未配置"是正确的，不能视为"默认即安全"。

## 16. 风险清单

| # | 等级 | 风险 | 证据 | 后果 | 是否阻塞上线 |
| --- | --- | --- | --- | --- | --- |
| R1 | **P0** | Production 无服务部署实例 | `deployment list -e production` = `[]` | 无法上线 | **是** |
| R2 | **P0** | Production 无任何 `POCKETSCORE_*` 变量 | 变量审计 = 0 | 无法启动 / 默认不安全 | **是** |
| R3 | **P0** | Production 无 Volume | `volumes: []` | 部署即丢数据 | **是** |
| R4 | **P0** | 无用户认证与数据隔离 | 无 user 模型/外键（§8/§9） | 全部项目对任何持令牌者可见 | **是（多用户）** |
| R5 | **P0** | Production 若用默认值将 `DEBUG=true`、允许私有网络 | `config.py` 默认值 | 信息泄露 / SSRF 面扩大 | **是** |
| R6 | P1 | 无 Git 集成，部署靠 CLI 上传 | 部署 meta 无 repo/branch | 不可追溯、无法自动回滚 | 是（建议） |
| R7 | P1 | `railway.json` 3 天后弃用 | CLI 警告 2026-12-01 | 配置失效风险 | 是（建议） |
| R8 | P1 | 无备份/恢复方案 | 仓库无 backup 脚本 | 数据不可恢复 | 是（建议） |
| R9 | P1 | 无 API 级 IP 限流（仅门禁失败限流） | 代码 | 资源耗尽 | 否 |
| R10 | P1 | SQLite 单写者 + 单副本 | 架构 | 无法水平扩展 | 否（当前规模可） |
| R11 | P2 | 门禁限流为内存态 | `access_gate.py` | 重启清零/多副本不共享 | 否 |
| R12 | P2 | Model Preload 生产未配置（默认 false） | 默认值 | 首请求慢 | 否 |
| R13 | P2 | 无结构化告警/监控与回滚流程 | 无相关配置 | 故障发现慢 | 否 |
| R14 | P3 | 环境变量文档与 `.env.example` 需同步维护 | 文档 | 维护成本 | 否 |

## 17. Production 上线阻塞项（必须全部清零）

1. R1 创建/确认 Production 服务部署（**本阶段未创建**）。
2. R2 配置 15 个 `POCKETSCORE_*`，密钥与 Staging **不同**。
3. R3 创建 Production 专属 Volume 并挂载 `/data`（禁止与 Staging 共用）。
4. R4 用户认证与数据隔离（C.5），或明确"仅单租户受控使用"的书面边界。
5. R5 显式 `DEBUG=false`、`ALLOW_PRIVATE_NETWORK_SOURCES=false`、`ACCESS_GATE_MODE=token`。
6. R6 决定部署来源（Git 连接或保留 CLI 上传并记录 SHA）。
7. R7 在 2026-12-01 前迁移 `railway.json` → `.railway/railway.ts`。
8. R8 备份方案（Volume 快照 / `sqlite3 .backup` 定时任务）。

## 18. 整改建议优先级

| 顺序 | 动作 | 对应风险 | 说明 |
| --- | --- | --- | --- |
| 1 | 决定"单租户受控"还是"多用户" | R4 | 决定是否必须先在 C.5 做认证 |
| 2 | 建 Production 服务 + Volume + 变量 | R1/R2/R3/R5 | 用与 Staging 不同的密钥 |
| 3 | 迁移 IaC（`.railway/railway.ts`） | R7 | 3 天窗口 |
| 4 | 备份与恢复演练 | R8 | Volume 快照或 SQLite backup |
| 5 | IP 级限流与告警 | R9/R13 | 上线后第一批 |
| 6 | 文档与 `.env.example` 同步 | R14 | 持续 |

## 19. 只读操作自检

| 检查项 | 预期 | 实际 |
| --- | --- | --- |
| Railway 配置修改 | NO | ✅ NO |
| 触发部署 | NO | ✅ NO |
| 重启/停止服务 | NO | ✅ NO |
| 修改 Volume | NO | ✅ NO |
| 操作数据库（写/迁移/恢复） | NO | ✅ NO |
| 写入业务数据 | NO | ✅ NO（仅 GET `/health` `/ready`） |
| 读取并输出 Secrets | NO | ✅ NO（值只在进程内比较，未落终端/报告） |
| 输出完整数据库 URL | NO | ✅ NO（只写 `sqlite` + 路径是否为绝对 + 文件名） |
| 修改 Git 文件 | NO | ✅ NO |
| Commit / Push / Merge | NO | ✅ NO |
| 部署 Production | NO | ✅ NO |

使用的只读命令：`whoami`、`status`、`environment list`、`volume list`、`domain list`、
`deployment list`、`variables --json`（读后即删原始 dump）、`GET /health`、`GET /ready`。
**未使用** `railway up/deploy/restart/down/domain`（无子命令形式会创建域名）、`variables set/delete`。

## 20. 最终结论

```text
BLOCKED
```

理由：

- Staging 侧审计**完整且有证据**（资源、变量、Secrets 元数据、Volume、门禁、线上探针均 VERIFIED）。
- Production 侧**未配置**：无服务实例、无变量、无 Volume、无域名、无部署记录。
  "Production 配置完整性"没有可审计对象，因此无法给出 PASS。
- 同时发现与 Production 无关但影响上线的 P0：**无用户认证与数据隔离**（R4）、
  Production 若用默认值会启用 `DEBUG` 与私有网络（R5）。
- 证据不足以形成"Production 可安全上线"的结论 → 按 §15 判为 BLOCKED，而非 FAIL
  （未发现既有的严重配置错误，因为配置尚不存在）或 PASS。

**本结论不代表获得 Production 部署授权。**

> 附注：Staging 本身状态健康 —— `/health` 200、`/ready` 200、门禁 `enabled=true`、
> Volume `Ready`（40.2 MB / 500 MB）、最近部署 SUCCESS。

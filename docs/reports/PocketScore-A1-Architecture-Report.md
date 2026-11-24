# PocketScore A.1 — 工程架构报告

- **项目**：PocketScore AI
- **版本**：V1.0-A（`1.0.0a1`）
- **阶段**：A.1 系统总体架构
- **报告时间**：2026-11-24
- **结论**：**PASS**（前后端均可启动并通过真实请求验证）

---

## 1. 阶段目标与完成情况

| 目标 | 状态 | 证据 |
| --- | --- | --- |
| 前后端分离工程 | ✅ | `backend/`（FastAPI）+ `frontend/`（Vite+React），仅通过 `/api/v1` 通信 |
| 模块职责清晰 | ✅ | `api`(边界) / `services`(领域) / `models`(ORM) / `schemas`(契约) 分层 |
| API 统一版本管理 | ✅ | 全部业务路由挂载在 `POCKETSCORE_API_V1_PREFIX=/api/v1` |
| 统一错误处理 | ✅ | `app/core/errors.py` + 4 个全局异常处理器，信封 `{error:{code,message,details,request_id}}` |
| 统一日志规范 | ✅ | `app/core/logging.py`，文本/JSON 双格式，自动携带 `request_id` |
| 配置环境变量 | ✅ | `pydantic-settings`，`POCKETSCORE_` 前缀，`.env.example` 全量注释 |
| 区分开发/生产 | ✅ | `POCKETSCORE_ENVIRONMENT`，CORS 白名单、日志格式、SQL echo 均随环境变化 |
| 密钥不入库 | ✅ | `.gitignore` 排除 `.env`/`*.pem`/`*.key`；令牌设计为 Fernet 加密落库 |
| 预留数据库迁移 | ✅ | Alembic 已安装，`Base.metadata` 为唯一建表来源 |
| 完整 README | ✅ | `README.md`（技术栈、启动、结构、设计原则） |
| 目录 `docs/architecture`、`docs/api`、`docs/reports` | ✅ | 均已建立并有内容 |
| 前后端启动测试 | ✅ | 见第 5 节真实请求结果 |

---

## 2. 架构落地

```
backend/app/
├── main.py                 # create_app()：CORS、请求上下文中间件、异常处理器、路由挂载
├── core/
│   ├── config.py           # Settings（环境变量 → 类型化配置，派生存储路径）
│   ├── db.py               # Engine / sessionmaker / Base / init_db（SQLite WAL + FK）
│   ├── errors.py           # AppError 家族（400/401/403/404/409/413/415/422/429/5xx/501）
│   └── logging.py          # JSON / Text formatter + ContextVar request_id
├── api/v1/
│   ├── router.py           # 版本化聚合器（每阶段追加模块，不改已有路径）
│   └── health.py           # 存活、就绪、能力探测
├── models/base.py          # TimestampMixin / IdMixin / utcnow
└── tests/                  # Pytest
```

前端：

```
frontend/src/
├── main.tsx                # QueryClient + BrowserRouter
├── App.tsx                 # 路由表（未交付模块明确标注阶段，不放假数据）
├── components/layout/      # AppShell / Sidebar / TopBar（响应式，移动端抽屉）
├── components/ui/          # Badge / Dot / Spinner / Skeleton / EmptyState
├── pages/                  # Dashboard / Settings / ComingSoon
├── lib/                    # api.ts（统一错误信封）、types.ts、hooks.ts、format.ts、nav.ts
└── test/setup.ts           # jsdom + jest-dom + media stub
```

### 2.1 请求生命周期

1. 中间件注入 `X-Request-ID`（客户端可透传），写入 `ContextVar`。
2. 路由处理，异常统一在处理器内转为错误信封。
3. 中间件记录 `method path -> status (duration_ms)`，回写请求 ID 与耗时。

### 2.2 能力探测（关键设计）

`GET /api/v1/health` 在真实运行时探测 FFmpeg / librosa / soundfile / mido /
pretty_midi / music21 / mutagen，返回 `{available, version, path}`。
前端据此启用或禁用功能，**杜绝“界面可用、调用即报错”**。

本次真实探测结果（Windows / CPython 3.9.13）：

| 依赖 | 可用 | 版本 |
| --- | --- | --- |
| FFmpeg | ✅ | `ffmpeg version 4.2.2`（`imageio-ffmpeg` 内置二进制，系统 PATH 无 ffmpeg） |
| librosa | ✅ | 0.10.2.post1 |
| soundfile | ✅ | 0.12.1 |
| mido | ✅ | 1.3.2 |
| pretty_midi | ✅ | 0.2.10 |
| music21 | ✅ | 8.3.0 |
| mutagen | ✅ | 1.47.0 |

---

## 3. 数据库

本阶段仅建立 **Engine / Session / Base / 建表入口**，业务表在 A.3–A.9 逐阶段追加
（`app/models/__init__.py` 作为注册表）。

- 驱动：SQLite，`check_same_thread=False`，连接级 `PRAGMA foreign_keys=ON`、`journal_mode=WAL`。
- 会话：请求级 `get_db` 依赖 + 事务级 `session_scope()`。
- 表结构变更：Alembic（生产）；`create_all` 仅用于空库快速启动。

## 4. 新增接口（A.1）

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/` | 服务标识（name/version/stage/docs） |
| GET | `/api/v1/health` | 存活 + 能力矩阵 |
| GET | `/api/v1/health/ready` | 就绪检查（数据库/FFmpeg/MIDI） |
| GET | `/api/v1/health/capabilities` | 仅能力矩阵 |

## 5. 测试与运行证据

### 5.1 后端 Pytest

```
$ .\.venv\Scripts\python.exe -m pytest
.....                                                                    [100%]
5 passed in 6.73s
```

覆盖：健康响应结构与能力字段、就绪检查数据库连通、根路由、`X-Request-ID` 回显、
未知路由错误信封（`HTTP_404` + `request_id`）。

### 5.2 前端 Vitest

```
$ npx vitest run
 ✓ src/lib/api.test.ts (6 tests)
 ✓ src/lib/format.test.ts (7 tests)
 ✓ src/pages/DashboardPage.test.tsx (2 tests)
 Test Files  3 passed (3)
      Tests  15 passed (15)
```

### 5.3 生产构建

```
$ npx vite build
✓ 1626 modules transformed.
dist/index.html                   0.62 kB
dist/assets/index-*.css          22.87 kB │ gzip:   4.83 kB
dist/assets/index-*.js          240.90 kB │ gzip:  75.63 kB
✓ built in 26.18s
```

### 5.4 启动验证（真实请求）

```text
backend  : uvicorn app.main:app --host 127.0.0.1 --port 8000
GET /api/v1/health                -> 200 {"stage":"V1.0-A","version":"1.0.0a1",...}

frontend : vite --host 127.0.0.1 --port 5173
GET http://127.0.0.1:5173/        -> 200 (781 bytes HTML)
GET http://127.0.0.1:5173/api/v1/health -> 200 (Vite 代理链路打通)
```

## 6. 已知问题与处理

| 问题 | 影响 | 处理 |
| --- | --- | --- |
| 系统 Python 为 3.8.5（Anaconda），SQLAlchemy 1.3 | 不满足 SQLAlchemy 2.0 / Pydantic v2 | 使用本机 CPython **3.9.13** 建立 `backend/.venv` |
| `music21` 9.x 要求 Python ≥3.10 | 依赖解析回溯卡死 | 约束 `music21>=8.3,<9`，并在 requirements 注释原因 |
| 系统 PATH 无 ffmpeg.exe | 音频预处理不可用 | 由 `imageio-ffmpeg` 提供内置二进制，`resolve_ffmpeg()` 三级回退 |
| 本机 Schannel 客户端（curl/Invoke-WebRequest）TLS 失败 | 仅影响运维脚本 | Node/Python 使用 OpenSSL 正常，已验证 |
| Vite watcher 在 Windows 上被编辑器临时文件（`*.tmpdir`）触发 `EBUSY` | 开发服务器崩溃 | `server.watch.ignored` 显式忽略临时文件 |
| 受限沙箱禁止管道型子进程（esbuild `spawn EPERM`） | 前端构建/测试需提权执行 | 已在需要时以完整访问权限运行，构建与测试结果见 5.2/5.3 |

## 7. 未完成内容（按计划后移）

- A.2 六大 Skill 文件（下一阶段）
- 业务数据表、MusicDocument、键盘、谱面、音源适配器、播放器（A.3–A.8）
- Alembic 基线迁移脚本（A.9 随表结构定型）
- 公开部署与 GitHub Push（A.9，需用户授权）

## 8. 下一阶段

A.2：建立 `pocket-music-core`、`pocket-keyboard-mapping`、`pocket-grid-notation`、
`pocket-jianpu-notation`、`pocket-audio-transcription`、`pocket-music-source`
六个 Skill（SKILL.md + 交叉依赖文档）。

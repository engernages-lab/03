# PocketScore AI · V1.1-C.1 生产部署架构审计（Architecture Audit）

- **审计日期**：2026-11-26
- **审计对象**：`pocketscore-v1.1-b @ afe0086`
- **审计性质**：只读审计（未修改业务代码、未推送、未部署）
- **结论**：**CONDITIONAL PASS**（3 项 P0 阻断公开部署，见风险登记册）

---

## 1. Git 基线

```text
$ git status --short        → 0 行（工作区干净）
$ git branch -vv
  main               5315e3d [origin/main: ahead 1]
  pocketscore-v1.1-a a928983
* pocketscore-v1.1-b afe0086
$ git log --oneline --decorate -4
afe0086 (HEAD -> pocketscore-v1.1-b) feat(V1.1-B): professional score export ...
a928983 (pocketscore-v1.1-a)          feat(V1.1-A): accuracy upgrade ...
5315e3d (main)                        chore(freeze): V1.0-A.10 baseline freeze report ...
9e7cd41 (origin/main)                 docs(A.10): record CI green ...
$ git remote -v
origin  git@github.com:engernages-lab/03.git (fetch/push)
```

| 项 | 结果 |
| --- | --- |
| 当前分支 | `pocketscore-v1.1-b`（符合预期，V1.1-B 工作分支） |
| HEAD | `afe0086`（V1.1-B 提交，未推送） |
| 工作区 | 干净（0 修改、0 未跟踪被忽略以外文件） |
| V1.1-A → V1.1-B 关系 | `5315e3d → a928983 → afe0086` 线性，V1.1-B 基于 V1.1-A |
| 未合并功能分支 | `pocketscore-v1.1-a`、`pocketscore-v1.1-b` 均未合并到 `main` |
| 远程一致性 | `origin/main = 9e7cd41`；本地 `main` 领先 1（`5315e3d`），两个功能分支各领先 |
| 跟踪文件 | 241（`git ls-files`），无 `.env` / `.p8` / `.pem` / `.key` |

> 说明：三份 V1.1 提交均在本地，远程尚未包含 V1.1-A/B 代码。这是本轮**不推送**约束的直接结果，
> 不是历史缺失。C.2 开始前必须先决定推送策略（否则线上前端仍是 V1.0-A.10 构建产物）。

---

## 2. 实际技术栈（实测版本）

### 2.1 前端

| 组件 | 版本（`frontend/package.json` + 构建输出） |
| --- | --- |
| React / ReactDOM | 18.3.1 |
| TypeScript | 5.5.4（`tsc -b` 严格模式） |
| Vite | 5.4.3（`@vitejs/plugin-react` 4.3.1） |
| Tailwind CSS | 3.4.10（PostCSS 8.4.45 / autoprefixer 10.4.20） |
| 状态管理 | Zustand 4.5.5 |
| 数据请求 | @tanstack/react-query 5.56.2 |
| 路由 | react-router-dom 6.26.2（`BrowserRouter` + `basename`） |
| 图标 | lucide-react 0.441.0 |
| 单测 | Vitest 2.0.5 + Testing Library 16.0.1 + jsdom 25 |
| E2E | @playwright/test 1.47.0 |
| Node 要求 | 无 `engines` 字段；本机 Node v24.22.0 实测通过；包管理 **npm**（有 `package-lock.json`） |

### 2.2 后端

| 组件 | 版本 |
| --- | --- |
| 本机解释器 | CPython 3.9.13（`backend/.venv`） |
| 容器解释器 | `python:3.11-slim`（`backend/Dockerfile`）→ **两套版本并存，见风险 R-P1-08** |
| FastAPI | 0.110.x（`>=0.110,<0.116`） |
| Uvicorn | 0.29–0.30（`[standard]`） |
| Pydantic | 2.7–2.9 |
| SQLAlchemy | 2.0.x |
| Alembic | 1.13.x（2 个迁移：`0001_initial`、`0002_event_confidence`） |
| ASGI 入口 | `app.main:app`（`create_app()` 工厂，模块级 `app`） |
| 数据库（默认） | SQLite（WAL + `foreign_keys=ON`），16 张表 |
| 后台任务 | FastAPI `BackgroundTasks` + `run_in_threadpool`（**无队列**） |
| 依赖管理 | `requirements.txt`（26 条，全部范围锁定） |

### 2.3 AI 与音频

| 项 | 实测值 |
| --- | --- |
| 模型 | Basic Pitch 0.4.0，`basic_pitch/saved_models/icassp_2022/nmp.onnx` = **230,444 字节** |
| 运行时 | onnxruntime **1.19.2**，providers = `["AzureExecutionProvider", "CPUExecutionProvider"]` |
| GPU | 不需要（纯 CPU 推理路径） |
| FFmpeg | `imageio-ffmpeg` 捆绑 `ffmpeg-win64-v4.2.2.exe`；系统 PATH **无** ffmpeg/ffprobe |
| 音频库 | librosa 0.10.2、soundfile 0.12.1、numpy 1.26.4、mutagen、imageio-ffmpeg |
| MIDI 库 | mido 1.3.2、pretty_midi 0.2.10、music21 8.3.0 |

---

## 3. 前端生产部署审计

### 3.1 构建（实测）

```text
$ VITE_BASE_PATH=/03/ npx vite build
✓ built in 10.61s
dist/index.html                   0.63 kB │ gzip:   0.44 kB
dist/assets/index-D3kZLxVa.css   37.54 kB │ gzip:   6.82 kB
dist/assets/index-DngeKLfM.js   390.32 kB │ gzip: 119.60 kB │ map: 1,514.24 kB
dist 合计 4 个文件 1,913 KB
```

| 检查项 | 结果 |
| --- | --- |
| `tsc --noEmit` | exit 0 |
| 生产构建 | 成功，10.6 s |
| 资源路径 | `base` 由 `VITE_BASE_PATH` 注入，子路径正确（`/03/assets/...`） |
| 路由刷新 404 | Pages 工作流 `cp dist/index.html dist/404.html` ✅ |
| 环境变量缺失 | **`VITE_API_BASE_URL` 未在仓库变量中设置**（工作流读 `vars.VITE_API_BASE_URL`）→ 见 R-P0-01 |
| 警告 | 有 sourcemap（1.5 MB `.map` 随产物发布）→ R-P1-09 |

### 3.2 API 地址架构

| 检查项 | 结论 | 证据 |
| --- | --- | --- |
| 统一入口 | ✅ 单一 `VITE_API_BASE_URL` | `src/lib/api.ts:8-10` |
| 业务代码硬编码 | ✅ 无（仅用户可见占位符/文档文本） | 全仓 `src/**` 扫描，命中 4 处均为文案 |
| 开发环境 | Vite proxy `/api` → `127.0.0.1:8000` | `vite.config.ts:34-42` |
| 生产环境 | 构建期注入绝对地址；为空时同源 | `api.ts` + 工作流 `env:` |
| WebSocket | 无（未使用） | 全仓无 `ws://` |
| 上传/导出地址 | 全部走 `API_V1` 前缀 | `buildUrl()` 唯一拼接点 |
| 密钥进前端 | ✅ 无（前端仅 `VITE_*` 公开配置） | `.env.example` 明确区分 |

### 3.3 浏览器兼容性（代码事实）

| 能力 | 实现 | 兼容性判断 |
| --- | --- | --- |
| 音频上传 | `<input type="file">` + `FormData` | 全绿 |
| PNG/ZIP 导出 | `canvas.toBlob` + `Blob` + `<a download>` | Chrome/Edge/Firefox 可用 |
| PDF 导出 | 同上（内存中生成字节） | 同上 |
| 保存落盘 | 优先 `showSaveFilePicker`（Chromium），否则 `<a download>` | Firefox/Safari 走降级；**落盘未验证（TD-06）** |
| Canvas 尺寸 | 1080×1920 ~ 2160×3840，40 MP 硬保护 | Safari iOS 上限更低，未测 |
| 大文件 | 22 页 ZIP 1.8 MB 实测通过 | 可用 |

---

## 4. 后端运行环境审计

### 4.1 启动与生产命令

```text
生产命令（Dockerfile:39）:
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

| 检查项 | 结果 |
| --- | --- |
| ASGI 入口 | ✅ `app.main:app`（已实测 `TestClient(app)` 可启动） |
| 启动耗时 | **0.24 s**（TestClient，含 `init_db()` + 能力探测缓存） |
| 健康检查 | ✅ `GET /api/v1/health` 200；另有 `/api/v1/health/ready`（DB/FFmpeg/MIDI） |
| 端口 | ❌ CMD 硬编码 `8000`，**未读取 `$PORT`** → R-P0-02（Railway） |
| 静态托管 | ✅ `serve_frontend=true` 时挂载 `frontend/dist`，同源无 CORS |
| 优雅关闭 | ⚠️ 未配置 `--timeout-graceful-shutdown`，在跑任务会被中断 |
| worker 数 | ⚠️ 单 worker（默认）；多 worker 会与 BackgroundTasks/SQLite 冲突 |

### 4.2 依赖与系统库

| 检查项 | 结果 |
| --- | --- |
| 纯 Python 依赖 | ✅ `pip install -r requirements.txt` 覆盖全部 |
| 系统库 | `libsndfile1`（Dockerfile 已装）、`ca-certificates` |
| 动态库 | `soundfile` 需 libsndfile；`librosa` 需 numba/llvmlite（wheel 已带） |
| 容器体积 | 未实测构建（本环境不执行 docker build）；镜像预计 1.2–1.8 GB（onnxruntime + librosa + numpy + 前端 dist） |

---

## 5. Basic Pitch / ONNX 生产兼容性审计

### 5.1 模型加载方式（关键发现）

`basic_pitch.inference.run_inference()` 源码：

```python
if isinstance(model_or_model_path, Model):
    model = model_or_model_path
else:
    model = Model(model_or_model_path)     # ← 每次 predict 都新建会话
```

我们的调用（`app/services/audio/transcription/inference.py:87-98`）传的是**路径**，因此每个作业都会
重新构造 ONNX 会话。实测构造成本 **0.028–0.073 s**（模型仅 230 KB，代价小但非零），
且会重复分配 ORT arena。

| 检查项 | 结论 |
| --- | --- |
| 模型文件真实存在 | ✅ 230,444 字节 `nmp.onnx` |
| 依赖运行时 | ✅ onnxruntime 1.19.2，CPUExecutionProvider |
| 是否依赖 GPU | ❌ 不需要 |
| 每次请求重复加载 | ⚠️ **是**（传路径）。建议改为启动时构造 `Model` 单例传入 |
| 启动预热 | ❌ 无（首个作业承担冷启动，见 §5.3） |
| 并发安全 | ⚠️ ORT session 可并行，但无并发上限（见 §6） |

### 5.2 推理性能（实测，CPU，本机 Windows）

| 音频 | 时长 | 推理耗时 | 检出音符 | 峰值 RSS |
| --- | --- | --- | --- | --- |
| `short_4s.wav` | 4 s | 1.88 s（首调用，含 ORT 预热） | 8 | 177.6 MB |
| `medium_30s.wav` | 30 s | **0.26 s** | 60 | 192.0 MB |
| `long_120s.wav` | 120 s | **1.13 s** | 239 | **261.7 MB** |

- 纯推理约 **0.9 s / 音频分钟**；内存随长度线性增长（4 s→177 MB，120 s→262 MB）。
- 冷进程（新解释器 + 冷模型）单次 4 s 音频：**1.67–2.06 s**。
- 两个进程并发处理 30 s 音频：墙钟 5.49 s，各自 2.19/2.32 s → **CPU 抢占近似线性**，
  说明并发不提升吞吐，只增加内存。

### 5.3 端到端作业延迟（含 FFmpeg 解码、后处理、写库）

| 场景 | 20 s / 0.84 MB WAV |
| --- | --- |
| 进程内首个作业（含 numba JIT + 库导入） | **7.6 s**（其中 `detect_onsets` 首调用 3.67 s） |
| 稳态第 1 次 | 0.57 s |
| 稳态第 2 次 | 0.51 s |
| 稳态第 3 次 | 0.56 s |
| 单阶段耗时 | `verify_decodable` 0.55 s、`probe_audio` 0.02 s、`energy_envelope` 0.02 s、`run_model` 0.62 s |

> 结论：**稳态 0.5 s 级**，冷启动 7.6 s。`detect_onsets` 的 numba JIT 只在首次触发，
> 而其结果在当前管线中仅用于统计（切分走 `split_by_energy`）→ 可移除或改为启动预热（R-P1-10）。

---

## 6. FFmpeg 审计

| 检查项 | 结果 |
| --- | --- |
| 依赖形式 | `imageio-ffmpeg` 随 wheel 捆绑可执行文件（**无需 apt install ffmpeg**） |
| 版本 | **4.2.2**（2019 年构建，较旧） |
| 解析顺序 | `POCKETSCORE_FFMPEG_PATH` → `PATH` → imageio 捆绑（`probe.py:75-87`） |
| 是否需要 ffprobe | ❌ 不需要（用 `ffmpeg -i` 解析容器信息 + `wave` 兜底） |
| 支持的容器 | MP3/WAV/FLAC/M4A/AAC/OGG/OPUS（`SUPPORTED_EXTENSIONS`，实测 6 种格式测试全绿） |
| MIDI | 独立路径（mido/pretty_midi/music21），不经 FFmpeg |
| 超时 | `ffprobe_timeout_seconds=60`（探测）、解码验证 120 s 硬编码 |
| 失败处理 | 抛 `AUDIO_PROBE_FAILED`（实测 HTTP 422） |
| Linux 可用性 | imageio-ffmpeg 提供 manylinux wheel，Dockerfile 无需额外安装；**未在 Linux 实测** |

---

## 7. 数据库与持久化审计

| 检查项 | 结果 |
| --- | --- |
| 引擎 | SQLite（`sqlite:///./data/pocketscore.db`），WAL 模式，外键开启 |
| 表 | 16 张（`audio_assets`、`music_documents`、`music_events`、`transcription_jobs` 等） |
| 初始化 | `init_db()` → `create_all` + `sync_additive_columns()`（可空新列自愈） |
| 迁移 | Alembic 2 个版本；**部署流程不自动执行**，靠自愈兜底 |
| 音频存储 | `data/storage/audio/<sha2>/<sha256><ext>`，内容寻址 + 校验去重 |
| 路径安全 | DB 存相对路径，`absolute_path()` 与存储根拼接；用户文件名仅取扩展名 |
| 容器持久化 | Dockerfile 声明 `VOLUME ["/data"]`；Railway 需显式挂载卷 |
| 多副本 | ❌ SQLite 单文件 + WAL 不支持多实例并发写 |
| Postgres 就绪 | ⚠️ ORM 层无 SQLite 硬依赖（PRAGMA 已按 URL 分支），但 **requirements 无 psycopg/asyncpg 驱动** |
| 备份 | ❌ 无备份策略（无脚本、无定时任务） |

**判定**：SQLite 可用于「单实例 + 持久卷 + 低并发」的首发验证；任何水平扩展、并发写、
数据可靠性要求都需要 PostgreSQL（C.3）。

---

## 8. 上传与存储安全审计

| 检查项 | 现状 | 证据 |
| --- | --- | --- |
| 大小限制 | ✅ 200 MB（`max_upload_mb`） | `assets.py:144` |
| **但**：先读全量再校验 | ⚠️ `data = await file.read()` → 200 MB 进内存 | `api/v1/audio.py:75` |
| 请求体上限 | ❌ 无 ASGI/网关级限制 | 无 `Content-Length` 预检 |
| 扩展名校验 | ✅ 白名单 7 种 | `probe.py:27,64` |
| 真实格式校验 | ✅ FFmpeg 解码验证 + 时长探测 | `probe.verify_decodable()` |
| MIME 校验 | ⚠️ 仅记录，不据此拒绝（以真实解码为准，更可靠） | `MIME_TYPES` |
| 文件名安全 | ✅ 显示名截断 255，存储名 = sha256 | `assets.py:183-184` |
| 路径穿越 | ✅ 无用户可控路径拼接 | 同上 |
| 时长上限 | ✅ 600 s | `max_audio_duration_seconds` |
| 临时文件 | ✅ `TemporaryDirectory` 自动清理；拒绝时 `unlink` | `assets.py:168` |
| 任务取消 | ✅ `POST /jobs/{id}/cancel`（终态 no-op） | `api/v1/transcription.py` |
| 僵尸临时文件回收 | ❌ 无常驻清理（进程崩溃时 `TemporaryDirectory` 由 OS 回收） | 无 TTL 清理 |
| 单用户并发限制 | ❌ 无 | 无实现 |
| 全局并发限制 | ❌ 无（线程池上限 40，非业务限制） | 无实现 |
| 任务超时 | ❌ 无（600 s 音频理论可跑数分钟，无中断机制） | 无实现 |

---

## 9. 安全审计

### 9.1 密钥与配置

| 检查项 | 结果 |
| --- | --- |
| `.env` 入库 | ❌ 未跟踪（`.gitignore` 覆盖 `.env`、`.env.*`、`*.db`、`storage/`） |
| Git 历史含密钥文件 | ✅ 无（`git log --all -- "*.env" "*.p8" "*.pem" "*.key"` 空） |
| 跟踪文件含 `.env`/`.p8`/`token` | ✅ 无 |
| 前端持有后端密钥 | ✅ 无 |
| `session_secret` 默认值 | ⚠️ `change-me-in-production`，**生产不校验** → R-P1-04 |
| `token_encryption_key` 缺省行为 | ⚠️ 派生自机器本地文件 → 容器重建即失效 → R-P1-05 |
| `allow_private_network_sources` 默认 | ⚠️ `True` → 云端可访问内网/metadata → R-P1-06 |

### 9.2 API 面

| 检查项 | 结果 |
| --- | --- |
| 认证 | ❌ **完全没有**（无用户体系、无 token 校验） |
| 授权/租户隔离 | ❌ 单租户；任何人可读删所有项目 |
| 频率限制 | ❌ 无 |
| CORS | ⚠️ 默认仅 `localhost:5173/4173`；生产未配置即阻断 Pages 域名 |
| 错误信息 | ✅ 500 返回 `Internal server error`，无堆栈/路径泄漏 |
| 调试接口 | ✅ 无（`/docs` 由 FastAPI 默认开启，生产建议关闭） |
| 任意文件读取 | ✅ 无（`/static` 仅挂载 storage 目录；播放代理有 SSRF 防护与白名单） |
| 日志隐私 | ⚠️ `logger.info("running %s on %s", MODEL_ID, path.name)` 记录文件名；无音频内容 |

### 9.3 结论

当前后端**只能视为单用户/未认证服务**。在公开互联网上暴露前，必须至少具备：
认证、限流、请求体上限、并发配额。否则任何脚本都能消耗 AI 推理资源（R-P1-01/02）。

---

## 10. Railway 可行性（详见 Deployment-Architecture）

| 条件 | 状态 |
| --- | --- |
| Python 运行环境 | ✅ Dockerfile 存在（`python:3.11-slim`） |
| FFmpeg | ✅ 由 imageio-ffmpeg 提供，无需系统包 |
| ONNX Runtime | ✅ CPU wheel，docker 内可安装 |
| 模型加载 | ✅ 230 KB 随 wheel 分发 |
| 启动命令 | ❌ 硬编码 8000，忽略 `$PORT` → **P0** |
| Dockerfile 位置 | ❌ `backend/Dockerfile`，Railway 默认只看根目录 → 需 `RAILWAY_DOCKERFILE_PATH` → **P0** |
| 健康检查 | ✅ `/api/v1/health` |
| PostgreSQL | ⚠️ 无驱动依赖，需加 `psycopg[binary]` |
| Volume | ✅ Dockerfile 声明 `/data` |
| 内存 | ⚠️ 峰值 262 MB/任务，无并发上限 → 需 ≥1 GB 实例 |
| 构建时间 | 未实测（pip 安装 librosa/onnxruntime 预计 3–6 分钟） |

---

## 11. 功能依赖矩阵

| 功能 | 前端 | 后端 | AI / 外部依赖 | 数据持久化 | 生产风险 | 状态 |
| --- | --- | --- | --- | --- | --- | --- |
| 音频上传 | VERIFIED | VERIFIED | FFmpeg | 文件系统 | 200 MB 读入内存 | VERIFIED |
| AI 扒谱 | VERIFIED | VERIFIED | Basic Pitch + ONNX | DB + 文件 | 无并发上限/无超时 | VERIFIED（资源受限） |
| 格子谱 | VERIFIED | VERIFIED | 内部模块 | DB | 无 | VERIFIED |
| 数字谱 | VERIFIED | VERIFIED | 内部模块 | DB | 无 | VERIFIED |
| 双谱同步 | VERIFIED | VERIFIED | MusicDocument | DB | 无 | VERIFIED |
| 音符编辑 | VERIFIED | VERIFIED | MusicDocument | DB | 无 | VERIFIED |
| 播放器 | VERIFIED | VERIFIED | 浏览器音频能力 | 无（代理流） | 上游 Range | VERIFIED |
| 项目保存 | VERIFIED | VERIFIED | DB | SQLite | 卷丢失风险 | VERIFIED |
| 项目重开 | VERIFIED | VERIFIED | DB | SQLite | 同上 | VERIFIED |
| MIDI 导出 | VERIFIED | VERIFIED | mido/pretty_midi | 无 | 无 | VERIFIED |
| PNG 导出 | VERIFIED | — | Canvas | 无 | 落盘未验证 | PARTIAL |
| PDF 导出 | VERIFIED | — | 自研写入器 | 无 | 位图非矢量 | PARTIAL |
| ZIP 导出 | VERIFIED | — | 自研 ZIP | 无 | 落盘未验证 | PARTIAL |
| 公开 API 接入 | **MISSING** | VERIFIED | — | — | Pages 无 API 地址 | **MISSING** |
| 用户认证 | MISSING | MISSING | — | — | 完全开放 | **MISSING** |
| 多用户隔离 | MISSING | MISSING | — | — | 数据互相可见 | **MISSING** |

**仅本地可用功能**：无。所有功能在 API 可达时均可跨网络使用；但**当前线上前端无 API 地址**，
因此线上表现为"静态预览"，这是部署配置缺失而非功能局限。

---

## 12. 测试结果（本轮实跑）

| 层级 | 命令 | 结果 |
| --- | --- | --- |
| 后端静态检查 | `ruff check app tests` | All checks passed |
| 后端测试 | `pytest` | **296 passed**（36.4 s） |
| 前端类型 | `tsc --noEmit` | exit 0 |
| 前端单测 | `vitest run` | **99 passed**（11 files） |
| 前端生产构建 | `vite build`（base=/03/） | 成功，10.6 s，1,913 KB |
| E2E | `playwright test` | **15 passed / 1 skipped**（58.9 s） |
| FFmpeg 版本 | `ffmpeg -version` | 4.2.2 |
| ONNX providers | `onnxruntime.get_available_providers()` | Azure / CPU |

---

## 13. 未验证事项（明确标记）

| 项 | 原因 |
| --- | --- |
| Docker 镜像构建与运行 | 本阶段禁止部署；未执行 `docker build` |
| Linux 下 ONNX 推理性能 | 本机为 Windows；Linux 数值可能不同 |
| Railway 实际构建时间/冷启动 | 未创建任何云资源 |
| 浏览器落盘保存 | 沙箱 Chromium 取消所有下载（TD-06） |
| Firefox / WebKit | 本机仅安装 Chromium |
| 600 DPI × 多页导出的内存峰值 | 未实跑极限组合（TD-10） |
| 真实录音识别精度 | 基准为合成音频（TD-01b） |

---

## 14. 结论

**CONDITIONAL PASS** —— 代码层面具备部署条件（构建通过、依赖自洽、模型与 FFmpeg 可随镜像分发），
但**部署配置缺失 3 项 P0**（前端 API 地址、Railway Dockerfile/PORT、CORS 域名），
且安全面（认证/限流/并发上限）尚不足以公开暴露。

依据：
1. 前端构建与 Pages 子路径分配置已具备，唯一缺口是 `VITE_API_BASE_URL` 未配置。
2. 后端可独立运行，健康检查齐全，但容器启动命令与平台端口约定不兼容。
3. AI 推理在 CPU 上可用（稳态 0.26–1.13 s/次），资源需求明确（≥1 GB，单任务 262 MB 峰值）。
4. 数据库与文件存储可持久化，但仅限单实例；扩展需 Postgres + 对象存储。
5. 无认证、无限流、无并发上限 → 公开前必须补（C.5）。

详见：
[Deployment-Architecture](PocketScore-V1.1-C.1-Deployment-Architecture.md) ·
[Risk-Register](PocketScore-V1.1-C.1-Risk-Register.md) ·
[Implementation-Roadmap](PocketScore-V1.1-C.1-Implementation-Roadmap.md) ·
[架构图](../architecture/PocketScore-Production-Architecture.mmd)

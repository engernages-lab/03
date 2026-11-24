# PocketScore AI · V1.0-A

**Foundation & Multi-Source Music Ecosystem** — 一个真正可使用的 Web 音乐工作站：
多音源统一曲库 + 完整播放器 + AI 扒谱输入管线 + 自定义口袋键盘 + 格子谱 / 数字谱双引擎。

> 本仓库遵循“分阶段实施、逐项自检、自动化测试、独立验收”的开发纪律。
> **任何未交付的能力都不会显示模拟数据或伪造的识别结果。**

---

## 1. 当前状态

| 阶段 | 内容 | 状态 |
| --- | --- | --- |
| A.1 | 工程架构（前后端分离、配置、日志、错误、DB、健康检查） | ✅ 完成 |
| A.2 | 六大 AI Skill 文件与交叉依赖 | ✅ 完成 |
| A.3 | MusicDocument 核心数据引擎 | ✅ 完成 |
| A.4 | 自定义口袋键盘系统 | ✅ 完成 |
| A.5 | MIDI 与音频输入基础 | ✅ 完成 |
| A.6 | 格子谱引擎 | ✅ 完成 |
| A.7 | 数字谱与双格式同步 | ✅ 完成 |
| A.8 | 多音源音乐中心与完整播放器 | ✅ 完成（外部平台按真实授权情况交付，见报告） |
| A.9 | 数据库、测试与部署 | 🟡 测试与部署产物完成；公网部署待托管凭据（Push 已完成） |

**测试现状**：后端 `pytest` **229 passed** · 前端 `vitest` **46 passed** · 端到端 `playwright` **6 passed**
（dev server 与生产构建产物各跑一遍，合计 **281** 项）

仓库：<https://github.com/engernages-lab/03>（`main`，公开）

阶段报告见 [`docs/reports/`](docs/reports/)，界面截图见 [`docs/screenshots/`](docs/screenshots/)。

---

## 2. 技术栈

**前端** React 18 · TypeScript 5 · Vite 5 · Tailwind CSS 3 · Zustand 4 · TanStack Query 5 · React Router 6
**后端** Python 3.9 · FastAPI · Pydantic v2 · SQLAlchemy 2 · Alembic
**数据** SQLite（WAL 模式，预留迁移到 PostgreSQL）
**音频** FFmpeg（经 `imageio-ffmpeg` 提供二进制）· librosa · soundfile
**MIDI** mido · pretty_midi · music21
**测试** Pytest · Vitest · Playwright

---

## 3. 快速开始

### 3.1 后端

```powershell
cd backend
python -m venv .venv                      # Python 3.9+
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

- API 根地址 <http://127.0.0.1:8000>
- 交互式文档 <http://127.0.0.1:8000/docs>
- 健康检查 <http://127.0.0.1:8000/api/v1/health>

### 3.2 前端

```powershell
cd frontend
npm install
npm run dev
```

开发服务器 <http://127.0.0.1:5173>，`/api` 与 `/static` 由 Vite 代理到后端。

### 3.3 一键脚本

```powershell
.\scripts\dev.ps1      # 同时启动后端与前端
.\scripts\test.ps1     # 后端 Pytest + 前端 Vitest
.\scripts\check.ps1    # Ruff + TypeScript 类型检查
```

### 3.4 环境变量

复制 [`.env.example`](.env.example) 为 `.env`（已被 `.gitignore` 忽略）。
所有后端配置使用 `POCKETSCORE_` 前缀，前端使用 `VITE_` 前缀。
**任何密钥、令牌、Cookie 都不得提交到 Git。**

---

## 4. 目录结构

```
.
├── backend/
│   ├── app/
│   │   ├── api/v1/          # 版本化路由（每个功能模块一个文件）
│   │   ├── core/            # 配置、日志、错误、数据库
│   │   ├── models/          # SQLAlchemy ORM
│   │   ├── schemas/         # Pydantic 请求/响应模型
│   │   └── services/        # 领域服务（引擎、适配器、解析器）
│   ├── tests/               # Pytest 单元 + 集成测试
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── components/      # UI 与布局
│       ├── pages/           # 路由页面
│       ├── store/           # Zustand 状态
│       ├── lib/             # API 客户端、格式化、hooks
│       └── engines/         # 与后端共享契约的渲染层
├── docs/
│   ├── architecture/        # 架构说明
│   ├── api/                 # 接口约定
│   └── reports/             # 阶段开发报告
├── .agents/skills/          # 六大 AI Skill
├── tests/e2e/               # Playwright 端到端
└── scripts/                 # 开发/测试脚本
```

---

## 5. 设计原则

1. **单一数据源** — 格子谱与数字谱都由同一份 `MusicDocument` 生成，绝不各自保存音符。
2. **逻辑不重复** — 音高→键位、音高→简谱数字等转换只在后端实现一次，前端只负责渲染后端计算出的视图模型。
3. **能力如实上报** — `/api/v1/health` 返回真实探测到的运行时能力；缺失依赖时前端禁用对应功能，而不是假装可用。
4. **权限分层** — `metadata_access` / `playback_access` / `audio_read_access` / `ai_processing_permission` / `model_training_permission` 五项独立判断，任何一项不满足都不会进入扒谱。
5. **平台政策优先** — Spotify 内容永久标记 `PROVIDER_RESTRICTED`，不进入 AI 音频链路；Apple Music 只通过 MusicKit 官方播放；不下载、不转存、不逆向。
6. **安全默认** — 第三方令牌加密存储、SSRF 校验、上传大小与类型白名单、错误不泄漏堆栈。

---

## 6. 文档

- [架构总览](docs/architecture/system-overview.md)
- [API 约定](docs/api/conventions.md)
- [部署指南](docs/deployment.md)
- [阶段报告](docs/reports/)
- [界面截图](docs/screenshots/)
- 六大 Skill：[`.agents/skills/`](.agents/skills/)

## 6.1 一键验证

```powershell
.\scripts\test.ps1      # 后端 pytest + 前端 vitest
.\scripts\check.ps1     # ruff + tsc
python scripts/make_fixtures.py   # 生成 E2E 用的 sample.mid / tone.wav
npx playwright test     # 端到端（需先构建 frontend 或启动 vite）
```

---

## 7. 许可证

内部项目，未授权不得分发。第三方音乐内容版权归各平台与权利人所有。

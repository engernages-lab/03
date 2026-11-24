# PocketScore AI · V1.0-A 最终开发报告

> Foundation & Multi-Source Music Ecosystem · 最终交付说明
> 报告日期：2026-11-24 ｜ 版本：`1.0.0a1` ｜ 阶段：V1.0-A

---

## 1. 项目版本

| 项 | 值 |
| --- | --- |
| 产品 | PocketScore AI |
| 版本 | V1.0-A（后端 `1.0.0a1`，前端 `1.0.0-a`） |
| 阶段 | Foundation & Multi-Source Music Ecosystem |
| 技术栈 | React 18 + TS 5 + Vite 5 + Tailwind 3 + Zustand 4 / Python 3.9 + FastAPI + Pydantic v2 + SQLAlchemy 2 + SQLite(WAL) |
| 运行时依赖 | FFmpeg（`imageio-ffmpeg` 内置 4.2.2）、librosa 0.10.2、soundfile 0.12.1、mido 1.3.2、pretty_midi 0.2.10、music21 8.3.0、mutagen 1.47 |

## 2. 开发范围

任务书 A.1–A.9 全部九个阶段均已实施。范围覆盖：工程架构、六大 Skill、MusicDocument
引擎、自定义键盘、MIDI/音频输入、格子谱、数字谱与双格式同步、多音源音乐中心与播放器、
数据库/测试/部署产物。

## 3. 完成情况

| 阶段 | 内容 | 状态 |
| --- | --- | --- |
| A.1 | 工程架构 | ✅ PASS |
| A.2 | 六大 Skill | ✅ PASS |
| A.3 | MusicDocument 引擎 | ✅ PASS |
| A.4 | 自定义键盘 | ✅ PASS |
| A.5 | MIDI 与音频输入 | ✅ PASS |
| A.6 | 格子谱引擎 | ✅ PASS |
| A.7 | 数字谱与双格式同步 | ✅ PASS |
| A.8 | 音乐中心与播放器 | 🟡 CONDITIONAL PASS（外部平台按真实授权情况交付） |
| A.9 | 数据库/测试/部署 | 🟡 CONDITIONAL PASS（Push 与公网部署待授权） |

**总验收结论：CONDITIONAL PASS**（见 §17）。

## 4. 架构说明

```
React SPA ──/api/v1──► FastAPI 路由层（Pydantic 校验）
                          │
                          ├─ services/music_document  （唯一音符真源）
                          ├─ services/keyboard        （音高↔键位唯一实现）
                          ├─ services/notation        （grid / jianpu / sync）
                          ├─ services/midi + audio    （输入侧）
                          ├─ services/sources         （6 个适配器）
                          ├─ services/library         （统一曲库）
                          ├─ services/eligibility     （扒谱资格闸门）
                          └─ services/transcription   （作业状态机）
                          │
                     SQLAlchemy 2 → SQLite(WAL) · Alembic 迁移
```

关键设计：

1. **单一数据源**：`MusicDocument` 是唯一音符存储，两种谱面均为纯函数编译结果，因此不可能分叉。
2. **转换唯一实现**：音高→键位、音高→简谱数字、拍→小节、MIDI tick→拍 各仅一处。
3. **能力如实上报**：`/api/v1/health` 探测真实运行时能力，前端据此启用/禁用功能。
4. **平台政策优先**：Spotify 三项权限被代码强制清零，永远不进入 AI 链路。

## 5. Skill 使用情况

| Skill | 使用位置 | 落地文件 |
| --- | --- | --- |
| `pocket-music-core` | 文档契约/时间轴/序列化 | `schemas/music_document.py`、`services/music_document/*` |
| `pocket-keyboard-mapping` | 布局 CRUD/映射 | `schemas/keyboard.py`、`services/keyboard/*` |
| `pocket-grid-notation` | 格子谱视图模型/SVG | `services/notation/grid.py`、`api/v1/notation.py` |
| `pocket-jianpu-notation` | 数字谱/同步/撤销 | `services/notation/jianpu.py`、`sync.py`、`store/document.ts` |
| `pocket-audio-transcription` | MIDI/音频/作业 | `services/midi/*`、`services/audio/*`、`services/transcription.py` |
| `pocket-music-source` | 音源/曲库/资格/播放 | `services/sources/*`、`library.py`、`eligibility.py`、`playback.py` |

六个 Skill 已注册进 DSH 技能目录，并在开发中被逐条对照实现。交叉依赖与「禁止重复实现」清单见
`.agents/skills/README.md`。

## 6. 数据库结构

16 张业务表（`music_documents`、`music_tracks`、`music_events`、`keyboard_layouts`、
`audio_assets`、`music_sources`、`external_accounts`、`music_source_permissions`、
`unified_tracks`、`unified_albums`、`unified_artists`、`unified_playlists`、`playlist_tracks`、
`user_favorites`、`playback_history`、`transcription_jobs`）+ `alembic_version`。

外键级联、唯一约束（`(document_id,event_id)`、`(source_id,external_track_id)`、
`(playlist_id,track_id)`）、查询索引（`(document_id,start_time)`、`pitch`、`played_at`）齐备。
`alembic upgrade head` 本机实测通过。

## 7. API 接口

**79 条**，全部位于 `/api/v1`：

| 前缀 | 条目 |
| --- | --- |
| `/health` | `health` · `ready` · `capabilities` |
| `/documents` | CRUD · `import` · `duplicate` · `edits` · `summary` · `export` |
| `/keyboard-layouts` | CRUD · `duplicate` · `preview` · `export` · `import` · `restore-default` · `pitch-map` |
| `/midi` | `inspect` · `import` · `{id}/export` |
| `/audio` | `upload` · `probe` · `assets` · `{id}` · `waveform` · `analyze` · `stream` |
| `/notation` | `{id}/grid` · `grid.svg` · `jianpu` · `jianpu.txt` · `both` |
| `/sources` | `providers` · CRUD · `{id}/test` · `sync` · `permissions` |
| `/library` | `tracks` · `import` · `stats` · `albums` · `artists` · `favorites` · `playlists`(+tracks) · `history` |
| `/playback` | `stream/{track}` · `proxy/{source}/{external}` |
| `/eligibility` | `{track_id}` · `source/{source_id}` |
| `/transcription` | `models` · `jobs` · `jobs/{id}` · `run` · `cancel` |

错误统一为 `{error:{code,message,details?,request_id}}`；OpenAPI 见 `/docs`。

## 8. 音源接入情况（真实状态）

| 平台 | 状态 | 证据 |
| --- | --- | --- |
| 本地音乐 | ✅ 可用 | E2E 实测：上传→播放→资格→作业 |
| Navidrome / OpenSubsonic | 🟡 协议完整，未连真实服务器 | 12 项 MockTransport 测试覆盖官方端点与认证签名 |
| Apple Music | 🟡 代码就绪，缺凭据 | `test_connection` 返回 `not_configured` |
| Spotify | 🟡 仅元数据，政策限制 | 资格恒为 `PROVIDER_RESTRICTED` |
| 网易云 | ⛔ 无官方接口 | 适配器返回 `unsupported` + 官方链接 |
| QQ 音乐 | ⛔ 无官方接口 | 同上 |

**没有伪造任何平台的连接成功状态。**

## 9. 播放器实现情况

- 队列 / 上一首 / 下一首 / 随机（可注入 RNG 的 Fisher-Yates）/ 循环（off→all→one）/ 音量 / 静音 / 进度拖拽 / 历史。
- 底部统一播放条 + `/music-player` 大播放页（真实波形、快捷键 Space/Shift+←→）。
- 播放按来源分流：本地 `direct`、Navidrome `proxy`（凭据不出后端）、Apple/Spotify `provider_sdk`（明确提示不代理）。
- 状态机 18 项 Vitest；E2E 断言 `<audio src>` 指向真实流地址。

## 10. 双格式制谱情况

- 格子谱：键位行 × 时间列，小节线、时值 span、休止轨道、和弦并列、超出范围提示、SVG 导出。
- 数字谱：1–7 级数、升降号、八度点、时值符号、附点、连音、休止、和弦纵向堆叠、键位小字、文本导出。
- **同步机制**：任一侧编辑 → 编辑指令 → 服务端原子应用 → 两谱整体重编译。
- 撤销/重做：文档快照栈（50 步），通过 `PUT /documents/{id}` 还原后重编译，两谱同时回滚。
- 13 项同步测试 + 2 项前端 store 测试覆盖；E2E 走通「改音符 → 切谱 → 撤销」。

## 11. 测试报告

| 层级 | 工具 | 结果 |
| --- | --- | --- |
| 后端单元+集成 | Pytest | **215 passed**（25.9s） |
| 前端单元 | Vitest | **39 passed**（5 文件） |
| 端到端 | Playwright Chromium | **6 passed**（10.2s） |
| 静态检查 | Ruff | **All checks passed** |
| 类型检查 | `tsc --noEmit` | **exit 0** |
| 生产构建 | `vite build` | 成功（JS 351 kB / gzip 105 kB） |
| 生产模式 | uvicorn + dist | `/`、`/scores`、`/keyboard`→HTML；`/api/v1/health`→JSON；`/api/v1/nope`→404 JSON |

## 12. 安全检查

| 项 | 结论 |
| --- | --- |
| 密钥入库 | ❌ 无（`.env`/`*.pem`/`*.key` 已忽略；提交前扫描通过） |
| 令牌存储 | Fernet 加密，含本机密钥回退 |
| 明文密码 | Navidrome 密码仅换 token+salt，测试后从 config 移除 |
| 令牌回传 | 任何接口不返回 token |
| SSRF | 协议白名单 + 环回/元数据拒绝 + 逐解析地址校验（9 项测试） |
| 上传 | 大小 + 扩展名 + 内容探测；不经同意不上传 |
| 平台合规 | Spotify 永久阻断 AI；Apple 不下载流；网易云/QQ 无逆向 |
| 错误泄漏 | 5xx 只记日志，响应不含堆栈 |

## 13. GitHub 地址

```
https://github.com/engernages-lab/03
```

- 远程检查：`git ls-remote` 返回 0 条引用 → **仓库为空**，无既有内容需要保留，不会覆盖其他项目。
- 本地 `main` 已提交（`e4105db`，183 文件 / 2.02 MB）。
- **Push 未执行**：任务书要求「由用户授权后执行 Push」。

## 14. 公开部署地址

**未部署。** 原因：缺少托管账号与凭据。任务书明确禁止"只提供本地地址并称为公开部署完成"，
因此此处如实标注为未完成。

已具备的部署产物：

| 文件 | 用途 |
| --- | --- |
| `backend/Dockerfile` | 后端镜像（内含可选前端） |
| `docker-compose.yml` | 单服务一键启动 |
| `render.yaml` | Render Blueprint |
| `frontend/vercel.json` | 前端分离部署 |
| `.github/workflows/ci.yml` | CI 全链路 |
| `docs/deployment.md` | 部署步骤与自检清单 |

本地生产模式已实测（见 §11），说明部署产物可用；**只差托管凭据**。

## 15. 已知限制

1. **无内置扒谱模型**：音频只做信号分析（BPM/起音/能量），作业终态 `analysis_only`、`events_produced=0`，不生成任何音符。
2. Apple Music / Spotify 未做真实账号验证（缺凭据）；网易云/QQ 无官方接口。
3. Navidrome 未连真实实例（协议层已按官方 API 实现并 Mock 验证）。
4. 多速度 MIDI 仅记录首个 tempo 为文档速度（时间轴按真实 tempo map 换算）。
5. 变音拼写默认升号，可配置 `flat`。
6. 撤销栈仅前端，刷新后清空（文档本身已持久化）。
7. 多轨数字谱合并显示，未做声部分行。
8. 本地"文件夹授权扫描"未实现（当前为文件选择上传）。
9. Subsonic 播放代理未做 Range 透传。
10. Docker 镜像未实际构建（本机无 Docker）。

## 16. 下一阶段计划（V1.0-B）

1. 接入真实扒谱模型（音高/节奏识别），输出带 `confidence` 的候选事件，人工确认后写入文档。
2. 补齐 Apple Music（MusicKit 前端）与 Spotify 真机联调。
3. 数字谱声部分行、拖拽编辑、连音符号合并。
4. 本地目录授权扫描（File System Access API）。
5. 多速度（tempo map）编辑与显示。
6. 部署到正式环境 + 域名 + HTTPS + 备份策略。

## 17. 最终验收结论

### CONDITIONAL PASS

**PASS 的部分**：核心架构、六大 Skill、MusicDocument、键盘、MIDI、音频管线、
格子谱、数字谱与双格式同步、统一曲库、播放器、资格判断、数据库与迁移、
260 项自动化测试、本地生产模式与部署产物 —— 全部完成并有三方证据（测试输出、
真实 HTTP 请求、8 张界面截图）。

**CONDITIONAL 的部分**：

- 公网部署未执行（无托管凭据）；
- GitHub Push 未执行（待用户授权）；
- Apple Music / Spotify / Navidrome 真实账号联调缺失（无凭据/实例）；
- 网易云、QQ 音乐无官方接口，按政策如实标注不可用。

**FAIL 判定不成立**：核心功能不存在严重缺陷，所有未完成项均已明确记录且不谎报。

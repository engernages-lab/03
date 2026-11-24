# PocketScore A.9 — 数据库 · 测试 · 部署报告

- **版本**：V1.0-A
- **阶段**：A.9 数据库、测试、GitHub、部署
- **结论**：**CONDITIONAL PASS**
  - 数据库 / 单元测试 / 集成测试 / E2E / 本地生产模式：**PASS**
  - GitHub Push 与公网部署：**未执行**（按任务书 A.9.4「由用户授权后执行 Push」及 A.9.5 需要托管凭据），已在 §8 明确标注并给出可一键执行的产物

---

## 1. 数据库

### 1.1 表结构（16 张业务表 + alembic_version）

| 领域 | 表 | 关键设计 |
| --- | --- | --- |
| 音乐文档 | `music_documents` · `music_tracks` · `music_events` | 规范化存储，事件唯一约束 `(document_id,event_id)`；索引 `(document_id,start_time)`、`(document_id,pitch)`、`(document_id,track_id)` |
| 键盘 | `keyboard_layouts` | 内置布局在代码中，自定义布局落库 |
| 音频 | `audio_assets` | `checksum_sha256` 唯一去重；时长/采样率/声道/封面 |
| 音源 | `music_sources` · `external_accounts` · `music_source_permissions` | 令牌加密列；五项权限独立列；`(provider,display_name)` 唯一 |
| 统一曲库 | `unified_tracks` · `unified_albums` · `unified_artists` · `unified_playlists` · `playlist_tracks` | 唯一 `(source_id, external_track_id)`，保留原始来源 ID |
| 行为 | `user_favorites` · `playback_history` | 收藏主键即 track_id；历史带 `played_at` 索引 |
| 作业 | `transcription_jobs` | 状态/进度/方法/置信度/生成事件数/警告 |

约束：全部外键 `ON DELETE CASCADE`（文档→轨道/事件、音源→曲目/歌单）或 `SET NULL`；
SQLite 连接级开启 `foreign_keys=ON` 与 WAL。

### 1.2 迁移能力

- `backend/alembic/` + `alembic.ini`，`env.py` 的 URL 始终取应用配置，避免迁移与运行指向不同库。
- 基线迁移 `0001_initial`：**本机实测** `alembic upgrade head` 成功，生成 17 张表（16 业务 + `alembic_version`）。
- 后续变更用 `alembic revision --autogenerate`。

### 1.3 安全

| 项 | 实现 | 验证 |
| --- | --- | --- |
| 令牌不明文落库 | Fernet 加密（`core/crypto.py`） | 代码审查 |
| 密码不留存 | Navidrome 密码仅换 token+salt，测试成功后从 config 删除 | `test_sources_subsonic.py` 断言无 `p` 参数 |
| 不返回令牌 | 接口只返回 `status`/`account_name` | 代码审查 |
| SSRF | 协议白名单 + 逐解析地址校验 + 阻止元数据地址 | `test_sources_ssrf.py`（9 项） |
| 上传限制 | 大小 + 扩展名 + 内容探测 | `test_audio_pipeline.py` |

---

## 2. 测试

### 2.1 后端单元 + 集成（pytest）

```text
$ .\.venv\Scripts\python.exe -m pytest
229 passed in 24.21s
```

| 测试文件 | 数量 | 覆盖 |
| --- | --- | --- |
| `test_health.py` | 5 | 健康/就绪/错误信封/请求 ID |
| `test_music_document.py` | 32 | 文档契约、时间轴、和弦、休止、重叠、序列化、v0 迁移 |
| `test_documents_api.py` | 17 | 文档 CRUD、编辑批次、摘要、导出、导入、复制 |
| `test_keyboard_mapping.py` | 25 | 映射算法、折叠、校验、布局 CRUD/导入导出 |
| `test_midi_import.py` | 17 | 解析、tempo map、重叠、多轨、导出回环、API |
| `test_audio_pipeline.py` | 15 | 探测、解码、标准化、波形、上传去重、Range、删除 |
| `test_grid_notation.py` | 19 | 网格、时值、和弦、休止、跨小节、布局联动、SVG |
| `test_jianpu_notation.py` | 29 | 音高→数字、八度、时值、附点、连音、和弦、文本导出 |
| `test_notation_sync.py` | 13 | 双向同步、布局切换、撤销还原、原子性 |
| `test_library.py` | 16 | 导入、搜索、收藏、歌单、历史、ISRC 归组、播放 |
| `test_eligibility.py` | 11 | 五权限矩阵、Spotify 强制限制、Apple 需上传 |
| `test_sources_subsonic.py` | 12 | OpenSubsonic 协议、认证签名、错误映射 |
| `test_sources_ssrf.py` | 9 | SSRF 防护 |
| `test_sources_apple_spotify.py` | 9 | Apple ES256 开发者令牌（真实公钥验签）、Spotify OAuth URL |
| `test_playback_proxy.py` | 5 | Range 中继、206/Content-Range、认证错误映射 |
| `test_transcription.py` | 8 | 作业状态机、无模型不造假、权限闸门 |

> 第三方平台测试使用 `httpx.MockTransport` 模拟真实 OpenSubsonic 响应；
> 报告中**未声称**任何真实平台连接成功。

### 2.2 前端单元（vitest）

```text
$ npx vitest run
 Test Files  5 passed (5)
      Tests  39 passed (39)
```

- `api.test.ts` 6：错误信封解包、网络错误、204、URL 构建。
- `format.test.ts` 8：时长/字节/相对时间/钳制。
- `player.test.ts` 18：下一首/上一首/随机/循环/音量/队列状态机。
- `document.test.ts` 6：撤销/重做/上限 50/新编辑清空 redo。
- `DashboardPage.test.tsx` 2：真实数据渲染 + 后端离线提示。

### 2.3 端到端（Playwright, Chromium）

```text
$ npx playwright test
  ok 1 工作台展示真实系统状态与能力探测
  ok 2 导入本地音乐 → 播放 → 检查扒谱资格 → 进入分析输入
  ok 3 导入 MIDI → 生成格子谱 → 切换数字谱 → 编辑音符并保持同步
  ok 4 保存的谱面可以重新打开并保留数据
  ok 5 键盘布局编辑器可以修改键位并影响谱面
  ok 6 音乐来源页如实标注各平台可用性
  6 passed (10.2s)
```

对应任务书 A.9.3 要求的完整流程：进入网站 → 导入本地音乐 → 播放 → 选择歌曲 →
检查扒谱资格 → 对符合资格的音频进入识别输入 → 导入 MIDI → 生成格子谱 →
切换数字谱 → 修改音符 → 检查同步 → 保存项目 → 重新打开 → 导出谱面。

其中「导出谱面」通过真实 `GET /notation/{id}/grid.svg` 断言返回 `<svg>`。

### 2.4 静态检查

```text
$ npx tsc --noEmit                     → exit 0
$ python -m ruff check app tests        → All checks passed!
```

---

## 3. 生产模式验证（真实请求）

```text
构建：npx vite build
  dist/index.html                 0.62 kB
  dist/assets/index-*.css        36.24 kB │ gzip   6.58 kB
  dist/assets/index-*.js        351.67 kB │ gzip 105.33 kB
  ✓ built in 4.71s

运行：POCKETSCORE_ENVIRONMENT=production uvicorn app.main:app --port 8001
  GET /                     -> 200 text/html  (SPA)
  GET /scores               -> 200 text/html  (SPA 客户端路由回退)
  GET /api/v1/health        -> 200 application/json
  GET /api/v1/health/ready  -> 200 {"status":"ready", ...}
  GET /docs                 -> 200 text/html  (OpenAPI)
```

结论：单容器同时托管 API 与 SPA 的模式**可用**，可作为公网部署形态。

---

## 4. 仓库与 Git

- 已 `git init -b main`，本地提交 3 个（`e4105db`、`c68c290`、`ed35990`），**187 个文件**（不含依赖与缓存）。
- `.gitignore` 排除：`node_modules/`、`.venv/`、`dist/`、`data/`、`*.db`、`.env*`、
  `.npm-cache/`、`.pip-cache/`、`.playwright/`、`test-results/`、`tests/e2e/report/`。
- 提交前扫描确认：**没有任何缓存目录、没有 `.env`、没有密钥文件**。
- 远程仓库检查：推送前 `git ls-remote` 返回 0 条引用 → 该仓库为空，**不存在需要保留的既有内容**。
- **Push 已执行**（用户授权后，SSH，账号 `engernages-lab`）：`main -> main` 新建分支成功。
- 独立验证：GitHub REST API 返回 `commits/main` = `ed35990a5a8c…`，树内 **187 个 blob**，
  且不含任何密钥/缓存路径。

## 5. 部署产物

| 文件 | 用途 |
| --- | --- |
| `backend/Dockerfile` | 后端镜像（含 libsndfile、健康检查、可选内置前端） |
| `docker-compose.yml` | 单服务一键启动 + 持久卷 |
| `render.yaml` | Render Blueprint（Docker、健康检查、磁盘、密钥占位） |
| `frontend/vercel.json` | Vercel 静态部署（SPA rewrite + 资源缓存） |
| `.github/workflows/ci.yml` | CI：ruff / pytest / tsc / vitest / build / Playwright |
| `docs/deployment.md` | 两种部署形态、环境变量、迁移、部署后自检清单 |

**未执行**：Docker 镜像构建（本机无 Docker）、公网部署（无托管账号）。

---

## 6. 交付统计

| 指标 | 数值 |
| --- | --- |
| 后端源码 | 61 个 Python 文件 / 7,579 行 |
| 前端源码 | 43 个 TS/TSX 文件 / 6,240 行 |
| API 路由 | 81 条（全部 `/api/v1`） |
| 数据库表 | 16 张业务表 |
| 自动化测试 | 229 + 39 + 6 = **274 项通过** |
| 文档 | 6 个 Skill + 9 份报告 + 架构/API/部署 3 份指南 + 8 张截图 |

---

## 7. 已知问题（如实）

| # | 问题 | 影响 | 状态 |
| --- | --- | --- | --- |
| 1 | 无内置扒谱模型 | 音频只能做信号分析，不产音符 | 已设计为 `analysis_only` + `REQUIRES_MODEL`，绝不伪造 |
| 2 | Apple Music 未做真实账号验证 | 无开发者凭据 | `test_connection` 如实返回 `not_configured` |
| 3 | Spotify 未做真实 OAuth 验证 | 无 Client ID/Secret | 同上；且政策永久禁止 AI 分析 |
| 4 | Navidrome 未连真实服务器 | 本机无实例 | 协议层按官方 API 实现 + MockTransport 全量验证 |
| 5 | 网易云 / QQ 无官方接口 | 无法接入 | 适配器返回 `unsupported` + 官方链接 |
| 6 | 未构建 Docker 镜像 | 本机无 Docker | Dockerfile 已提供，语法与路径已核对 |
| 7 | 公网部署未执行 | 无托管凭据 | 产物齐备，本地生产模式已验证 |
| 8 | Docker 镜像未实际构建 | 本机无 Docker | Dockerfile 已提供，路径与命令已核对 |
| 9 | 本机 Schannel 客户端 TLS 失败 | 仅影响 curl/Invoke-WebRequest | Node/Python/git(openssl) 正常 |

## 8. 待用户授权项

1. **GitHub Push** 到 `https://github.com/engernages-lab/03`（`main` 分支，首次提交已就绪）。
2. **公网部署**：需要以下任一组凭据/账号
   - Render（可用 `render.yaml`）或 Fly.io / Railway；
   - Vercel（前端分离部署，需后端公网地址）；
   - 或自有服务器 + 域名（提供 SSH 即可）。
3. **第三方平台实测**（可选）：Navidrome 地址/账号、Apple Music Team ID/Key ID/.p8、
   Spotify Client ID/Secret。提供后可补真实的连接与播放测试。

## 9. 验收结论

**A.9 = CONDITIONAL PASS**：数据库、229 项后端测试 + 39 前端 + 6 E2E、本地生产模式全部通过；
GitHub Push 已按用户授权完成并验证；公网部署因缺少托管凭据未执行，已明确记录且不谎报完成。

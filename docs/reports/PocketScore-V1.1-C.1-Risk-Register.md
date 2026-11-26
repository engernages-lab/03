# PocketScore AI · V1.1-C.1 生产风险登记册（Risk Register）

- **基准**：`pocketscore-v1.1-b @ afe0086`
- **分级**：P0 阻断公开部署 / P1 严重影响稳定性或数据安全 / P2 公开前应解决 / P3 后续优化
- **原则**：每条风险都附代码或实测证据；未验证项单独标注，不冒充已解决

---

## 汇总

| 等级 | 数量 | 关键项 |
| --- | --- | --- |
| P0 | 3 | 前端无 API 地址、Railway 启动不兼容、CORS 未配置 |
| P1 | 11 | 无认证、无限流、并发无上限、上传全量入内存、SQLite 单点、密钥默认值、SSRF 默认开、无任务超时、冷启动、sourcemap、无备份 |
| P2 | 7 | 位图 PDF、无对象存储、无指标、迁移不自动、ffmpeg 4.2.2、下载落盘、无多用户隔离 |
| P3 | 5 | 跨浏览器、CDN、文档、日志保留、成本可观测 |

---

## P0 · 阻断公开部署

### R-P0-01 前端生产构建没有 API 地址

| 项 | 内容 |
| --- | --- |
| 描述 | GitHub Pages 构建读取仓库变量 `VITE_API_BASE_URL`，当前未设置 → `API_BASE=""` → 所有请求打到 `https://engernages-lab.github.io/api/v1/...`（不存在） |
| 影响 | 线上站点只能显示静态预览，上传/扒谱/保存/导出全部失败 |
| 证据 | `.github/workflows/deploy-pages.yml:48` `VITE_API_BASE_URL: ${{ vars.VITE_API_BASE_URL }}`；`frontend/src/lib/api.ts:8-10` 空值即同源 |
| 解决阶段 | C.2 |
| 验收 | 线上执行一次真实扒谱：上传 → 作业完成 → 打开谱面，Network 面板中请求域名为后端域名 |

### R-P0-02 Railway 无法直接构建/启动后端

| 项 | 内容 |
| --- | --- |
| 描述 | (a) Dockerfile 位于 `backend/Dockerfile`，Railway 默认只探测仓库根；(b) `CMD` 硬编码 `--port 8000`，Railway 注入 `$PORT` 时服务不可达 |
| 影响 | 部署直接失败或健康检查永远超时 |
| 证据 | 仓库无 `railway.json`/`nixpacks.toml`/根 `Dockerfile`；`backend/Dockerfile:39` `--port 8000`；`config.py:42` `port=8000` 未参与 CMD |
| 解决阶段 | C.2 |
| 验收 | Railway 部署成功，公网 `GET /api/v1/health` 200；日志显示实际监听端口 = `$PORT` |

### R-P0-03 CORS 默认只允许 localhost

| 项 | 内容 |
| --- | --- |
| 描述 | `cors_origins` 默认 `localhost:5173/4173`，生产未覆盖时 Pages 源被浏览器拦截 |
| 影响 | 前端所有跨域请求 preflight 失败（表现为"API 未连接"） |
| 证据 | `app/core/config.py:43-50`；`.env.example` 仅示例 dev 源 |
| 解决阶段 | C.2 |
| 验收 | 浏览器控制台无 CORS 报错；`curl -H "Origin: https://engernages-lab.github.io" -I /api/v1/health` 返回 `access-control-allow-origin` |

---

## P1 · 严重影响稳定性或数据安全

### R-P1-01 完全没有任何认证

| 项 | 内容 |
| --- | --- |
| 描述 | 无用户体系、无 token 校验；所有文档/项目对所有访问者可见可删 |
| 影响 | 公开后任意人可读取、清空他人数据，可使用 AI 推理算力 |
| 证据 | 全仓无 auth middleware/依赖；`main.py:32` 仅设置 `WWW-Authenticate` 响应头常量 |
| 解决阶段 | C.5（P0 性质，但可用"临时口令 + 仅本人使用"过渡） |
| 验收 | 未带凭据请求返回 401；两个账号互相看不到对方项目 |

### R-P1-02 无限流、无请求体上限

| 项 | 内容 |
| --- | --- |
| 描述 | 无速率限制、无 Body 大小上限；`await file.read()` 先把整个文件读进内存，之后才比对 200 MB |
| 影响 | 单个脚本可造成内存耗尽（DoS）；一次 5 GB POST 会在校验前触发 OOM |
| 证据 | `api/v1/audio.py:75`；`assets.py:144` 校验在读入之后；全仓无 `Content-Length` 预检、无限流中间件 |
| 解决阶段 | C.5 |
| 验收 | 超过 `max_upload_mb` 的请求在读取前被 413 拒绝；每分钟请求数超阈值返回 429 |

### R-P1-03 推理并发无上限

| 项 | 内容 |
| --- | --- |
| 描述 | 每个作业经 `run_in_threadpool` 执行，无信号量；anyio 默认线程池上限 40 |
| 影响 | 40 个并发作业 × ~200–260 MB ≈ 8–10 GB 内存峰值 → 实例 OOM 崩溃 |
| 证据 | `api/v1/transcription.py:106-107` `run_in_threadpool(_run_sync_job, job_id)`；无 semaphore/队列 |
| 解决阶段 | C.4 |
| 验收 | 并发 5 个作业时进程 RSS 不超过设定上限；第 3 个作业进入排队并回传 `queued` 状态 |

### R-P1-04 `session_secret` 默认值无生产校验

| 项 | 内容 |
| --- | --- |
| 描述 | 默认 `change-me-in-production`，生产启动不报错 |
| 影响 | 若忘记配置，签名类功能使用公开已知密钥 |
| 证据 | `config.py:72`；`is_production` 属性存在但未被用于校验 |
| 解决阶段 | C.2 |
| 验收 | `ENVIRONMENT=production` 且密钥为默认值时启动失败并给出明确错误 |

### R-P1-05 令牌加密密钥随容器重建丢失

| 项 | 内容 |
| --- | --- |
| 描述 | `token_encryption_key` 为空时派生自机器本地文件；容器重建即换键 |
| 影响 | 已保存的第三方令牌全部无法解密（Apple/Spotify/Navidrome 需重新授权） |
| 证据 | `config.py:69-71` 注释与实现；无外部 KMS 集成 |
| 解决阶段 | C.2 |
| 验收 | 重启/重新部署后已存令牌仍能解密（用固定 key 实测一次） |

### R-P1-06 SSRF 面默认开启

| 项 | 内容 |
| --- | --- |
| 描述 | `allow_private_network_sources=True` 默认允许访问私有网段 |
| 影响 | 云端可被用于探测内网/云元数据（169.254.169.254） |
| 证据 | `config.py:73`；`docker-compose.yml` 也设为 true |
| 解决阶段 | C.2（生产设 false） |
| 验收 | 生产环境请求内网地址返回 403；SSRF 测试用例全绿 |

### R-P1-07 SQLite 单文件、无备份

| 项 | 内容 |
| --- | --- |
| 描述 | 元数据与作业状态全在单个 SQLite 文件；无备份脚本/策略 |
| 影响 | 卷丢失 = 全部项目丢失；无法水平扩展；并发写有锁竞争 |
| 证据 | `config.py:53` 默认 sqlite；Dockerfile `VOLUME /data`；全仓无备份代码 |
| 解决阶段 | C.3 |
| 验收 | 每日自动备份可在 10 分钟内恢复出完整数据；迁移 PG 后写入并发无锁错误 |

### R-P1-08 容器 Python 版本与本机不一致

| 项 | 内容 |
| --- | --- |
| 描述 | 容器 `python:3.11-slim`，本地 venv 3.9.13；`requirements.txt` 按 3.9 锁定（如 `music21<9`、`greenlet<3.3`） |
| 影响 | 3.11 下依赖解析结果与本地不同（basic-pitch 会拉 TensorFlow 而非 onnxruntime），镜像体积与推理路径都可能变化 |
| 证据 | `backend/Dockerfile:5`；`requirements.txt` 顶部注释"Target interpreter: CPython 3.9" |
| 解决阶段 | C.2 |
| 验收 | 镜像内 `python -V` 与 CI 一致；`/transcription/models` 报告的 runtime 与预期一致 |

### R-P1-09 生产构建发布 sourcemap

| 项 | 内容 |
| --- | --- |
| 描述 | `vite.config.ts` `build.sourcemap: true`，Pages 上线会公开 `.map`（1.5 MB） |
| 影响 | 完整源码可被还原（非密钥，但暴露实现细节） |
| 证据 | `vite.config.ts:57`；构建输出 `map: 1,514.24 kB` |
| 解决阶段 | C.2 |
| 验收 | 生产产物无 `.map`，构建仍可用 `--sourcemap` 调试 |

### R-P1-10 冷启动首个作业 7.6 s

| 项 | 内容 |
| --- | --- |
| 描述 | 首次作业承担 numba JIT（`detect_onsets` 3.67 s）+ 库导入 + ORT 预热 |
| 影响 | 首批用户体验差；若健康检查依赖"能跑一次推理"会被误判 |
| 证据 | 实测：首作业 7.6 s，稳态 0.51–0.57 s；`detect_onsets` 首调用 3.67 s，次调用 0.01 s |
| 解决阶段 | C.2 |
| 验收 | 启动后 3 s 内完成预热；首个真实作业 ≤1 s |

### R-P1-11 无任务超时机制

| 项 | 内容 |
| --- | --- |
| 描述 | `max_audio_duration_seconds=600`，但作业无执行超时；FFmpeg 解码验证硬编码 120 s |
| 影响 | 畸形文件可长期占用线程；用户取消后计算不中断（cancel 只改状态） |
| 证据 | `transcription.py` 无超时；`probe.py:207` 硬编码 `timeout=120`；`cancel` 仅置状态 |
| 解决阶段 | C.4 |
| 验收 | 超过 N 秒的作业被标记 `failed(TIMEOUT)` 且线程释放 |

---

## P2 · 公开前应解决

| 编号 | 风险 | 证据 | 影响 | 阶段 |
| --- | --- | --- | --- | --- |
| R-P2-01 | PDF 为位图非矢量 | `pdf.ts` DCTDecode 嵌入 | 放大失真；不能用于印刷级 | C.6 |
| R-P2-02 | 无对象存储，音频与 DB 同卷 | `storage_dir` 与 DB 同 `/data` | 备份/扩容耦合，迁移成本高 | C.3 |
| R-P2-03 | 无指标/告警（仅结构化日志） | 全仓无 prometheus/otel | 线上故障不可见 | C.7 |
| R-P2-04 | Alembic 迁移不随部署执行 | 依赖 `sync_additive_columns` 兜底 | 改类型/删列时兜底不生效 | C.3 |
| R-P2-05 | FFmpeg 4.2.2（2019） | `imageio-ffmpeg` 捆绑版本 | 新编码器/容器支持有限 | C.3 |
| R-P2-06 | 浏览器落盘未验证（TD-06） | 三种下载机制均 `canceled` | 用户可能拿不到文件 | C.6 |
| R-P2-07 | 无多用户隔离模型 | 无 user_id 外键 | 无法做 SaaS 多租户 | C.5 |

---

## P3 · 后续优化

| 编号 | 风险 | 说明 |
| --- | --- | --- |
| R-P3-01 | 仅 Chromium 自动化 | Firefox/WebKit 未测（TD-11） |
| R-P3-02 | Pages 无缓存头/CDN 策略 | 静态资源重复下载 |
| R-P3-03 | 单 worker 无优雅关闭 | 部署时在跑任务被中断 |
| R-P3-04 | 日志无保留策略 | 长期成本与合规 |
| R-P3-05 | 无成本可观测 | 无法按租户归集推理成本 |

---

## 与既有 TD 的映射

| 既有 | 本册编号 | 状态变化 |
| --- | --- | --- |
| TD-04 公网后端未部署 | R-P0-02 | 原因已具体化为 Dockerfile/PORT 两点 |
| TD-06 下载落盘 | R-P2-06 | 保持 CONDITIONAL |
| TD-09 位图 PDF | R-P2-01 | 保持 |
| TD-01b 真实录音精度 | — | 与部署无关，保留在 TECH-DEBT |
| TD-05 平台凭据 | R-P2-07 关联 | 无认证时平台接入无意义 |

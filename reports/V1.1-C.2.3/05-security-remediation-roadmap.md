# PocketScore AI V1.1-C.2.3.4 · 安全整改路线图

> 输入：`05-security-baseline-audit.md`（2026-11-28，结论 BLOCKED，P0×2 / P1×5 / P2×6 / P3×3）。
> 本文件只做计划，**不含任何代码改动**。每项给出目标、影响范围、修改文件、推荐实现、
> 兼容性风险、测试要求、验收标准、是否阻塞后续阶段。

## 总览

| 阶段 | 主题 | 覆盖风险 | 是否阻塞开放试用 |
| --- | --- | --- | --- |
| C.2.3.4.2 | 存储边界与路径安全 | P1-1、P1-2、P2-1 | 否（单租户也受益） |
| C.2.3.4.3 | 上传、限流、供应链、运行加固 | P2-3、P2-4、P2-5、P2-6、P3-1 | 否 |
| C.2.3.4.4 | 身份、所有权与访问控制 | **P0-1、P0-2**、P1-4、P1-5 | **是** |
| C.2.3.4.5 | 备份加密与恢复演练 | P1-3 | 否（但强烈建议） |

建议顺序：**4.4 优先**（P0），4.2 可与 4.4 并行（都动文件读取链路，需协调），
4.3 独立，4.5 收尾。

---

## C.2.3.4.2 · 存储边界与路径安全

### R-01 存储根包含性校验（P1-1）

| 项 | 内容 |
| --- | --- |
| 目标 | 任何从数据库或请求得到的路径，`resolve()` 后必须仍位于存储根内 |
| 影响范围 | `app/services/audio/assets.py`（`absolute_path`）、`app/services/music_document/*`（MIDI 导出）、`app/api/v1/{audio,notation,midi,playback}.py` |
| 修改文件 | `app/services/audio/assets.py`、新增 `app/core/paths.py`（`safe_join(root, relative)` + `assert_within`） |
| 推荐实现 | 统一 `safe_join()`：`normcase(abspath(resolve(root, rel)))` 前缀比较 + `os.path.commonpath` 双校验；越界抛 `ValidationAppError(code="PATH_OUTSIDE_STORAGE", 400)`，**错误体不含绝对路径** |
| 兼容性风险 | 现有 `stored_path` 全部是 `audio/xx/<sha>.wav` 相对路径 → 正常数据零影响；Windows 反斜杠历史数据需归一化 |
| 测试要求 | 复用审计中的 6 组篡改探针（`../`、反斜杠、绝对路径、空串、深层 `../`、符号链接），全部必须 4xx；合法路径仍 200 |
| 验收标准 | 6/6 逃逸用例返回 400/404 且响应体不含磁盘路径 |
| 是否阻塞 | 否 |

### R-02 错误信息脱敏（P1-2）

| 项 | 内容 |
| --- | --- |
| 目标 | 客户端错误体不出现服务器绝对路径、堆栈、内部文件名 |
| 影响范围 | `app/core/errors.py`、`app/api/v1/audio.py`（`AUDIO_PROBE_FAILED.details.reason`）、`probe.py` 抛错处 |
| 修改文件 | `app/core/errors.py`（新增 `scrub_paths()`）、`app/services/audio/probe.py` |
| 推荐实现 | 统一在 `_error_response` 前把 `details` 里的绝对路径替换为 `<redacted>`；`reason` 只保留错误类别（如 `decode_failed`），完整原因进服务端日志 |
| 兼容性风险 | 前端若依赖 `details.reason` 文案提示，需要同步（前端只展示 message，风险低） |
| 测试要求 | 对空路径、损坏文件、越界路径三种失败各断言响应体不含 `storage` 根字符串 |
| 验收标准 | 响应体 grep 不到任何绝对路径；服务端日志仍保留完整原因 |
| 是否阻塞 | 否 |

### R-03 上传文件名清洗（P2-1）

| 项 | 内容 |
| --- | --- |
| 目标 | `filename` 只用于展示与扩展名判定，不得含路径分隔符/控制字符/超长 |
| 修改文件 | `app/services/audio/assets.py`（`ingest_*` 入口）、`app/api/v1/audio.py` |
| 推荐实现 | `sanitize_filename()`：取 `PurePath(name).name`、剥离 `\x00`-`\x1f`、长度截断 255、保留原扩展名 |
| 兼容性风险 | 已入库的旧文件名不追溯（只影响新上传） |
| 测试要求 | `../../x.wav`、`C:\x.wav`、`evil\x00.wav`、300 字符名 → 落库为纯文件名 |
| 验收标准 | 落库 `filename` 不含 `/`、`\`、控制字符；`stored_path` 不受影响 |
| 是否阻塞 | 否 |

---

## C.2.3.4.3 · 上传、限流、供应链与运行加固

### R-04 接口级限流（P2-3）

| 项 | 内容 |
| --- | --- |
| 目标 | 除门禁失败限流外，对上传与推理入口做按 IP 的速率限制 |
| 修改文件 | `app/core/access_gate.py` 或新增 `app/core/ratelimit.py`、`app/main.py` |
| 推荐实现 | 令牌桶（内存），上传 10/min/IP、推理 5/min/IP；超限 429 `RATE_LIMITED`；**记录已知局限：多副本不共享、重启清零** |
| 兼容性风险 | 单用户正常使用不会触发；压测脚本需知情 |
| 测试要求 | 连续请求触发 429；不同 IP 互不影响；限流窗口滑动正确 |
| 验收标准 | 单测覆盖 + 手工 20 连击验证 |
| 是否阻塞 | 否 |

### R-05 CORS 收紧（P2-4）

| 项 | 内容 |
| --- | --- |
| 目标 | 明确 methods/headers 白名单，避免 `*` + credentials 组合 |
| 修改文件 | `app/main.py` |
| 推荐实现 | `allow_methods=["GET","POST","PUT","PATCH","DELETE","OPTIONS"]`、`allow_headers=["Authorization","Content-Type","X-Request-Id","Range"]`、`expose_headers=["X-Request-Id","Content-Range"]` |
| 兼容性风险 | 前端新增自定义头需同步；`Range` 播放依赖 |
| 测试要求 | 现有 CORS 测试 + 浏览器预检 |
| 验收标准 | `OPTIONS` 预检返回精确 allow 列表 |
| 是否阻塞 | 否 |

### R-06 供应链硬pin（P2-5）

| 项 | 内容 |
| --- | --- |
| 目标 | 基础镜像与 Actions 固定到 digest/SHA；依赖可复现；CI 有 CVE 扫描 |
| 修改文件 | `backend/Dockerfile`、`.github/workflows/*.yml`、`backend/requirements.txt` |
| 推荐实现 | 镜像 `python:3.11-slim@sha256:…`；Actions 用 commit SHA；加 `pip-audit` 步骤（失败不阻断，先告警） |
| 兼容性风险 | digest 更新需人工；Actions SHA 可读性差（加注释） |
| 测试要求 | 构建通过；`pip-audit` 输出入库为 artifact |
| 验收标准 | 无浮动 tag；CVE 报告存在 |
| 是否阻塞 | 否 |

### R-07 非 root 运行 + 安全响应头（P2-6 / P3-1）

| 项 | 内容 |
| --- | --- |
| 目标 | 容器非 root；补 HSTS/CSP/XCTO/XFO/Referrer-Policy |
| 修改文件 | `backend/Dockerfile`（`USER app`）+ `chown /data`、`app/main.py`（中间件） |
| 推荐实现 | 建 `app` 用户；`/data` 由启动脚本 `chown` 或 Railway Volume 权限预置（**需验证 Volume 迁移可行性**）；响应头中间件 |
| 兼容性风险 | **Volume 属主变更影响现有数据写入** → 必须在 staging 先验证，禁止直接上生产 |
| 测试要求 | 容器内 `id` 非 0；写入 `/data` 成功；响应头断言 |
| 验收标准 | `docker run … id -u` ≠ 0 且上传成功 |
| 是否阻塞 | 否（但 P2-6 建议在开放试用前完成） |

---

## C.2.3.4.4 · 身份、所有权与访问控制（**P0**）

### R-08 用户与会话基础

| 项 | 内容 |
| --- | --- |
| 目标 | 最小可用认证：注册（邀请制）、登录、登出、会话过期 |
| 影响范围 | 全部 `/api/v1/**`、前端登录页、数据库新增表 |
| 修改文件 | 新增 `app/models/user.py`、`app/core/security.py`、`app/api/v1/auth.py`、`alembic/versions/0003_users.py`、`app/main.py`、前端路由/状态 |
| 推荐实现 | 邮箱 + Argon2id 密码哈希；服务端会话（SQLite `sessions` 表，token 存哈希）；HttpOnly + Secure + SameSite=Lax Cookie；30 天滑动过期；登出即删会话；**邀请码**限制注册 |
| 兼容性风险 | 需要迁移；旧数据无 owner → 需要"归属迁移"策略（见 R-09） |
| 测试要求 | 注册/登录/登出/过期/错误密码/重复邮箱；Cookie 属性断言 |
| 验收标准 | 未登录访问受保护接口 → 401；登录后仅见自己数据 |
| 是否阻塞 | **是**（开放试用前必须） |

### R-09 资源所有权与查询过滤（P0-1）

| 项 | 内容 |
| --- | --- |
| 目标 | `AudioAsset`、`MusicDocument`、`TranscriptionJob`、`Playlist`、`KeyboardLayout` 全部带 `owner_id`，所有查询按 owner 过滤，所有按 ID 的读写做所有权断言 |
| 修改文件 | `app/models/*.py`（5 张表加列 + 索引）、`alembic/versions/0004_ownership.py`、`app/services/**`、`app/api/v1/**` |
| 推荐实现 | 注入 `current_user` 依赖；服务层强制 `where(owner_id == user.id)`；按 ID 的读取失败统一返回 **404**（不泄露存在性）；删除前校验所有权 |
| 兼容性风险 | **高**：旧数据需回填 owner（建议"首个管理员账户接管全部历史数据"），迁移必须可回滚；共享资产去重与 owner 冲突需决策（建议：`audio_assets` 全局去重 + 单独 `asset_owners` 关联表，或按 owner 分区） |
| 测试要求 | 双用户 A/B 矩阵：列、读、流、删、转录、导出、notation 全维度交叉访问必须 404/403；修改 URL 中 ID 无效化 |
| 验收标准 | 审计中的 SEC-04 探针全部由 200/204 变成 404；A 列表不含 B 任何对象 |
| 是否阻塞 | **是** |

### R-10 `/static` 收敛（P0-2）

| 项 | 内容 |
| --- | --- |
| 目标 | 不再整树暴露存储根；音频经带授权的 API 读取，或改用签名短期 URL |
| 修改文件 | `app/main.py`（移除整根挂载）、`app/api/v1/audio.py`（`/assets/{id}/stream` 已存在，补 Range 与所有权）、`app/api/v1/artwork` 新增 |
| 推荐实现 | 方案 A（推荐）：删除 `app.mount("/static", storage_path)`，`artwork` 走 `/api/v1/audio/assets/{id}/artwork` 校验所有权后返回文件；方案 B：保留 `/static` 但只挂 `artwork/` 且文件名不可枚举 |
| 兼容性风险 | 前端 `artwork_url`/`stream_url` 字段需改指向；历史 DB 里 `artwork_path` 存的是 `/static/...` → 需要兼容映射 |
| 测试要求 | `/static/**` 全部 404；`/assets/{id}/stream` 仅 owner 200，他人 404；匿名 401 |
| 验收标准 | 不再存在可枚举的静态音频路径 |
| 是否阻塞 | **是** |

### R-11 审计日志（P1-4）

| 项 | 内容 |
| --- | --- |
| 目标 | 记录"谁在何时对哪个对象做了什么"（登录、上传、删除、导出、恢复尝试） |
| 修改文件 | 新增 `app/models/audit.py`、`app/core/audit.py`、若干服务调用点 |
| 推荐实现 | 追加式 `audit_events` 表（user_id, action, object_type, object_id, ip, ua, ts, result），JSON 行日志双写；**不记录文件内容与 Token** |
| 兼容性风险 | 写放大；需索引与保留策略 |
| 测试要求 | 关键动作产生记录；敏感字段不出现 |
| 验收标准 | 删除/登录/上传可在日志中追溯 |
| 是否阻塞 | 否（但试用期强烈建议） |

### R-12 共享引用与删除保护（P1-5）

| 项 | 内容 |
| --- | --- |
| 目标 | 删除资产前确认无其它引用（文档内嵌、任务、播放列表） |
| 修改文件 | `app/services/audio/assets.py`、`app/services/music_document/repository.py` |
| 推荐实现 | 删除前扫描 `music_documents.source_metadata_json` 与 `transcription_jobs.asset_id`；有引用则 409 `ASSET_IN_USE`；或引入引用计数表 |
| 兼容性风险 | 现有前端删除流程需处理 409 |
| 测试要求 | 被引用资产删除返回 409；解除引用后可删 |
| 验收标准 | 不再产生悬空引用 |
| 是否阻塞 | 否 |

---

## C.2.3.4.5 · 备份加密与恢复演练

### R-13 备份加密（P1-3）

| 项 | 内容 |
| --- | --- |
| 目标 | 快照落盘即加密（数据库 + 文件），密钥与备份分离 |
| 修改文件 | `app/ops/project_backup.py`、`app/ops/database_backup.py`、`docs/operations/*.md` |
| 推荐实现 | `age`（推荐）或 `cryptography` AES-GCM 分块加密；密钥来自 `POCKETSCORE_BACKUP_KEY`（Railway 变量），**禁止与备份同目录**；恢复时先解密到临时目录再走现有校验 |
| 兼容性风险 | 旧明文快照需兼容读取；`prune` 需识别 `.age` 后缀 |
| 测试要求 | 加密→解密→恢复全链路；错误密钥必须明确失败；密文中不得出现明文音频头 |
| 验收标准 | 快照目录内无明文字节；恢复后哈希与原文一致 |
| 是否阻塞 | 否 |

### R-14 恢复演练与 RPO/RTO 实测（P3）

| 项 | 内容 |
| --- | --- |
| 目标 | 把设计目标变成实测数字 |
| 修改文件 | `docs/operations/storage-backup-recovery.md`、`reports/*` |
| 推荐实现 | 在 staging 用真实体量（当前 40 MB）跑一次端到端恢复，记录耗时 |
| 测试要求 | 记录恢复开始/结束时间与数据一致性结果 |
| 验收标准 | 文档中 RPO/RTO 标注为"实测"并附命令与时间 |
| 是否阻塞 | 否 |

---

## 阶段门禁

| 门禁 | 条件 |
| --- | --- |
| 进入 C.2.3.4.2 | ✅ 允许（审计已完成） |
| 进入 C.2.3.4.3 | ✅ 允许 |
| 进入 C.2.3.4.4 | ✅ 允许（且必须做） |
| 进入 C.2.3.4.5 | ✅ 允许 |
| **开放多用户试用** | ❌ 必须 R-08/R-09/R-10 全部完成且双用户矩阵测试通过 |
| **进入 C.2.4** | ❌ 当前不允许（P0 未清零） |

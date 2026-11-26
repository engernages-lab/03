# PocketScore AI · V1.1-C.1 实施路线图（C.2 – C.7）

- **输入**：[架构审计](PocketScore-V1.1-C.1-Architecture-Audit.md) 与 [风险登记册](PocketScore-V1.1-C.1-Risk-Register.md)
- **原则**：严格按依赖顺序推进；上一阶段验收未过不得进入下一阶段
- **禁止**：跨阶段提前上线；用 Mock 通过验收；降低既有测试标准

依赖链：`C.2 可上线` → `C.3 数据可靠` → `C.4 并发可控` → `C.5 安全可用` → `C.6 交付质量` → `C.7 可运维`

---

## C.2 后端生产基线（让服务真正跑在公网）

| 项 | 内容 |
| --- | --- |
| 1 目标 | Railway 上跑起真实 API，Pages 前端能连通；满足"单实例 + 持久卷 + 最低安全项" |
| 2 修改范围 | `backend/Dockerfile`（`$PORT`、启动预热、非 root 用户）、新增 `railway.json`（dockerfile 路径/健康检查/重启策略）、`app/core/config.py`（生产密钥强制校验）、`app/services/audio/transcription/inference.py`（模型单例预加载）、`app/main.py`（启动预热 + docs 关闭）、`vite.config.ts`（生产关闭 sourcemap） |
| 3 技术方案 | CMD 改 `sh -c "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"`；启动钩子中构造 `Model` 单例并跑一次 1 s 静音推理完成 numba/ORT 预热；`is_production` 时校验 `session_secret != 默认值` 且 `token_encryption_key` 非空 |
| 4 步骤 | 改 Dockerfile → 加 railway.json → 改 config 校验 → 加预热 → 本地 `docker build && docker run -e PORT=8080` 验证 → Railway 部署 → 配 CORS/密钥 → 配仓库变量 `VITE_API_BASE_URL` → 重跑 Pages 构建 |
| 5 数据迁移 | 无（继续 SQLite + 卷） |
| 6 安全要求 | `ALLOW_PRIVATE_NETWORK_SOURCES=false`；CORS 精确到 Pages 源；`/docs` 关闭；密钥只走平台变量 |
| 7 自检 | `/health` 200、`/health/ready` 全绿、日志为 JSON、启动 <5 s、预热完成日志 |
| 8 自动化测试 | 新增 `tests/test_production_config.py`（默认密钥启动失败、CORS 解析、PORT 读取）；既有 296 项保持全绿 |
| 9 E2E | 新增 `tests/e2e/remote.spec.ts`：以 `PSC_BASE_URL` 指向线上，跑上传→扒谱→打开谱面→导出 PNG |
| 10 验收 | 公网地址可完成一次真实扒谱；重启后项目仍在；首作业 ≤1 s；无 CORS 报错 |
| 11 回滚 | 保留前一镜像 tag；Pages 用 `git revert` 回上一构建；数据在卷中不受影响 |
| 12 报告 | `PocketScore-V1.1-C.2-Deployment-Report.md`（含公网 URL、冒烟截图、首作业耗时） |

关闭风险：R-P0-01/02/03、R-P1-04、R-P1-05、R-P1-06、R-P1-08、R-P1-09、R-P1-10。

---

## C.3 数据持久化（Postgres + 对象存储 + 备份）

| 项 | 内容 |
| --- | --- |
| 1 目标 | 元数据迁到 PostgreSQL，音频进对象存储或独立卷，具备可恢复备份 |
| 2 修改范围 | `requirements.txt`（`psycopg[binary]`）、`app/core/db.py`（连接池按引擎分支）、`app/services/audio/assets.py`（存储适配器抽象：本地/对象存储）、`alembic/env.py`（PG 兼容）、新增 `scripts/backup.py` |
| 3 技术方案 | 存储层接口 `StorageBackend{put,get,delete,url}`，本地与 S3 兼容两种实现；DB 只存 key；备份用 `pg_dump` + 音频增量同步 |
| 4 步骤 | 加驱动 → 迁移脚本 `alembic upgrade head` 在 PG 空库跑通 → 数据搬运脚本（SQLite→PG）→ 存储适配器切换 → 备份定时任务 → 恢复演练 |
| 5 数据迁移 | 一次性窗口：停写 → 导出 SQLite → 导入 PG → 校验行数与校验和 → 切 URL → 双读比对 → 完成 |
| 6 安全要求 | PG 连接串走平台变量；对象存储用最小权限凭据；备份加密 |
| 7 自检 | 迁移后 `music_documents`/`music_events` 行数一致；抽样文档 JSON 逐字节一致 |
| 8 自动化测试 | `tests/test_storage_backend.py`（两种实现同契约）；`tests/test_postgres_migration.py`（跳过需 PG 的用例时明确 `pytest.mark.skipif`） |
| 9 E2E | 同一批操作在 PG 后端跑一遍 workstation + export 套件 |
| 10 验收 | 杀掉实例重建后项目/音频完整；备份可在 10 分钟内恢复；并发 5 写无锁错误 |
| 11 回滚 | 保留 SQLite 只读副本 24 h；切回仅改 `DATABASE_URL` |
| 12 报告 | `PocketScore-V1.1-C.3-Persistence-Report.md` |

关闭风险：R-P1-07、R-P2-02、R-P2-04、R-P2-05。

---

## C.4 推理并发治理（队列、超时、配额）

| 项 | 内容 |
| --- | --- |
| 1 目标 | 并发可控、任务可取消、长任务有超时，内存不随并发线性爆炸 |
| 2 修改范围 | 新增 `app/services/jobs/queue.py`（进程内队列 + 信号量；预留 Redis 适配）、`app/api/v1/transcription.py`（入队、状态 `queued`、取消即中断）、`app/services/transcription.py`（超时与阶段检查点） |
| 3 技术方案 | 单进程：`asyncio.Semaphore(N=1..2)` + 有界队列（maxsize）+ 每任务 `asyncio.wait_for`；取消用 `threading.Event` 在阶段间检查；作业状态机加 `queued` |
| 4 步骤 | 定义队列接口 → 实现内存队列 → 接入上传/作业端点 → 加超时与取消 → 加队列长度上限与 429 → 压测 |
| 5 数据迁移 | `transcription_jobs` 增加 `queue_position`/`started_at`（可空，走自愈列） |
| 6 安全要求 | 队列长度上限防 DoS；取消仅限本人（依赖 C.5 认证） |
| 7 自检 | 并发 5 时第 3 个起 `queued`；取消后 2 s 内线程释放 |
| 8 自动化测试 | `tests/test_job_queue.py`（排队/取消/超时/并发上限），用假模型桩，不跑真推理 |
| 9 E2E | 连续提交 3 个作业，界面显示排队与进度，全部完成 |
| 10 验收 | 10 并发提交下进程 RSS ≤ 设定上限；无失败作业泄漏线程 |
| 11 回滚 | 环境变量 `POCKETSCORE_JOB_QUEUE=inline` 回到直接执行 |
| 12 报告 | `PocketScore-V1.1-C.4-Concurrency-Report.md`（含压测曲线） |

关闭风险：R-P1-03、R-P1-11。

---

## C.5 安全加固（认证、限流、体积上限、审计）

| 项 | 内容 |
| --- | --- |
| 1 目标 | 公开服务可用且不被滥用：每个用户只能访问自己的数据 |
| 2 修改范围 | 新增 `app/core/security.py`（会话/token）、`app/api/v1/auth.py`、`app/core/ratelimit.py`、所有资源路由加 `Depends(current_user)`、模型加 `owner_id`（迁移 `0003`） |
| 3 技术方案 | 邮箱魔法链接或 OAuth（二选一，需用户决定）；HttpOnly Cookie + CSRF；限流令牌桶（内存，预留 Redis）；上传先看 `Content-Length` 再流式读盘 |
| 4 步骤 | 用户表/会话 → 登录流 → 资源归属列 → 路由鉴权 → 限流 → 体积上限 → 越权测试 |
| 5 数据迁移 | 现有数据归到一个"迁移用户"；`owner_id` 可空一段时间后回填 |
| 6 安全要求 | 密码不落库（若用密码则 argon2）；令牌加密（复用 Fernet）；日志脱敏 |
| 7 自检 | 未登录 401；A 用户访问 B 项目 404；超限 429；超大 body 413 |
| 8 自动化测试 | `tests/test_auth.py`、`tests/test_ownership.py`、`tests/test_ratelimit.py`、`tests/test_body_limit.py` |
| 9 E2E | 两账号并行：各自看到自己的谱面，互相不可见 |
| 10 验收 | 越权测试全绿；限流阈值可配置；审计日志记录登录与删除 |
| 11 回滚 | 保留 `POCKETSCORE_AUTH_MODE=disabled`（仅私有部署） |
| 12 报告 | `PocketScore-V1.1-C.5-Security-Report.md` |

关闭风险：R-P1-01、R-P1-02、R-P2-07。

---

## C.6 交付质量（导出落盘、矢量 PDF 评估、跨浏览器）

| 项 | 内容 |
| --- | --- |
| 1 目标 | 用户能可靠拿到文件；矢量 PDF 有明确路线；跨浏览器行为已知 |
| 2 修改范围 | `frontend/src/lib/exportScore.ts`（保存编排）、`ExportScoreDialog.tsx`（失败重试与说明）、`pdf.ts`（可选矢量路径）、Playwright 项目矩阵 |
| 3 技术方案 | 落盘：`showSaveFilePicker` 优先 + `<a download>` 兜底 + 失败时提供"复制地址/重新生成"；矢量 PDF：先用 PDF 原生文本 + 矢量矩形绘制 grid（中文需字体子集，评估 `fontkit`/`pdf-lib`） |
| 4 步骤 | 真实桌面手工验证落盘（Chrome/Edge/Firefox）→ 记录矩阵 → 实现矢量 grid 页 → 与位图 PDF 并存（用户可选） |
| 5 数据迁移 | 无 |
| 6 安全要求 | 不引入外部 CDN 字体；导出内容不含用户隐私路径 |
| 7 自检 | 三种浏览器各保存一次 PNG/ZIP/PDF 成功 |
| 8 自动化测试 | 现有 `exportLayout/pdf/pageFormats` 单测扩展；矢量 PDF 解析测试（页面对象、字体嵌入） |
| 9 E2E | Firefox 项目跑导出套件（本机需 `npx playwright install firefox`） |
| 10 验收 | 桌面浏览器落盘 3/3 成功；PDF 可选矢量且中文正确；TD-06 关闭 |
| 11 回滚 | 矢量 PDF 用 feature flag 关闭 |
| 12 报告 | `PocketScore-V1.1-C.6-Export-Report.md` |

关闭风险：R-P2-01、R-P2-06；R-P3-01 部分。

---

## C.7 可观测性与发布工程

| 项 | 内容 |
| --- | --- |
| 1 目标 | 线上可观测、可回滚、可演练，具备发布流程 |
| 2 修改范围 | 新增 `app/core/metrics.py`（Prometheus `/metrics` 内网）、结构化日志字段规范、`scripts/smoke.py`、`.github/workflows/deploy-backend.yml` |
| 3 技术方案 | 指标：请求数/延迟/作业数/队列深度/推理耗时/内存；日志：`request_id` 贯穿；告警：错误率与队列深度阈值 |
| 4 步骤 | 埋点 → 指标端点与访问控制 → 告警规则 → 冒烟脚本 → CI 部署流水线（手动触发）→ 回滚演练 |
| 5 数据迁移 | 无 |
| 6 安全要求 | `/metrics` 仅内网或带 token |
| 7 自检 | 一次发布后指标可见、冒烟全绿、回滚 5 分钟内完成 |
| 8 自动化测试 | `tests/test_metrics.py`（计数正确、不含敏感标签） |
| 9 E2E | 冒烟脚本串起 health → 上传 → 扒谱 → 导出 |
| 10 验收 | 演练：注入故障 → 告警触发 → 回滚成功，全程有记录 |
| 11 回滚 | 镜像 tag 回退 + 数据库向后兼容（只加列） |
| 12 报告 | `PocketScore-V1.1-C.7-Operations-Report.md` |

关闭风险：R-P2-03、R-P3-03、R-P3-04、R-P3-05。

---

## 阶段闸门（Gate）

| 闸门 | 通过条件（全部满足才可进入下一阶段） |
| --- | --- |
| C.2 → C.3 | 公网可完成真实扒谱；P0 全关闭；首作业 ≤1 s |
| C.3 → C.4 | 重启不丢数据；备份恢复演练通过；PG 上全测试绿 |
| C.4 → C.5 | 并发压测不 OOM；排队/取消/超时可用 |
| C.5 → C.6 | 越权测试全绿；限流与体积上限生效 |
| C.6 → C.7 | 桌面浏览器落盘 3/3；导出矩阵通过 |
| C.7 → 完成 | 告警 + 冒烟 + 回滚演练全部留痕 |

---

## 里程碑与交付物

| 阶段 | 交付物 | 建议顺序原因 |
| --- | --- | --- |
| C.2 | 部署报告 + 公网冒烟证据 | 先让服务存在，才有后续一切 |
| C.3 | 持久化报告 + 迁移记录 | 数据可靠性必须早于用户增长 |
| C.4 | 并发报告 + 压测曲线 | 有了用户再谈队列，顺序不能颠倒 |
| C.5 | 安全报告 + 越权测试 | 认证依赖稳定的数据模型（C.3） |
| C.6 | 导出报告 + 浏览器矩阵 | 与后端解耦，可并行但排在安全之后 |
| C.7 | 运维报告 + 演练记录 | 最后收口 |

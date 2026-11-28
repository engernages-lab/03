# PocketScore AI V1.1-C.2.3.4.3 · Upload Rate Limiting, Supply-chain & Runtime Hardening Report

## 1. 项目信息

| 项 | 值 |
| --- | --- |
| 项目 | PocketScore AI |
| 阶段 | V1.1-C.2.3.4.3 |
| 日期 | 2026-11-28 |
| 分支 | `pocketscore-v1.1-b` |
| 开始 HEAD | `ef6a18df717a9c1f29a130536c8c06442b81a3e1` |
| 结束 HEAD | `ef6a18df717a9c1f29a130536c8c06442b81a3e1`（未提交） |
| `origin/main` | `9e7cd419ea6576b89053ef1596d0dd155d422410`（未变） |
| `origin/pocketscore-v1.1-b` | `a94dfb98f562a0dcf9df44397ac7b09f3c333ec3`（未变） |
| 工作区 | 11 改 + 新增（历史阶段工作全部保留） |

## 2. 阶段结论

```text
CONDITIONAL PASS
```

判定依据（严格执行任务书的 P0 门槛）：

| 门槛 | 结果 |
| --- | --- |
| P0-A 非 root 运行 | ⛔ **NOT VERIFIED** — 本机无 Docker，最终镜像无法启动验证（代码与脚本已就绪） |
| P0-B 隔离 Volume 读写 | ⛔ **NOT VERIFIED** — 同上 |
| P0-C 历史 Volume 兼容 | ⛔ **NOT VERIFIED** — 同上（脚本已实现三种所有权模式） |
| P0-D 禁止危险权限修复 | ✅ **满足** — 无 0777、无启动期递归 chown（静态断言 + 代码审查） |

其余全部通过：独立限流、IP 信任边界、CORS 收紧、响应头、供应链 pin、581 项回归。
按任务书"如果历史 Volume 权限兼容性未验证，必须给出 CONDITIONAL PASS 或 BLOCKED"，
本阶段取 **CONDITIONAL PASS**，并把 Docker 类验收明确交给 CI（已验证工作流已接入，尚未执行）。

**Railway real Staging Volume compatibility: NOT VERIFIED**（本阶段未触碰任何 Railway 资源）。

## 3. 执行前审计（详见 `03-runtime-hardening-audit.md`）

| 问题 | 证据 |
| --- | --- |
| 只有门禁失败限流 | `access_gate.py:45` `MAX_FAILURES=20`，成功请求不计数 |
| CORS 全通配 | `main.py:68-75` `allow_methods=["*"]`、`allow_headers=["*"]` + credentials |
| 代理头被无条件信任 | Dockerfile CMD `--forwarded-allow-ips='*'` |
| 容器 root | Dockerfile 无 `USER` |
| `/data` 0777 | `RUN ... chmod 0777 /data` |
| 基础镜像浮动 tag | `node:20-slim`、`python:3.11-slim` |
| Actions 浮动 tag | `@v4`/`@v3`/`@v6` |
| 无安全响应头 | 全仓无 XCTO/XFO/CSP/HSTS |
| 无 CVE 扫描 / 无 SBOM | `pip-audit` 未装 |

## 4. API 限流实现

| 项 | 实现 |
| --- | --- |
| 算法 | 滑动窗口（每 `(bucket, client)` 一个时间戳列表） |
| 存储 | 进程内 dict + `threading.Lock`；`max_keys` 上限 + 过期/LRU 淘汰 |
| 可注入时钟 | `RateLimiter(clock=...)`，测试无需 sleep |
| 中间件 | 原生 ASGI（不缓冲流式响应），位于 CORS 之内、Access Gate 之外 |
| 桶 | `general` / `upload` / `transcription` / `waveform` |

默认限额（可配）：

| 桶 | 默认 | 命中路径 |
| --- | --- | --- |
| general | 120 / 60s | 其余全部 API |
| upload | 10 / 60s | `POST /api/v1/audio/upload`、`POST /api/v1/transcription/upload` |
| transcription | 5 / 60s | `POST /api/v1/transcription/jobs` |
| waveform | 60 / 60s | `*` 以 `/waveform` 结尾 |

429 行为：`code=RATE_LIMIT_EXCEEDED`、`Retry-After`（秒，≥1）、`X-RateLimit-Limit`、
`X-RateLimit-Remaining: 0`、`details={bucket, limit, window_seconds}`，无内部路径。

豁免：`/health`、`/ready`、`OPTIONS`（预检不会被业务限流拦截）。

**代理信任边界**：只有当**对端 IP** 落在 `POCKETSCORE_TRUSTED_PROXY_CIDRS`
（默认 `127.0.0.1/32, ::1/128, 10/8, 172.16/12, 192.168/16`）内时才解析 `X-Forwarded-For`，
且取**最右侧非受信跳**（不取客户端可控的 leftmost）。对端不受信时完全忽略该头。
uvicorn 侧同时把 `--forwarded-allow-ips` 从 `'*'` 改为 `${POCKETSCORE_TRUSTED_PROXY_IPS:-127.0.0.1}`。

**单实例限制（明确声明）**：计数在内存中，**重启清零**，**多副本不共享**。
没有实现分布式限流，也不声称多实例安全。存储层已抽出 `RateLimiter.check()` 接口便于换 Redis。

**环境默认**：`POCKETSCORE_RATE_LIMIT_ENABLED` 未显式设置时，staging/production 启用、
test 关闭（否则测试自身会被限流打穿 —— 本轮真的发生过，是有效信号）。

## 5. CORS 整改

| 项 | 修改前 | 修改后 |
| --- | --- | --- |
| methods | `["*"]` | `GET, POST, PUT, PATCH, DELETE, OPTIONS` |
| headers | `["*"]` | `Authorization, Content-Type, Accept, Range, If-Range, X-Requested-With, X-Request-ID` |
| expose | `X-Request-ID` | 追加 `Retry-After`、`X-RateLimit-*` |
| origin 校验 | 仅拒绝 `*` | 额外拒绝带 path/query/fragment、userinfo、非 http(s) 的 origin（生产环境生效） |
| credentials | true | true（origin 仍为精确白名单） |

实测（`test_cors_security.py`，15 项）：允许源精确回显；`localhost:5173.evil.example`、
`https://localhost:5173`、`localhost:5174`、`null`、带 path、带 userinfo、`ftp://` 全部**不返回**
`Access-Control-Allow-Origin`；预检只允许配置的方法与头；`*` 永不出现。

## 6. 供应链安全（详见 `03-supply-chain-audit.md`）

| 项 | 结果 |
| --- | --- |
| `pip check` | ✅ 无冲突 |
| `pip-audit` | ⛔ **未执行**（安装时网络阻塞 >10 分钟，已终止，未伪造结果） |
| `npm audit` | ✅ 执行：生产 `react-router-dom` **moderate**（仅 SSR hydration 路径，本项目无 SSR → 当前不可利用）；dev 侧 `vite` high、`vitest`/`tinypool` critical（不进入镜像） |
| 基础镜像 | ✅ 双 stage 均改为 `@sha256:` digest pin（multi-arch index） |
| Actions | ✅ 5 个 action 全部 40 位 SHA + 版本注释 |
| SBOM | ⛔ NOT VERIFIED（未启用 buildx `--sbom`，也未安装 syft） |

## 7. Docker 非 root 改造

| 项 | 值 |
| --- | --- |
| 用户 | `pocketscore`，uid/gid **10001**，`nologin` |
| 最终用户 | `USER 10001:10001`（在 `CMD` 之前） |
| `/app` | root 拥有、应用只读（不 chmod 可写） |
| `/data` | `10001:10001`、`0775`（不是 0777） |
| `/data/storage`、`/data/backups` | 构建期创建并 chown 给 10001 |
| `/app/tmp` | `0700`，`TMPDIR=/app/tmp`（上传流式临时文件） |
| `POCKETSCORE_BACKUP_DIR` | 镜像内显式 `/data/backups` |
| 启动期 chown | **无** |
| capabilities | 未在 Dockerfile 里限制（属运行参数）；CI 脚本以常规权限运行，未加 `--privileged` |
| 只读根文件系统 | **未启用**（应用写 `/app/tmp` 与 `/data`；需 tmpfs 配合，未验证 → NOT VERIFIED） |
| HEALTHCHECK | 保留 `/health` 探测 |
| SIGTERM | `exec` 保持 PID 1，`--timeout-graceful-shutdown 25` |

新增 `Settings.verify_runtime_writable()`：启动时探测数据目录可写性，
失败时抛出**带 uid/gid 与处置建议**的明确错误（替代原本晦涩的 SQLite 报错）。

## 8. Railway `/data` Volume 权限专项

| 测试项目 | 隔离 Docker Volume | Railway 真实 Staging Volume |
| --- | --- | --- |
| 空 Volume | ⛔ NOT VERIFIED（无 Docker） | — |
| 历史数据 Volume | ⛔ NOT VERIFIED | — |
| 非 root 读取历史文件 | ⛔ NOT VERIFIED | — |
| 新建音频文件 | ⛔ NOT VERIFIED | — |
| 音频读取 | ⛔ NOT VERIFIED | — |
| 音频删除 | ⛔ NOT VERIFIED | — |
| SQLite 数据库写入 | ⛔ NOT VERIFIED | — |
| WAL / SHM | ⛔ NOT VERIFIED | — |
| 备份写入 | ⛔ NOT VERIFIED | — |
| 容器重启 | ⛔ NOT VERIFIED | — |
| 数据持久化 | ⛔ NOT VERIFIED | — |
| SIGTERM | ⛔ NOT VERIFIED | — |
| 权限修复策略 | ✅ 设计完成（见下） | — |

**脚本已实现、已通过 `bash -n`、已接入 CI，但本机无法执行**：
`scripts/docker/test_nonroot_runtime.sh`（身份、数据写、WAL、音频、备份、SIGTERM、重启持久性）
与 `scripts/docker/test_nonroot_volume.sh`（A 已归属 / B root 拥有 / C 一次性迁移三种模式）。
两者都只清理自己创建的 Volume，Docker 不可用时 `exit 78` 而不是假装通过。

**权限策略（P0-D）**：
1. 新 Volume：构建期 `chown 10001:10001 /data` 会在 Docker 创建空具名卷时被继承 → 可写。
2. 历史 Volume（root 拥有）：**不做递归 chown**。建议一次性、受控地
   `chown 10001:10001 /data && chown -R 10001:10001 /data/storage /data/backups`
   （只动两个应用目录 + 卷根，不动其它文件），在停服窗口执行一次。
3. 若 Railway 不允许该操作 → 记录 BLOCKED，改为加入共享 GID 的替代方案。

**明确区分**：`Docker isolated Volume compatibility: NOT VERIFIED`（本机无 Docker）；
`Railway real Staging Volume compatibility: NOT VERIFIED`（本阶段禁止触碰）。

## 9. 自动化测试

| 文件 | 数量 | 结果 |
| --- | --- | --- |
| `tests/test_rate_limit.py` | 25 | ✅ 25 passed |
| `tests/test_cors_security.py` | 15 | ✅ 15 passed |
| `tests/test_security_headers.py` | 9 | ✅ 9 passed |
| `tests/test_runtime_config.py` | 19 | ✅ 19 passed |
| 合计新增 | **68** | **68 passed** |

关键覆盖：限流窗口滑动/重置、桶隔离、键空间上限（500 次请求后 ≤50）、
伪造 `X-Forwarded-For` 无法重置计数、受信代理取最右非受信跳、429 的 `Retry-After`、
预检与探针豁免；CORS 8 种恶意 origin；响应头在 200/401/404/429/OPTIONS 上都存在；
Dockerfile 与 worklfow 的 pin 断言；`verify_runtime_writable()` 的正负用例。

## 10. 全量回归

| 项 | 命令 | 结果 |
| --- | --- | --- |
| 后端全量 | `pytest` | **581 passed, 3 skipped**（97.5 s） |
| Ruff | `ruff check app tests` | **All checks passed** |
| 前端构建 | `npm run build`（`VITE_BASE_PATH=/`） | ✅ 1668 modules，`index-BGu74WxJ.js` 390.85 kB，`index-BcW44oh8.css` 37.58 kB |
| Docker build | — | ⛔ NOT VERIFIED（无 Docker） |
| 非 root 运行 | — | ⛔ NOT VERIFIED |
| SQLite / 备份 / SIGTERM（容器内） | — | ⛔ NOT VERIFIED |
| 备份模块回归（进程内） | 含在 581 中（`test_database_backup`/`test_project_backup`/`test_project_restore_e2e`） | ✅ |
| CI 工作流静态检查 | YAML 解析 + 全部 `run` 块 `bash -n` | ✅ 34 步，全部通过 |

> 「581 passed」中 3 个 skip 均为环境限制（1 个 C.2.3.3 符号链接 + 2 个 C.2.3.4.2 文件级符号链接）。

## 11. 验收矩阵

| ID | 项目 | 结果 | 证据 |
| --- | --- | --- | --- |
| RH-01 | 独立 API 限流 | **PASS** | 独立中间件；25 项测试；不依赖门禁 |
| RH-02 | 429 响应 | **PASS** | `RATE_LIMIT_EXCEEDED` + `Retry-After` ≥1 + `X-RateLimit-*` |
| RH-03 | 限流状态清理 | **PASS** | 键空间测试：500 请求后 ≤50 键；过期淘汰 |
| RH-04 | 代理 IP 信任 | **PASS** | 非受信对端的 XFF 被忽略；受信取最右非受信跳 |
| RH-05 | 限流兼容性 | **PASS** | OPTIONS/health/ready 豁免，均有测试 |
| RH-06 | CORS 来源 | **PASS** | 精确白名单；8 类恶意 origin 被拒 |
| RH-07 | CORS 方法与头 | **PASS** | 显式列表，无通配符 |
| RH-08 | CORS 预检 | **PASS** | 200 + 精确 allow 列表 |
| RH-09 | Python 依赖扫描 | **NOT VERIFIED** | `pip-audit` 不可用（网络阻塞） |
| RH-10 | Node 依赖扫描 | **PASS** | `npm audit` 结果已分类记录 |
| RH-11 | 镜像固定 | **PASS** | 双 stage `@sha256` digest |
| RH-12 | Actions 固定 | **PASS** | 5 个 action 全部 40 位 SHA + 注释；静态测试断言 |
| RH-13 | SBOM | **NOT VERIFIED** | 未启用 buildx `--sbom` / 无 syft |
| RH-14 | Docker 非 root | **NOT VERIFIED** | Dockerfile 就绪；本机无 Docker 无法启动验证 |
| RH-15 | 应用目录权限 | **PASS** | 无 0777；`/app` 只读；`/data` 0775 属 10001 |
| RH-16 | 空 Volume | **NOT VERIFIED** | 脚本已接入 CI（步骤 14） |
| RH-17 | 历史文件 Volume | **NOT VERIFIED** | 脚本已实现三种模式（步骤 15） |
| RH-18 | SQLite WAL/SHM | **NOT VERIFIED** | 脚本内含 WAL 断言，未执行 |
| RH-19 | 备份目录 | **NOT VERIFIED** | 同上 |
| RH-20 | Volume 持久性 | **NOT VERIFIED** | 同上 |
| RH-21 | SIGTERM | **NOT VERIFIED**（容器内）| 进程内优雅关闭既有测试通过 |
| RH-22 | 安全响应头 | **PASS** | 200/401/404/429/OPTIONS 全覆盖；HSTS 可选 |
| RH-23 | Docker healthcheck | **NOT VERIFIED** | 无 Docker；HEALTHCHECK 保留 |
| RH-24 | 全量后端回归 | **PASS** | 581 passed / 3 skipped |
| RH-25 | 前端构建 | **PASS** | `npm run build` 成功 |
| RH-26 | Docker 构建 | **NOT VERIFIED** | 无 Docker |
| RH-27 | Docker 安全运行 | **NOT VERIFIED** | 同上 |
| RH-28 | CI 工作流 | **PASS（静态）** | 34 步、YAML 合法、`bash -n` 全通过、旧步骤保留 |
| RH-29 | Railway 隔离 | **PASS** | 未部署、未改变量、未碰 Volume |
| RH-30 | Git 安全边界 | **PASS** | 未提交/未推送/未合并，HEAD 未变 |

**PASS 17 · NOT VERIFIED 12 · FAIL 0**（NOT VERIFIED 全部因"本机无 Docker"或"未授权 Push"）。

## 12. 风险与遗留

| # | 项 | 等级 | 说明 |
| --- | --- | --- | --- |
| 1 | 非 root 运行时未经真实容器验证 | **P0（验证缺口）** | 需 CI 或本地 Docker |
| 2 | 历史 Volume 所有权迁移策略未在真实 Volume 验证 | **P0（验证缺口）** | 需停服窗口 + 授权 |
| 3 | 限流为单实例内存态 | P2 | 重启清零、多副本不共享；已明确声明 |
| 4 | `pip-audit` 未执行 | P1 | 需联网 CI |
| 5 | `react-router-dom` moderate（生产依赖） | P3 | 仅 SSR 路径，本项目无 SSR；升级需单独回归 |
| 6 | 只读根文件系统未验证 | P2 | 需 tmpfs 方案；未启用 |
| 7 | capabilities 未收敛 | P2 | 未在运行参数层验证 `--cap-drop=ALL` |
| 8 | SBOM 未建立 | P2 | 评估完成，实施待定 |
| 9 | C.2.3.4.2 文件级 symlink 缺口 | P2 | 仍待 Linux/CI 补验 |
| 10 | CORS `null` origin 未列入白名单 | — | 已拒绝（正确） |

## 13. Git 与环境边界

| 项 | 状态 |
| --- | --- |
| 操作 Railway（部署/重启/变量/Volume） | ❌ 无 |
| 修改真实数据库 | ❌ 无 |
| 访问真实 Volume | ❌ 无 |
| Commit | ❌ 无 |
| Push | ❌ 无 |
| Merge | ❌ 无 |
| 影响 `origin/main` | ❌ 无（`9e7cd41`） |
| 历史未提交工作 | ✅ 全部保留（`app/ops/`、7 个旧测试、`docs/operations/`、旧报告、CI 既有步骤） |

本阶段文件清单：

```text
新增  backend/app/core/ratelimit.py
新增  backend/app/core/security_headers.py
新增  backend/tests/test_rate_limit.py
新增  backend/tests/test_cors_security.py
新增  backend/tests/test_security_headers.py
新增  backend/tests/test_runtime_config.py
新增  scripts/docker/test_nonroot_runtime.sh
新增  scripts/docker/test_nonroot_volume.sh
新增  reports/V1.1-C.2.3.4/03-runtime-hardening-audit.md
新增  reports/V1.1-C.2.3.4/03-supply-chain-audit.md
新增  reports/V1.1-C.2.3.4/03-runtime-hardening-report.md
修改  backend/app/core/config.py      (+限流/CORS/头/代理/可写性校验)
修改  backend/app/main.py             (+限流与安全头中间件、CORS 收紧)
修改  backend/Dockerfile              (非 root、digest pin、去 0777、代理信任)
修改  .github/workflows/docker-verify.yml (SHA pin、非 root 两步、新测试)
```

## 14. 下一阶段建议

可以进入 **C.2.3.4.4 · User Identity, Ownership & Access Isolation**（P0 身份与隔离是本项目
开放试用的真正阻塞项）。但在部署任何东西之前，必须先解决本阶段的两个 **P0 验证缺口**：

1. 在 CI（或本地装 Docker）跑 `test_nonroot_runtime.sh` 与 `test_nonroot_volume.sh`；
2. 获授权后在 Staging 做一次性 Volume 所有权迁移并复验。

**Railway real Staging Volume compatibility: NOT VERIFIED** —— 在完成第 2 项之前，
不得把本阶段结论用于"可以直接部署"的判断。

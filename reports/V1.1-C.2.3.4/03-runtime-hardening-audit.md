# PocketScore AI V1.1-C.2.3.4.3 · 运行时加固审计（实施前）

> 只读审计，2026-11-28。目标是把 C.2.3.4.1 的限流 / CORS / 供应链 / root 运行 / 响应头
> 问题定位到具体文件与行号，并确认 Docker 与 Volume 的真实约束。

## 1. Git 基线

| 项 | 值 |
| --- | --- |
| 分支 | `pocketscore-v1.1-b` |
| HEAD | `ef6a18df717a9c1f29a130536c8c06442b81a3e1` |
| `origin/main` | `9e7cd419ea6576b89053ef1596d0dd155d422410` |
| `origin/pocketscore-v1.1-b` | `a94dfb98f562a0dcf9df44397ac7b09f3c333ec3` |
| 未提交（必须保留） | `M .github/workflows/docker-verify.yml`、`M .gitignore`、`M audio.py/main.py/assets.py/probe.py`；`?? app/core/paths.py`、`?? app/ops/`、7 个测试文件、`?? docs/operations/`、`?? reports/V1.1-C.2.3/`、`?? reports/V1.1-C.2.3.4/` |

## 2. API 限流审计

| 位置 | 现状 | 问题 |
| --- | --- | --- |
| `app/core/access_gate.py:45` | `MAX_FAILURES = 20`，60s 窗口，仅统计**凭据失败** | 不是 API 限流：成功请求永不计数 |
| `app/main.py` 中间件链 | CORS（最外）→ AccessGate → 路由 | 无任何按接口/按 IP 的吞吐限制 |
| `/api/v1/audio/upload` | 只有大小上限（50 MB） | 单 IP 可无限次上传小文件 |
| `/api/v1/transcription/jobs` | 有并发闸门（capacity=1，超出 503） | 但可无限排队，无速率限制 |
| `/api/v1/audio/assets/{id}/waveform` | 每次请求都做整段解码 | CPU 密集且无限流 |
| `--forwarded-allow-ips='*'`（Dockerfile CMD） | uvicorn 信任**任意**对端提交的 `X-Forwarded-For` | **限流可被伪造头绕过**，必须先修 |

## 3. CORS 审计

`app/main.py:68-75`：

```python
allow_origins=settings.cors_origins,
allow_credentials=True,
allow_methods=["*"],
allow_headers=["*"],
```

- `allow_methods`/`allow_headers` 全通配 + `allow_credentials=True`。
- `cors_origins` 默认只有 localhost 开发源；但配置项本身**没有格式校验**（可写入 `https://x/path`、
  带 userinfo 的值，启动不会报错）。
- 缺少 `Retry-After`/限流头的 `expose_headers`。

## 4. 供应链审计

| 项 | 现状 |
| --- | --- |
| `backend/requirements.txt` | 版本范围锁定（`fastapi>=0.110,<0.116` 等），无精确 pin、无 hash |
| `requirements-dev.txt` / `requirements-model.txt` | 存在（模型包 `--no-deps`） |
| 前端 | `package-lock.json` 146 KB（有锁），`npm ci` 可用 |
| Docker 基础镜像 | `node:20-slim`、`python:3.11-slim`（**浮动 tag，无 digest**） |
| GitHub Actions | `actions/checkout@v4`、`setup-node@v4`、`docker/setup-buildx-action@v3`、`docker/build-push-action@v6`、`upload-artifact@v4`（**浮动 major tag**） |
| `pip-audit` | 未安装；本轮尝试安装时网络阻塞（见报告） |
| SBOM | 无 |

## 5. Docker 与 Volume 审计

| 项 | 现状 | 问题 |
| --- | --- | --- |
| `USER` | **无** | 应用以 **root (uid 0)** 运行 |
| `RUN mkdir -p /data/storage && chmod 0777 /data` | 0777 | 违反最小权限 |
| `/app` | root 拥有 | 非 root 后需只读可执行（当前 0644/0755，可读） |
| `/tmp` | 系统 tmp | 非 root 可写；镜像内另有 `/app/tmp` 待建 |
| 数据路径 | `/data/pocketscore.db`、`/data/storage`（`POCKETSCORE_BACKUP_DIR` 未在镜像设置，默认 `<db 目录>/backups` = `/data/backups`） | 需显式化 |
| SQLite WAL | 连接级 `PRAGMA journal_mode=WAL` | 需 `/data` 可写（含 `-wal`/`-shm` 创建） |
| Railway Volume | 已挂载 `/data`，现存数据由 root 身份写入 | **非 root 后可能无写权限**，这是本阶段最大风险 |
| SIGTERM | `exec uvicorn --timeout-graceful-shutdown 25` | 需在非 root 下复验 |
| 本地 Docker | **不可用**（无守护进程） | 所有容器类验收只能标 NOT VERIFIED 或交由 CI |

## 6. 安全响应头

全仓无 `X-Content-Type-Options` / `X-Frame-Options` / `Referrer-Policy` / `Permissions-Policy` / CSP / HSTS。
HSTS 需要先确认 TLS 终止点（Railway 边缘），本阶段默认不发送。

## 7. 实施计划

| 文件 | 变更 |
| --- | --- |
| `app/core/ratelimit.py`（新增） | 滑动窗口限流 + 代理信任解析 + ASGI 中间件 |
| `app/core/security_headers.py`（新增） | 安全响应头中间件 |
| `app/core/config.py` | 限流 / 受信代理 / CORS 方法头 / CSP / HSTS 配置；Origin 格式校验；`verify_runtime_writable()` |
| `app/main.py` | 接入限流（CORS 内、门禁外）、安全头（最外）、CORS 显式方法/头 |
| `backend/Dockerfile` | 非 root 用户 10001、去 0777、显式 `POCKETSCORE_BACKUP_DIR`、`--forwarded-allow-ips` 收紧、镜像 digest pin |
| `.github/workflows/docker-verify.yml` | Action SHA pin、非 root 运行时与历史 Volume 两步、新测试文件 |
| `scripts/docker/test_nonroot_runtime.sh`（新增） | 非 root 运行时 + 隔离 Volume + WAL + SIGTERM + 重启持久性 |
| `scripts/docker/test_nonroot_volume.sh`（新增） | 历史 Volume 三种所有权模式 |
| 测试 | `test_rate_limit.py`、`test_cors_security.py`、`test_security_headers.py`、`test_runtime_config.py` |

不修改：认证架构、`/static` 挂载、模型与迁移、备份模块的对外行为。

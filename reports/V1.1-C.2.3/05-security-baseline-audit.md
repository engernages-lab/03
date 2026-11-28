# PocketScore AI V1.1-C.2.3.4.1 · Security Baseline Audit Report

> **最终结论：BLOCKED**
> P0 共 **2 项**，均已实测复现：**不存在用户身份与所有权体系**，同一共享 Token 下
> **A 可列出、读取、串流、甚至删除 B 的音频资产**（实测 `200 / 200 / 204`）；
> 以及 `/static` 把整个存储根**原样暴露**给任何持 Token 者。
> 在多用户试用前必须修复。本阶段仅审计，未改任何业务代码。

| 统计 | 数量 |
| --- | --- |
| P0 | **2** |
| P1 | 5 |
| P2 | 6 |
| P3 | 3 |

## 1. 项目信息与 Git 基线

| 项 | 实测值 |
| --- | --- |
| 分支 | `pocketscore-v1.1-b` |
| HEAD | `ef6a18df717a9c1f29a130536c8c06442b81a3e1` |
| `origin/pocketscore-v1.1-b` | `a94dfb98f562a0dcf9df44397ac7b09f3c333ec3` |
| `origin/main` | `9e7cd419ea6576b89053ef1596d0dd155d422410` |
| 领先 origin | 1 个提交（本地未推送的文档提交） |
| 工作区 | 9 项未提交：`.github/workflows/docker-verify.yml`、`.gitignore` 修改；`backend/app/ops/`、4 个测试文件、`docs/operations/`、`reports/V1.1-C.2.3/` 新增（皆来自 C.2.3.2/3，**未提交**） |
| 审计时间 | 2026-11-28（Asia/Shanghai） |

**Secret 泄露检查**（只扫 git 会带走的 355 个文件，排除缓存与二进制）：

| 结果 | 说明 |
| --- | --- |
| 命中 3 处 | `backend/tests/test_access_gate.py:25` `staging-token-abcdef0123456789`；`docker-compose.yml:22` `local-compose-only-change-me`；`scripts/smoke_deployment.py:40` `smoke-access-token-0123456789abcdef` —— 均为测试/本地占位值，非真实凭据 |
| 私钥 / AWS / GitHub / Slack / Google / OpenAI 令牌 | 0 |
| 数据库 URL 带密码 | 0 |
| 被跟踪的 `.env` / `.pem` / `.key` | 仅 `.env.example` ×3（模板，真实字段为空或 `change-me-in-production`） |
| `.gitignore` | 含 `.env`、`.env.*`、`!.env.example`、`backups/`、`*.manifest.json` ✅ |

## 2. 审计范围

SEC-01 Git/基线、SEC-02 路径与存储、SEC-03 引用与生命周期、SEC-04 API 身份与访问控制、
SEC-05 上传安全、SEC-06 SSRF、SEC-07 认证与会话、SEC-08 备份恢复安全、SEC-09 依赖与供应链、
SEC-10 日志与错误处理。

## 3. 审计工具与版本

| 工具 | 版本/方式 |
| --- | --- |
| Python | 3.9.13（`backend/.venv`） |
| pytest | 2.x（项目既有） |
| ruff | 项目既有 |
| `pip check` | ✅ 执行 |
| `pip-audit` | ❌ 未安装 → 依赖 CVE **未验证** |
| 自定义探针 | `.run/sec01_secrets.py`、`sec02_paths.py`、`sec45b.py`、`sec5c.py`（隔离临时目录） |
| 手工代码审计 | `app/core/{config,ssrf,access_gate,db}.py`、`app/api/v1/*.py`、`app/services/audio/*.py`、`app/main.py` |

全部探针在 `tempfile.mkdtemp()` 下建库建目录，**未触碰 `/data`、未连 Railway、未读真实用户数据**。

## 4. 安全检查项与证据

### SEC-02 路径与存储安全

`absolute_path(record) = get_settings().storage_path / record.stored_path`（`app/services/audio/assets.py`），
**没有 resolve 后的包含性校验**。用篡改行实测（合法 WAV 放在存储根之外）：

| 探针 `stored_path` | `/waveform` 状态 | 是否逃逸 |
| --- | --- | --- |
| `audio/aa/<sha>.wav`（合法） | 200 | 否 |
| `../../outside-secret.wav` | **200** | **是** |
| `..\..\outside-secret.wav` | **200** | **是** |
| 绝对路径 `D:\…\outside-secret.wav` | **200** | **是** |
| `../../../<root>/outside-secret.wav` | **200** | **是** |
| 空字符串 | 422 | 否，但**错误详情泄露绝对路径** |
| `audio/../../../outside-secret.wav` | **200** | **是** |

5/6 逃逸。**触发前提**：`stored_path` 由服务端按内容寻址写入，用户不能直接指定 →
当前是"数据库被篡改/被写入"后的提权路径，而非匿名可达漏洞。定级 **P1**。

**静态挂载**（`app/main.py:169` `app.mount("/static", StaticFiles(directory=settings.storage_path))`）：

| 探针 | 状态 |
| --- | --- |
| `GET /static/<asset>` 无令牌 | **401**（门禁生效） |
| `GET /static/<asset>` 带令牌 | **200**，8 044 字节原始音频 |
| `/static/../outside-secret.wav` | 404（StaticFiles 自身防穿越） |
| `/static/%2e%2e/outside-secret.wav` | 404 |
| `/static/uploads/../../outside-secret.wav` | 404 |

静态层本身不穿越，但它**把 `audio/`、`artwork/`、`uploads/`、`midi/` 整棵树**交给任何持令牌者。

**错误信息**：`AUDIO_ASSET_NOT_FOUND` 干净（无路径）；但**解码失败**时
`details.reason` 返回 `[Errno 13] Permission denied: 'D:\\…\\storage'` —— **绝对路径泄露（P1）**。

### SEC-03 引用与生命周期

- `delete_asset()`（`assets.py:336`）：先删数据库行并提交，再 `path.unlink()`。
  **不检查该文件是否被其它记录引用**（`music_documents.source_metadata_json` 内嵌 asset id）。
- 内容寻址天然去重 → 两条 `audio_assets` 行**不会**指向同一文件（`checksum_sha256` 唯一），
  所以"删除资产破坏别人文件"目前不会发生；风险在于**非音频引用**（文档 JSON 里的 asset id）悬空。
- `uploads/` 与 `midi/`：上传成功 `os.replace` 移走；失败分支 `shutil.rmtree(tmp_dir)`（`audio.py:118`）。
- 并发删除 + 读取：无锁，但删除是 DB 先提交 → 读取方拿到 404 而非半文件。

### SEC-04 API 身份与访问控制（**核心 P0**）

路由共 **91** 条，其中 **89 条**受 Access Gate 保护，`/health`、`/ready` 公开。
**没有任何一条**做用户身份或资源所有权判断（全仓无 `user_id`/`owner_id`/`get_current_user`）。

实测（同一 Token，两个"用户"各自上传）：

| 检查 | 结果 |
| --- | --- |
| A 上传 | 201 |
| B 上传 | 201 |
| `GET /api/v1/audio/assets`（A 的会话）列出数量 | **2**（A 与 B 都在） |
| 列表字段是否含 owner/user | **否**（字段：asset_id/filename/title/artist/mime/ext/size/duration/sample_rate/channels/bitrate/codec/checksum_sha256/artwork_url/stream_url/source_id/created_at） |
| A 用 B 的 asset_id `GET /assets/{id}` | **200** |
| A 用 B 的 asset_id `GET /assets/{id}/stream` | **200** |
| A 用 B 的 asset_id `DELETE /assets/{id}` | **204（删除成功）** |
| 匿名 `GET /assets` | 401 |

分类结论：

| 接口族 | 保护级别 |
| --- | --- |
| `/health`、`/ready` | 公开 |
| `/api/v1/**`（含 documents、assets、jobs、notation、midi、playback、sources） | **仅 Access Gate**（共享 Token） |
| `/static/**` | 仅 Access Gate |
| 前端 SPA | 仅 Access Gate |
| 用户身份 / 所有权 / 管理员 | **不存在** |

> ```text
> SHARED ACCESS TOKEN IS NOT AUTHENTICATION, AND NOT AUTHORIZATION.
> ```

### SEC-05 上传安全

| 探针 | 状态 | 判定 |
| --- | --- | --- |
| 合法 WAV | 201 | ✅ |
| 文本冒充 `.wav` | 422 `AUDIO_PROBE_FAILED` | ✅ 内容校验有效 |
| 文本冒充 `.mp3` | 422 | ✅ |
| 截断 WAV（40 字节） | 422 | ✅ |
| 空文件 | 422 `uploaded file is empty` | ✅ |
| `.exe` | 415 `UNSUPPORTED_MEDIA_TYPE` | ✅ |
| `evil.wav.exe` | 415 | ✅ 取最后扩展名 |
| RIFF 头 + 垃圾 | 422 | ✅ |
| `Content-Type: text/plain` + 真 WAV | 201 | ✅ 以内容为准，不信任头 |
| 2 100 396 B（限制 1 MB） | **413** `PAYLOAD_TOO_LARGE`，`declared_mb: 2.0` | ✅ 预检查生效 |
| 文件名 `../../escape.wav` | **201**，`filename` 原样存并回显，`stored_path` 仍是内容寻址 | ⚠️ 文件未逃逸，但**文件名未清洗**（P2） |

### SEC-06 SSRF

`validate_server_url` 实测（`ALLOW_PRIVATE_NETWORK_SOURCES=false`，加固态）：

| 目标 | 结果 |
| --- | --- |
| `localhost` | BLOCKED |
| `127.0.0.1` | BLOCKED |
| `[::1]` | BLOCKED |
| `169.254.169.254` | BLOCKED |
| `instance-data` | BLOCKED |
| `10.0.0.5` / `192.168.1.10` / `172.16.0.9` | BLOCKED（加固态） |
| `[fd00::1]` | BLOCKED |
| `file://` / `gopher://` | BLOCKED（scheme 白名单） |
| `http://2130706433/`、`http://0x7f000001/`、`http://127.1/` | BLOCKED（无法解析） |
| 公网域名 | BLOCKED —— **因本机无 DNS 解析，非策略拦截**，此项**未验证** |

默认值：`allow_private_network_sources: bool = True`（宽松）。但 staging/production 下
`validate_hardened_secrets()` 会把它列为错误，应用**拒绝启动**（下文 SEC-07 实测）。

### SEC-07 认证与会话

| 项 | 现状 |
| --- | --- |
| 注册 / 登录 / 密码哈希 | ❌ 不存在（全仓无 login/password_hash/session 表） |
| Cookie / 会话 / Token 过期 / 撤销 | ❌ 不存在（无 `set_cookie`） |
| CSRF | 不适用（无 Cookie 会话） |
| 管理员角色 | ❌ 不存在 |
| Session Secret | 存在配置项，≥32 字符校验；staging 实测 96 字符且非占位值 |
| Token 加密密钥 | Fernet 格式校验通过；**生产未配置** |
| CORS | `allow_origins=settings.cors_origins`（精确源）、`allow_credentials=True`、`allow_methods=["*"]`、`allow_headers=["*"]`；`*` 在 staging/production 被拒 |
| 安全响应头 | ❌ **完全未配置**（无 HSTS / CSP / X-Content-Type-Options / X-Frame-Options / Referrer-Policy） |
| Token 日志泄露 | ✅ 未见（门禁日志只记 method/path/client/attempt；无 Authorization 输出） |

**生产配置错误会拒绝启动**（实测）：

```
RuntimeError: refusing to start with insecure configuration:
  POCKETSCORE_SESSION_SECRET must be set to a random value of at least 32 characters;
  POCKETSCORE_TOKEN_ENCRYPTION_KEY must be set;
  POCKETSCORE_CORS_ORIGINS must not contain '*';
  POCKETSCORE_ALLOW_PRIVATE_NETWORK_SOURCES must be false outside a trusted LAN;
  POCKETSCORE_ACCESS_GATE_MODE=off is not allowed in staging/production
```

这是本审计里**最有效的现有防线**。

### SEC-08 备份与恢复安全

| 检查 | 结果 |
| --- | --- |
| 备份目录位置 | 默认 `<db 所在目录>/backups` → 生产为 `/data/backups`，**在 `storage` 之外** |
| 是否被 `/static` 暴露 | ❌ 否（不在存储根内） |
| 是否可能进 Git | ✅ `.gitignore` 含 `backups/`、`*.manifest.json` |
| Manifest 完整性 | ✅ joint manifest + `snapshot.sha256`，逐文件 SHA-256 |
| 恢复路径保护 | ✅ `/data`、staging、production 拒绝，`--force` 不解除（C.2.3.3 已有测试） |
| 恢复路径穿越 | ✅ `is_within()` 校验每个相对路径 |
| 未授权恢复入口 | ✅ 无 API 暴露，仅 CLI |
| **备份加密** | ❌ **未实现**（P1） |

### SEC-09 依赖与供应链

| 检查 | 结果 |
| --- | --- |
| `pip check` | ✅ No broken requirements |
| 依赖锁定 | 范围锁定（`fastapi>=0.110,<0.116` 等），非精确 pin；镜像构建可解析到不同补丁版 |
| CVE 扫描 | ❌ **未验证**（`pip-audit` 未安装，且需漏洞库网络） |
| 前端依赖 | `package-lock.json` 存在（有锁） |
| 基础镜像 | `node:20-slim`、`python:3.11-slim`（**浮动 tag，非 digest 固定**） |
| Actions 版本 | `actions/checkout@v4`、`setup-node@v4`、`docker/setup-buildx-action@v3`、`docker/build-push-action@v6`、`upload-artifact@v4`（均为大版本 tag，非 SHA 固定） |
| 镜像内多余工具 | 已装 ffmpeg（必要）；未见编译器/包管理器残留（C.2.1 已验证） |
| 运行时权限 | ⚠️ 容器以 **root** 运行（Dockerfile 未 `USER`） |
| 安装脚本风险 | 模型包用 `--no-deps` 固定闭包，构建期真值断言（C.2.1 已固化） |

### SEC-10 日志与错误处理

| 检查 | 结果 |
| --- | --- |
| Secret 入日志 | ✅ 未见 |
| Token 入日志 | ✅ 未见 |
| 绝对路径泄露 | ⚠️ **解码失败详情泄露**（实测 `Permission denied: 'D:\\…\\storage'`） |
| 堆栈回传客户端 | ✅ 否（通用 `Exception` → `InternalError`，堆栈只进服务端日志） |
| request_id 追踪 | ✅ 有（响应头 + 错误体） |
| 审计日志 | ❌ 无"谁在何时读了/删了什么"的记录；仅门禁失败日志 |
| 认证/权限/不存在 三态区分 | ⚠️ 只有门禁 401 与 404，无权限维度（因为没有权限模型） |

## 5. 关键源码文件与行号

| 文件 | 行 | 内容 |
| --- | --- | --- |
| `backend/app/services/audio/assets.py` | 336-345 | `delete_asset`：先删库后删文件，无共享引用检查 |
| 同上 | 171-174 / 227-234 | 内容寻址写入 + `os.replace` |
| 同上 | 360-367 | `_store_artwork` 返回 `/static/artwork/...` |
| 同上 | `absolute_path` | `storage_path / stored_path`，无包含性校验 |
| `backend/app/main.py` | 63-66 | CORS：`allow_credentials=True`、methods/headers `*` |
| 同上 | 169 | `app.mount("/static", StaticFiles(directory=storage_path))` |
| 同上 | 129-133 | 通用异常 → `InternalError()` |
| `backend/app/core/config.py` | 228-250 | 加固校验（私有网络、门禁模式） |
| `backend/app/core/ssrf.py` | 26-60 | 阻断表、IP 判定、scheme 白名单 |
| `backend/app/core/access_gate.py` | 45 / 108-166 | `MAX_FAILURES=20`、失败限流、拒绝日志 |
| `backend/app/api/v1/audio.py` | 84-111 | Content-Length 预检查 + 分块累计 |
| `backend/app/api/v1/playback.py` | `proxy_stream` | 适配器代理，非任意 URL 下载 |

## 6. 测试命令与实际结果

```bash
# 密钥扫描（355 个 git 可见文件）
python .run/sec01_secrets.py
# → files scanned: 355 | hits: 3（均为测试/占位值）| suspicious tracked filenames: 仅 .env.example

# 路径穿越 + 静态暴露 + 门禁
python .run/sec02_paths.py
# → 5/6 篡改 stored_path 逃逸成功（200）；/static 匿名 401、带令牌 200；
#   静态层 ../ 与 %2e%2e 均 404；AUDIO_ASSET_NOT_FOUND 不泄露路径

# 用户隔离 + 上传校验
python .run/sec45b.py
# → 同一令牌列出 2 个资产；跨读 200；跨串流 200；跨删 204；
#   假冒/截断/空/多扩展 全部 415/422

# 超限 + 文件名 + SSRF 加固 + 生产启动
python .run/sec5c.py
# → 2.1 MB 上传 413 PAYLOAD_TOO_LARGE；../../escape.wav 201 但 stored_path 仍内容寻址；
#   SSRF 加固态全部 BLOCKED；生产+不安全配置 → RuntimeError 拒绝启动

# 依赖
python -m pip check          # → No broken requirements found.
python -m pip_audit          # → No module named pip_audit（未验证）
```

## 7. 已确认问题

### P0

| ID | 问题 | 证据 | 影响 |
| --- | --- | --- | --- |
| P0-1 | **无用户身份/所有权，跨用户读、串流、删除全部成功** | 同一 Token 下 `GET /assets/{B}`=200、`/stream`=200、`DELETE`=**204**；列表返回 A+B 共 2 条 | 任何拿到共享 Token 的人可读写删所有人的项目与音频 |
| P0-2 | **`/static` 暴露整个存储根** | 带令牌 `GET /static/audio/aa/….wav` = 200（8 044 B） | 音频/封面/临时目录可被逐个拉取，绕过 API 语义 |

### P1

| ID | 问题 | 证据 |
| --- | --- | --- |
| P1-1 | `absolute_path` 无包含性校验（路径穿越） | 5/6 篡改 `stored_path` 读出存储根外文件（200） |
| P1-2 | 解码失败泄露服务器绝对路径 | `details.reason` 含 `D:\…\storage` |
| P1-3 | 备份与音频均为明文 | 备份工具无加密实现 |
| P1-4 | 无审计日志（谁读了/删了什么） | 仅门禁失败日志 |
| P1-5 | `delete_asset` 不检查共享/内嵌引用 | 代码路径 + 无引用计数；文档 JSON 内嵌 asset id 会悬空 |

### P2

| ID | 问题 | 证据 |
| --- | --- | --- |
| P2-1 | 上传文件名未清洗（`../../escape.wav` 原样入库并回显） | 201 + `filename_returned` 原样 |
| P2-2 | SSRF 默认 `allow_private_network_sources=True` | 配置默认值；靠启动校验兜底 |
| P2-3 | 限流只有门禁失败维度（20/60s），无按接口/按 IP 的 API 限流 | `access_gate.py:45` |
| P2-4 | CORS `allow_methods/headers="*"` + `allow_credentials=True` | `main.py:63-66` |
| P2-5 | 依赖 CVE 未扫描；基础镜像与 Actions 非 digest/SHA 固定 | `pip-audit` 缺失、`python:3.11-slim`、`@v4` |
| P2-6 | 容器以 root 运行 | Dockerfile 无 `USER` |

### P3

| ID | 问题 | 证据 |
| --- | --- | --- |
| P3-1 | 无安全响应头（HSTS/CSP/XCTO/XFO/Referrer-Policy） | 全仓无相关中间件 |
| P3-2 | 门禁日志记录客户端 IP | `access_gate.py:160` |
| P3-3 | `/health` `/ready` 匿名可访问（设计如此，需确认是否暴露内部版本/阶段） | 返回 `version`、`stage` |

## 8. 是否满足多用户试用条件

**不满足。**

- 缺少身份与授权 → P0-1；`/static` 全量暴露 → P0-2。
- 试用意味着"少数朋友各自的数据"，而当前**任何**持令牌者对所有数据拥有完全权限，包括删除。
- 共享 Token 一旦外传无法撤销粒度化，也无法定位是谁做的（无审计日志）。

## 9. C.2.3.4.2～C.2.3.4.5 整改路线（详见 roadmap 文件）

| 阶段 | 主题 | 前置 |
| --- | --- | --- |
| C.2.3.4.2 | 文件路径与存储边界加固（P1-1/P1-2/P2-1） | 无 |
| C.2.3.4.3 | 上传/限流/供应链与运行加固（P2-3/4/5/6、P3-1） | 无 |
| C.2.3.4.4 | **身份、所有权与访问控制**（P0-1/P0-2/P1-4/P1-5） | 建议独立阶段，工作量最大 |
| C.2.3.4.5 | 备份加密与恢复演练补强（P1-3） | 可与 4.2/4.3 并行 |

## 10. 无法验证的事项及原因

| 项 | 原因 |
| --- | --- |
| 依赖 CVE（Python/Node） | `pip-audit` 未安装；离线环境无法查漏洞库 |
| SSRF 公网放行路径 | 本机 DNS 不可用，`music.example.com` 被"无法解析"拦截，无法区分策略拦截与网络失败 |
| Docker 内工具（C.2.3.2/3 的 ST-11/DBR-10） | 本机无 Docker 守护进程 |
| CI 远程执行（ST-12/DBR-11） | 未获 Push 授权 |
| 真实多用户并发行为 | 无用户系统，无法构造真实身份 |
| Windows 符号链接逃逸 | 当前环境无法创建 symlink（逻辑已由 `is_within` 覆盖） |

## 11. Git / Railway / 数据边界确认

| 项 | 状态 |
| --- | --- |
| 修改业务源码 | ❌ 无 |
| 修改 Schema / 迁移 | ❌ 无 |
| Commit / Push / Merge | ❌ 无（HEAD 仍 `ef6a18d`，工作区仍是 C.2.3.2/3 的未提交变更） |
| Railway 部署/重启/环境变量 | ❌ 无 |
| Railway Volume / 真实数据库读写 | ❌ 无 |
| 真实用户数据导出 | ❌ 无 |
| 输出真实 Secret | ❌ 无（报告只写"存在/长度/格式"，不写值） |
| 临时文件 | 全部在系统临时目录，脚本结束即删 |

## 12. 结论与放行判断

| 问题 | 回答 |
| --- | --- |
| 最终结论 | **BLOCKED** |
| P0 / P1 / P2 / P3 | 2 / 5 / 6 / 3 |
| 是否满足 C.2.3.4.2（路径加固）前置 | ✅ 可进入（该阶段本身就是修 P1-1/P1-2） |
| 是否满足 C.2.3.4.3（上传/供应链加固） | ✅ 可进入 |
| 是否满足 C.2.3.4.4（身份与访问控制） | ✅ 可进入，且**必须**做，否则不可开放试用 |
| 是否满足 C.2.3.4.5（备份加密） | ✅ 可进入 |
| 是否允许进入 C.2.4 | ❌ **不允许**（P0 未修复） |
| 是否允许开放多用户试用 | ❌ **不允许** |
| Git 是否有变化 | 无（仅新增本报告两份） |
| Railway 是否有变化 | 无 |
| 数据库 / Volume 是否有变化 | 无 |

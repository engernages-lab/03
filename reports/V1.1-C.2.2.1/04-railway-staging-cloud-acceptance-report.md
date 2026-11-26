# V1.1-C.2.2.1 · Railway Staging 云端验收报告

> **结论：BLOCKED**
> 阻塞原因：本机**没有 Railway 登录权限**（CLI 未安装、无凭据、无 `RAILWAY_*` 变量），
> 且用户**未明确授权 AI 直接操作真实云资源**。
> 依据提示词 §18.3：「没有真实 Railway 云端部署，最多只能报告部署准备完成」。
>
> **本报告中没有任何云端测试结果** —— 未部署、未调用真实域名、未编造指标。

---

## 1. 项目版本信息

| 项 | 值 |
| --- | --- |
| 项目 | PocketScore AI |
| 阶段 | V1.1-C.2.2.1 · Railway Staging Cloud Acceptance |
| 应用版本 | V1.1（`app_version`） |
| 报告日期 | 2026-11-26 |

## 2. Git

| 项 | 值 |
| --- | --- |
| 分支 | `pocketscore-v1.1-b` |
| HEAD | `9856378b4084436ed395a9856e8d85516c59db1c` |
| 工作区 | 干净，与 `origin/pocketscore-v1.1-b` 同步 |
| `origin/main` | `9e7cd41`（未合并任何 V1.1 提交） |
| C.2.2 代码 | `8e47b41` + `1dcaecc`，均在 HEAD 祖先链 |
| 本轮是否推送 | ❌ 否（零推送；仅本地文档修正待提交） |

## 3. Railway 项目 / 环境 / 服务

| 项 | 值 |
| --- | --- |
| Railway Project | **未确认**（无登录权限） |
| Railway Environment | **未确认**（无法证明是 Staging 而非 Production） |
| Railway Service | **未确认**（建议名 `pocketscore-api`，未核实是否已存在） |
| 是否创建/修改任何云资源 | ❌ 否 |

## 4. Railway Deployment ID

**未执行**（无部署）。

## 5. 实际云端 URL

**不存在**。本报告不提供任何 URL —— 域名需要在部署后从 Railway 控制台读取，我不会编造。

## 6. 环境变量映射表（名称，不含密钥）

依据 `backend/app/core/config.py`（`env_prefix="POCKETSCORE_"`，无别名）：

| 配置用途 | 代码读取名称 | Railway 应配置 | 必需 |
| --- | --- | --- | --- |
| 环境 | `POCKETSCORE_ENVIRONMENT` | `staging` | ✅ |
| Session Secret | `POCKETSCORE_SESSION_SECRET` | 随机 ≥32 字符 | ✅ |
| Token 加密密钥 | `POCKETSCORE_TOKEN_ENCRYPTION_KEY` | Fernet key | ✅ |
| 访问门禁令牌 | `POCKETSCORE_ACCESS_GATE_TOKEN` | 随机 hex | ✅ |
| 门禁模式 | `POCKETSCORE_ACCESS_GATE_MODE` | 可省略（auto） | 建议 |
| CORS | `POCKETSCORE_CORS_ORIGINS` | `https://engernages-lab.github.io` | ✅ |
| 私有网络源 | `POCKETSCORE_ALLOW_PRIVATE_NETWORK_SOURCES` | `false` | ✅ |
| 数据库 | `POCKETSCORE_DATABASE_URL` | `sqlite:////data/pocketscore.db`（**四斜杠**） | ✅ |
| 存储目录 | `POCKETSCORE_STORAGE_DIR` | `/data/storage` | ✅ |
| 模型预加载 | `POCKETSCORE_MODEL_PRELOAD` | `true` | 建议 |
| 上传上限 | `POCKETSCORE_MAX_UPLOAD_MB` | `50` | ✅ |
| HTTP 端口 | `PORT`（shell 展开，非 Settings） | Railway 自动注入 | 自动 |

> 详细代码依据见 `02-env-var-audit.md`。**裸写不带前缀的变量名会被完全忽略**。

## 7. Docker 部署结果

| 项 | 结果 |
| --- | --- |
| 镜像构建（CI） | ✅ run `45828419659`（`1dcaecc`） |
| Railway 构建 | ⛔ **未执行** |
| 部署状态 | ⛔ **未部署** |

## 8. Healthcheck 结果

| 项 | 结果 |
| --- | --- |
| 云端 `/health` | ⛔ 未执行（无域名） |
| 云端 `/ready` | ⛔ 未执行 |
| Railway Healthcheck 状态 | ⛔ 未执行 |
| 本地等价（C.2.2 冒烟） | `/health` 200、`/ready` `ready:true`、模型 3.3 s / 预热 1.9 s |

## 9. Access Gate 云端测试结果

| 编号 | 测试 | 预期 | 云端结果 |
| --- | --- | --- | --- |
| AG-01 | `/health` 无凭据 | 200 | ⛔ 未执行 |
| AG-02 | `/ready` 无凭据 | 200 | ⛔ 未执行 |
| AG-03 | `/docs` 无凭据 | 401 | ⛔ 未执行 |
| AG-04 | 受保护 API 无凭据 | 401 | ⛔ 未执行 |
| AG-05 | 错误 Token | 401 | ⛔ 未执行 |
| AG-06 | 正确 Token | 200 | ⛔ 未执行 |
| AG-07 | 连续失败 | 429 | ⛔ 未执行（且**不允许**对生产/暂存做压测式验证） |
| AG-08 | OPTIONS 预检 | 符合 CORS | ⛔ 未执行 |
| AG-09 | 门禁状态 | enabled=true | ⛔ 未执行 |
| AG-10 | Token 不出现在响应 | 通过 | ⛔ 未执行 |

**已有的非云端证据**（不能算云端通过）：
- CI 内 `verify-access-gate.sh` 在容器上通过（run `45828419659` 步骤 19）；
- 本机真实进程：匿名 `/api/v1/documents` → 401、带 bearer → 200；
- 单元测试 19 项覆盖 401/429/OPTIONS/Basic/描述不泄漏。

## 10. 真实音频上传结果

⛔ **未执行**。测试音频已就绪：`tests/fixtures/melody.wav`（WAV PCM 单声道，77.6 KB，≈1.6 s）。

## 11. Basic Pitch 云端推理结果

⛔ **未执行**。
本机与 CI 的真实推理结果为：`4 notes, pitches [60,64,67,72]`，不可作为云端结果引用。

## 12. MusicDocument 生成结果

⛔ **未执行**（云端）。本地/CI：4 个音符事件，网格谱 3 / 数字谱 4。

## 13. 项目保存和读取结果

⛔ **未执行**（云端）。

## 14. Volume 持久化结果

| 项 | 结果 |
| --- | --- |
| Volume 是否存在 | ⛔ 未确认 |
| 是否挂载到 `/data` | ⛔ 未确认 |
| 写入权限 | ⛔ 未确认 |
| WAL 是否正常 | ⛔ 未确认 |
| 音频能否写入 | ⛔ 未确认 |
| 重启后是否保留 | ⛔ 未确认 |

## 15. 服务重启后恢复结果

⛔ **未执行**。

## 16. CORS 检查结果

| 项 | 结果 |
| --- | --- |
| 云端 CORS 响应头 | ⛔ 未执行 |
| 是否使用通配符 | 代码侧为显式来源列表（`settings.cors_origins`），云端值 ⛔ 未确认 |
| 前端 Origin 是否允许 | 建议值 `https://engernages-lab.github.io`，云端 ⛔ 未确认 |

## 17. 前端 Token 泄漏检查结果

| 检查 | 结果 |
| --- | --- |
| `frontend/dist` 含 `ACCESS_GATE_TOKEN` | ✅ 无 |
| 含 `SESSION_SECRET` / `TOKEN_ENCRYPTION_KEY` | ✅ 无 |
| 含 `Bearer` 构造 | ✅ 无 |
| 含 CI 测试令牌 | ✅ 无 |
| Sourcemap 泄漏源码 | ✅ 0 个 `.map` |
| `VITE_*` 中是否放入共享令牌 | ✅ 无 |

## 18. 安全检查结果

| 风险项 | 状态 |
| --- | --- |
| 门禁被关闭 | ✅ 代码层面不可能（staging 缺凭据即拒绝启动，显式 off 也拒绝） |
| 默认 Session Secret | ✅ 代码拒绝（`validate_hardened_secrets`） |
| 默认 Encryption Key | ✅ 拒绝 |
| 密钥泄漏到 Git | ✅ 无（tracked 文件扫描通过） |
| 密钥进入前端 | ✅ 无（§17） |
| 私有网络音频源 | ✅ staging 强制 `false` |
| CORS 任意来源 | ✅ 代码不含通配符默认；云端值待确认 |
| SQLite 写入临时目录 | ⚠️ **配置风险**：默认值是相对路径，必须显式设 `sqlite:////data/...` |
| 上传超限 | ✅ 415/413 逻辑与测试齐备 |
| 未授权访问 | ✅ 本地/CI 已验证 401，云端待验 |
| 启动失败可诊断 | ✅ 启动期打印每条 `configuration error` |

## 19. Railway CPU / Memory / Restart 指标

**未采集**（无控制台访问）。本报告不提供任何 CPU、内存、流量、费用数字。

## 20. 自动化测试统计

| 层级 | 结果 | 说明 |
| --- | --- | --- |
| 后端 pytest | **346 passed** | 本地执行（本轮实跑） |
| 前端 vitest | **103 passed**（12 文件） | 本地执行 |
| TypeScript | exit 0 | 本地执行 |
| 生产构建 | 9.92 s，0 sourcemap | 本地执行 |
| Ruff | All checks passed | 本地执行 |
| Docker CI | 29 步全绿（`45828419659` @ `1dcaecc`） | **远程**执行，非本地 |
| Railway 云端测试 | **0 项执行** | 无凭据 |

## 21. 人工验证记录

| 项 | 记录 |
| --- | --- |
| 审计者 | 本次执行（自动化代理） |
| Railway 控制台操作 | 无 |
| 云端浏览器验证 | 无 |
| 密钥生成 | 未生成（未部署，不产生真实凭据） |

## 22. 遗留风险

| # | 风险 | 等级 | 说明 |
| --- | --- | --- | --- |
| 1 | 无用户认证与数据隔离 | P1（已知设计） | 共享令牌 = 同一服务内全部项目可见 |
| 2 | 共享令牌非账号体系 | P1 | 无法审计到人 |
| 3 | SQLite + 单实例 | P2 | 扩展性受限，写并发有锁风险 |
| 4 | 内存限流不持久 | P3 | 重启清零；多副本不共享 |
| 5 | 推理线程不可中断 | P2 | 停机时任务停在中间态 |
| 6 | 容器以 root 运行 | P2 | Volume 权限未在云端核实 |
| 7 | DB/存储路径默认是相对路径 | **P1（部署必踩）** | 必须显式绝对路径，否则重启丢数据 |
| 8 | 长音频资源占用 | P3 | 120 s 音频本机峰值 262 MB |
| 9 | 云端指标未知 | P3 | 未采集 |

## 23. 未执行测试（明确清单）

1. Railway 部署（构建、发布、健康检查）
2. AG-01…AG-10 全部云端访问门禁用例
3. 云端真实音频上传与 Basic Pitch 推理
4. 云端 MusicDocument / 项目保存 / 读取
5. Volume 持久化与容器重建
6. 服务重启恢复
7. 云端 CORS 与预检
8. 云端 429 限流实测
9. 云端稳定性观察（重启计数、500、超时、SQLite 锁定）
10. Railway CPU / Memory / 计费指标

## 24. 最终验收结论

### BLOCKED

依据 §18.3：

> 「没有 Railway 登录权限」「用户尚未授权部署」「没有真实 Railway 云端部署，最多只能报告部署准备完成，不能报告云端验收通过」

| 阻塞项 | 具体事实 |
| --- | --- |
| Railway 登录 | `railway` 命令不存在；`~/.railway/config.json` 不存在；无 `RAILWAY_*` 环境变量 |
| CLI 可用性 | `npx @railway/cli` 安装被执行环境拒绝（`npm error The operation was rejected by your operating system`） |
| 部署授权 | 用户本轮仅给出执行提示词，未明确「授权 AI 直接操作 Railway」 |
| 环境确认 | 无法确认目标 Environment 是 Staging（存在误部署 Production 的风险） |

**已完成**（部署准备度 100%）：Git 审计、环境变量映射表（代码级核验）、部署配置静态核验、
本地回归（346/103/tsc/build/密钥扫描）、CI 绿色记录确认。

**未完成**：一切需要真实云端的环节。

## 25. 下一阶段建议 / 你可以直接执行的步骤

### 第 0 步：准备凭据（在你的机器上，不要贴到对话里）

```bash
railway login                    # 浏览器授权
railway status                   # 确认 Project / Environment
railway environment              # 确认当前是 staging，不是 production
```

### 第 1 步：创建/确认资源

```bash
railway service                  # 确认服务名（建议 pocketscore-api）
railway volume list              # 确认 Volume 已挂到 /data
```

### 第 2 步：录入环境变量（控制台，名称必须带前缀）

```dotenv
POCKETSCORE_ENVIRONMENT=staging
POCKETSCORE_SESSION_SECRET=<随机 48 字节>
POCKETSCORE_TOKEN_ENCRYPTION_KEY=<Fernet key>
POCKETSCORE_ACCESS_GATE_TOKEN=<随机 hex 24 字节>
POCKETSCORE_CORS_ORIGINS=https://engernages-lab.github.io
POCKETSCORE_ALLOW_PRIVATE_NETWORK_SOURCES=false
POCKETSCORE_DATABASE_URL=sqlite:////data/pocketscore.db
POCKETSCORE_STORAGE_DIR=/data/storage
POCKETSCORE_MODEL_PRELOAD=true
POCKETSCORE_MAX_UPLOAD_MB=50
```

生成方式（本地执行，不要上传）：

```bash
python -c "import secrets; print('SESSION', secrets.token_hex(48))"
python -c "from cryptography.fernet import Fernet; print('FERNET', Fernet.generate_key().decode())"
python -c "import secrets; print('GATE', secrets.token_hex(24))"
```

### 第 3 步：部署

```bash
railway up --service pocketscore-api
```

### 第 4 步：验收（部署后立刻执行）

```bash
export STAGING_URL="https://<控制台显示的真实域名>"
export POCKETSCORE_ACCESS_GATE_TOKEN="<第 2 步生成的令牌>"
scripts/deploy/verify-access-gate.sh "$STAGING_URL" "$POCKETSCORE_ACCESS_GATE_TOKEN"
```

期望：`/health` 200、`/ready` 200、匿名 `/api/v1/documents` 401、带令牌 200、错令牌 401。

```bash
PSC_STAGING_URL="$STAGING_URL" POCKETSCORE_ACCESS_GATE_TOKEN="$POCKETSCORE_ACCESS_GATE_TOKEN" \
  npx playwright test tests/e2e/staging-smoke.spec.ts
```

### 第 5 步：把结果给我

请提供（**不要包含任何密钥/token**）：域名、Deployment ID、两个验收脚本的输出、
以及是否需要我继续做持久化与重启验收。

拿到后我会补完 §5、§7–§15，并把本报告从 BLOCKED 改为 PASS 或 CONDITIONAL PASS。

### 下一阶段（完成后才建议启动）

**V1.1-C.3 · PostgreSQL & Object Storage Migration** —— 不属于本阶段范围，未开始。

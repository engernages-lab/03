# PocketScore AI V1.1-C.2.2 · 访问门禁与 Railway Staging 报告

---

## 1. 阶段信息

| 项 | 值 |
| --- | --- |
| 阶段 | V1.1-C.2.2 · Staging Access Gate + Railway Deployment |
| 日期 | 2026-11-26 |
| 分支 | `pocketscore-v1.1-b` |
| 开始时 HEAD | `9dca1ad` |
| 完成时 HEAD | `1dcaecc` + 本次报告提交 |
| 未提交修改 | 无（提交后干净） |
| **结论** | **CONDITIONAL PASS** |

---

## 2. 你要的两件事，分别做到什么程度

| 要求 | 状态 |
| --- | --- |
| 访问保护纳入**部署强制门禁**，不留到部署后 | ✅ **已完成并在 CI 验证**（三层：启动拒绝 / 运行时 401 / 部署步骤红灯） |
| 不重复开发 Docker 验证系统，保留工作流并继续触发 | ✅ 沿用 C.2.1 工作流；仅补门禁令牌与一个断言步骤；paths 增 `scripts/deploy/**` |

**未完成的一件事**：真正的 Railway 云端部署。原因是**我没有 Railway 凭据**（CLI 未安装、无登录会话），
而凭据不应出现在对话里。部署所需的一切已就绪，你执行两条命令即可（§5）。

---

## 3. 门禁实现（三层，缺一不可）

### 3.1 启动层：忘配置就起不来

`Settings.validate_hardened_secrets()` 在 staging/production 启动时检查：

- 没有 `POCKETSCORE_ACCESS_GATE_TOKEN`，也没有 `USER`+`PASSWORD` → **RuntimeError，进程不启动**；
- 显式 `ACCESS_GATE_MODE=off` → 同样拒绝；
- `mode=token` 但 token 为空 / `mode=basic` 但只给了用户名 → 分别报错。

development / test 保持开放，本地开发不受影响。

### 3.2 运行时层：除探针外全部要凭据

| 路径 | 行为 |
| --- | --- |
| `/health`、`/ready` | 放行（平台健康检查无法带凭据） |
| `OPTIONS` | 放行（CORS 预检不带凭据，拦了浏览器就废了） |
| 其余（`/api/v1/*`、`/static/*`、SPA、`/docs`） | 无凭据/错凭据 → **401** `ACCESS_GATE_REQUIRED` |

- 支持 `Authorization: Bearer <token>` 与 HTTP Basic；
- 401 响应**不含**任何凭据信息；日志只记 method/path/IP/attempt；
- 单 IP 60 s 内 20 次失败 → **429 `TOO_MANY_ATTEMPTS`**；
- `/ready` 报 `access_gate.mode/enabled/token_configured`，让部署探针能区分"已保护"与"意外开放"。

### 3.3 部署层：CI 里的一条硬断言

`scripts/deploy/verify-access-gate.sh`（工作流中的 **Access gate enforced** 步骤）：

```
/health 无凭据            → 必须 200
GET /api/v1/documents 无凭据 → 必须 401 + ACCESS_GATE_REQUIRED
POST /api/v1/audio/upload 无凭据 → 必须 401
带正确令牌                → 必须 200
带错误令牌                → 必须 401
```

任一不满足 → **流水线红**。也就是说，这条流水线**在结构上无法产出**一个裸奔的 staging 镜像。

---

## 4. 验证证据

### 4.1 CI（`45828419659` @ `1dcaecc`，29 步全绿）

| 步骤 | 耗时 | 结果 |
| --- | --- | --- |
| Build image | 25 s | ✅ |
| Verify image contents | 6 s | ✅ |
| PORT injection (8123) | 21 s | ✅ |
| **Access gate enforced** | 0 s | ✅ |
| Real Basic Pitch transcription（带令牌） | 14 s | ✅ |
| Persistence across rebuild（带令牌） | 58 s | ✅ |
| Graceful shutdown | 21 s | ✅ |

### 4.2 本机（真实进程 + 真实模型）

```
/health                无凭据 → 200
/api/v1/documents      无凭据 → 401
/api/v1/documents      带 bearer → 200
transcription --token  → 4 notes, pitches [60,64,67,72], 2.477 s
gated smoke            → startup 9.79 s, /ready ready:true, upload 201, job completed,
                         document 200, 重启后数据仍在
```

### 4.3 回归

后端 **346 passed**（+19 门禁测试）、前端 **103 passed**、Ruff 通过、`tsc` 通过。

### 4.4 过程中两次失败（如实）

| run | 失败点 | 根因 |
| --- | --- | --- |
| `45823317201` | 真实扒谱/415 步骤 | 脚本调被保护的 API 没带令牌 —— 门禁**按设计**拦住了 |
| `45827062415` | 持久化 | shell 补丁把 `${TEST_ACCESS_TOKEN}` 写成空串 → 容器缺凭据拒绝启动 |

第二次尤其说明启动门禁有效：少一个字符，容器就不启动。

---

## 5. 你需要执行的两条命令（部署）

```bash
railway login                                   # 浏览器授权一次
railway up --service pocketscore-api            # 仓库根执行，railway.json 已就绪
```

控制台需设置（一次性，**名称必须带 `POCKETSCORE_` 前缀，代码没有别名**）：
`POCKETSCORE_ENVIRONMENT=staging`、`POCKETSCORE_SESSION_SECRET`、
`POCKETSCORE_TOKEN_ENCRYPTION_KEY`、**`POCKETSCORE_ACCESS_GATE_TOKEN`**（不设则容器起不来）、
`POCKETSCORE_CORS_ORIGINS=https://engernages-lab.github.io`、`POCKETSCORE_ALLOW_PRIVATE_NETWORK_SOURCES=false`、
`POCKETSCORE_DATABASE_URL=sqlite:////data/pocketscore.db`、`POCKETSCORE_STORAGE_DIR=/data/storage`、
`POCKETSCORE_MODEL_PRELOAD=true`、`POCKETSCORE_MAX_UPLOAD_MB=50`；Volume 挂 `/data`。

> 注意 `sqlite:////data/...` 是**四条斜杠**（绝对路径）。写成三条斜杠会落到容器内
> `/app/data/`，重启即丢数据（C.2.2.1 实测确认）。

部署后立刻验收（两条都已就绪）：

```bash
scripts/deploy/verify-access-gate.sh https://<service>.up.railway.app "$POCKETSCORE_ACCESS_GATE_TOKEN"
PSC_STAGING_URL=https://<service>.up.railway.app \
POCKETSCORE_ACCESS_GATE_TOKEN=<token> \
npx playwright test tests/e2e/staging-smoke.spec.ts
```

---

## 6. 必须说清的边界

1. **这不是认证**：单一共享凭据，不做用户隔离，持有凭据者能看到全部项目。它的作用是"把 staging 挡在互联网之外"，不是"多用户安全"。C.5 才做认证。
2. **GitHub Pages 前端仍不可用**：页面没有这枚凭据，调 staging 会 401。这是设计，避免让人误以为产品已可公开。
3. **云端未部署**：无凭据，未执行；未编造 URL 或云端数据。
4. 门禁 429 防爆破只做了单测，未做容器内压测。

---

## 7. 结论：CONDITIONAL PASS

| 判定条件 | 结果 |
| --- | --- |
| 访问保护是部署强制门禁 | ✅ 三层强制 + CI 断言 |
| 不留到部署后补 | ✅ 缺凭据时容器**根本无法启动** |
| Docker 验证未被重复开发 | ✅ 沿用 C.2.1 工作流 |
| Docker 相关变更继续触发验证 | ✅ paths 含 backend/frontend/docker/deploy |
| 云端部署完成 | ❌ 缺 Railway 凭据 |
| 云端验收（health/ready/扒谱/持久化） | ❌ 无 URL |

依据 §19 的 CONDITIONAL 条款："非核心项待补、且可明确说明缺口的真实原因"。
**缺口只有一个**：需要你在 Railway 上执行一次 `railway login` + `railway up`。

---

## 8. 下一步

1. 你完成部署 → 跑 §5 的两条验收命令；
2. 我把云端结果写进 `04-railway-staging-report.md`，C.2.2 转 PASS；
3. 之后进入 **C.3（PostgreSQL + 对象存储 + 备份）**；
4. 不要在本阶段公开 staging：无用户隔离，等 C.5。

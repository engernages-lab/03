# V1.1-C.2.2 · 04 Railway Staging 部署报告

> **Railway Deployment: NOT EXECUTED**
> 阻塞原因：本机没有 Railway 凭据（`railway` CLI 未安装、无登录会话）。
> 这是**凭据**阻塞，不是代码或配置阻塞 —— 部署所需的一切都已就绪并在 CI 中验证过。

---

## 1. 为什么我不能自己完成部署

| 前提 | 状态 |
| --- | --- |
| `railway` CLI | ❌ 未安装 |
| Railway 账号登录 | ❌ 无（需要浏览器端 `railway login` 或 API token） |
| 项目/环境可见性 | ❌ 无法列出 |
| Docker 本地验证 | ✅ 已在 GitHub Actions 完成（C.2.1） |
| 访问门禁 | ✅ 已实现并在 CI 中强制验证（C.2.2） |

我不会索取你的 Railway token（凭据不应出现在对话里）。**你用两条命令就能完成**，见 §3。

## 2. 已就绪的部署配置

`railway.json`（仓库根）：

```json
{
  "build": { "builder": "DOCKERFILE", "dockerfilePath": "backend/Dockerfile" },
  "deploy": {
    "healthcheckPath": "/health",
    "healthcheckTimeout": 180,
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 5,
    "numReplicas": 1
  }
}
```

必须设置的环境变量（staging）：

| 变量 | 说明 |
| --- | --- |
| `POCKETSCORE_ENVIRONMENT=staging` | 触发生成环境规则（密钥与门禁强制） |
| `POCKETSCORE_SESSION_SECRET` | ≥32 字符随机值 |
| `POCKETSCORE_TOKEN_ENCRYPTION_KEY` | Fernet key（否则重启后令牌失效） |
| **`POCKETSCORE_ACCESS_GATE_TOKEN`** | **门禁凭据；不设则容器拒绝启动** |
| `POCKETSCORE_CORS_ORIGINS=https://engernages-lab.github.io` | 精确来源 |
| `POCKETSCORE_ALLOW_PRIVATE_NETWORK_SOURCES=false` | 关闭 SSRF 面 |
| `POCKETSCORE_DATABASE_URL=sqlite:////data/pocketscore.db` | 卷内 SQLite |
| `POCKETSCORE_STORAGE_DIR=/data/storage` | 卷内音频 |
| `POCKETSCORE_MODEL_PRELOAD=true` | 启动预热 |
| `POCKETSCORE_MAX_UPLOAD_MB=50` | 首发收敛 |

Volume：挂载到 `/data`（存 DB + 音频 + MIDI）。

## 3. 你要执行的两条命令

```bash
# 1) 登录（浏览器一次）
railway login

# 2) 在仓库根部署（railway.json 已指定 Dockerfile 与健康检查）
railway up --service pocketscore-api
```

变量与卷在 Railway 控制台设置一次（见 §2 表）。部署后立刻跑门禁验证：

```bash
scripts/deploy/verify-access-gate.sh https://<your-service>.up.railway.app "$POCKETSCORE_ACCESS_GATE_TOKEN"
```

期望输出：

```text
/health -> 200 ; /ready -> 200
GET /api/v1/documents (no credentials) -> 401
POST /api/v1/audio/upload (no credentials) -> 401
GET /api/v1/documents (bearer) -> 200
ACCESS GATE OK
```

再跑云端冒烟（真实扒谱）：

```bash
PSC_STAGING_URL=https://<your-service>.up.railway.app \
POCKETSCORE_ACCESS_GATE_TOKEN=<token> \
npx playwright test tests/e2e/staging-smoke.spec.ts
```

> 注：`staging-smoke.spec.ts` 目前直接用 `request`，若门禁开启需要带 `Authorization`。
> 部署前我会补一个 5 行改动让它读取 `POCKETSCORE_ACCESS_GATE_TOKEN`（见 §5）。

## 4. 部署后的访问边界（必须明确）

- staging **不是公开产品**：持凭据者能看到**全部**项目（无用户隔离）；
- GitHub Pages 前端**没有**凭据，调用 staging 会得到 401 —— 这是设计，不是 bug；
- 因此不要把 staging 地址发给非测试者；对外发布必须等 C.5 的认证。

## 5. 本轮未做但下一轮要补的 3 件小事

1. `tests/e2e/staging-smoke.spec.ts` 支持 `POCKETSCORE_ACCESS_GATE_TOKEN`（1 个 header）。
2. 把 `verify-access-gate.sh` 接进一个 `deploy-staging` 手动工作流（`workflow_dispatch`），
   让"部署后验收"也能在 CI 留痕。
3. 记录一次真实的公网 `/ready` 与容器冷启动耗时（目前只有 CI 内网数据）。

## 6. 成本与影响（不编造金额）

| 项 | 说明 |
| --- | --- |
| 新增资源 | 1 个 Web 服务 + 1 个 Volume |
| 内存 | ≥1 GB（推理峰值 262 MB + Web 常驻） |
| 计费 | 按 Railway 实际用量；本报告不估算金额 |
| 对现有服务影响 | 无：不动 GitHub Pages（`origin/main` 未变），不删任何资源 |
| 回滚 | 保留上一镜像；Volume 不受回滚影响 |

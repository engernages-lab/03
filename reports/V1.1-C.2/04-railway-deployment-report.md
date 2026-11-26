# V1.1-C.2 · 04 Railway 部署报告（Railway Deployment）

> **Railway Deployment: NOT EXECUTED**

---

## 1. 未执行的原因

| 前提 | 状态 |
| --- | --- |
| 用户授权 | ❌ 本阶段默认授权仅含"代码修改 + 本地测试 + 本地 Docker 验证"，云端部署需另行授权 |
| Railway 账号登录 | ❌ 无 CLI，也无浏览器会话凭据 |
| Railway CLI | ❌ `railway --version` 命令不存在 |
| Docker 本地验证 | ⛔ 未通过（本机无 Docker，见 03 报告）——按阶段门禁不得进入云端部署 |

按执行顺序表（本阶段提示词 §八），第 11 步"Railway Staging 部署"的前置条件是第 8–10 步
（Docker 构建 / 运行 / 真实扒谱）通过。前置未通过，因此**不进入部署**，也不伪造部署结果。

---

## 2. 已完成的部署准备（可直接使用的交付物）

### 2.1 `railway.json`（仓库根）

```json
{
  "$schema": "https://railway.com/railway.schema.json",
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

要点：
- `dockerfilePath` 指向 `backend/Dockerfile`（否则 Railway 在仓库根找不到 Dockerfile）。
- `healthcheckPath=/health` 为轻量探针（不加载模型，不会在每次探测触发 3.7 s JIT）。
- `healthcheckTimeout=180` 覆盖冷启动（实测启动 9 s，留足余量）。
- `numReplicas=1`：SQLite + 本地文件存储不支持多副本。

### 2.2 容器启动

```text
sh -c exec python -m uvicorn app.main:app --host 0.0.0.0 \
       --port "${PORT:-8000}" --timeout-graceful-shutdown 25 \
       --proxy-headers --forwarded-allow-ips='*'
```

`exec` 保证 uvicorn 取代 shell 成为 PID 1，SIGTERM 直达；`${PORT:-8000}` 兼容本地无 `PORT`。

### 2.3 需要设置的 Railway 变量（脱敏）

| 变量 | 必填 | 建议值 |
| --- | --- | --- |
| `POCKETSCORE_ENVIRONMENT` | ✅ | `staging` |
| `POCKETSCORE_DEBUG` | ✅ | `false` |
| `POCKETSCORE_LOG_JSON` | ✅ | `true` |
| `POCKETSCORE_SESSION_SECRET` | ✅ | `openssl rand -base64 48`（≥32 字符，缺失则拒绝启动） |
| `POCKETSCORE_TOKEN_ENCRYPTION_KEY` | ✅ | `Fernet.generate_key()`（缺失则拒绝启动） |
| `POCKETSCORE_CORS_ORIGINS` | ✅ | `https://engernages-lab.github.io` |
| `POCKETSCORE_ALLOW_PRIVATE_NETWORK_SOURCES` | ✅ | `false` |
| `POCKETSCORE_DATABASE_URL` | ✅ | `sqlite:////data/pocketscore.db` |
| `POCKETSCORE_STORAGE_DIR` | ✅ | `/data/storage` |
| `POCKETSCORE_MODEL_PRELOAD` | ✅ | `true` |
| `POCKETSCORE_MAX_UPLOAD_MB` | 建议 | `50`（首发收敛，验证后放宽） |
| `POCKETSCORE_MAX_CONCURRENT_INFERENCES` | ✅ | `1` |
| `POCKETSCORE_INFERENCE_TIMEOUT_SECONDS` | ✅ | `300` |
| `PORT` | 平台注入 | 无需手工设置 |
| `RAILWAY_DOCKERFILE_PATH` | 备选 | 若平台不读 `railway.json`，用 `backend/Dockerfile` |

### 2.4 Volume

| 项 | 值 |
| --- | --- |
| 挂载路径 | `/data` |
| 内容 | `pocketscore.db`（SQLite，WAL）、`storage/audio/<sha2>/<sha256><ext>`、`storage/midi/`、`storage/artwork/` |
| 重建影响 | 卷独立于镜像层，重新部署不清空（已在本地等价验证中复现"重启后数据仍在"） |
| 备份 | **无**（C.3 处理） |

### 2.5 Staging 访问限制方案（本阶段必须解决，否则不公开）

当前后端**没有认证**，因此不能作为开放服务。可选方案（按推荐顺序）：

1. **Railway 环境级访问控制**：把服务放在私有环境，仅通过 Railway 的访问凭证访问；
   前端不指向它，或指向时需要额外头。
2. **临时访问层**：在 Railway 前挂一层 Basic Auth（Railway 支持自定义域名 + 代理，
   或用 Cloudflare Access）。注意：Basic Auth 只是访问门槛，不是应用级认证。
3. **不公开**：只做内部 curl/脚本验证，前端继续用本地 API。

**推荐**：C.2 阶段不公开；等 C.5 完成认证后再考虑对外。若必须先给少量测试者，
用方案 2，并把测试者范围写进报告。

---

## 3. 若获得授权，部署步骤（可直接执行）

```bash
# 0) 前置：本地 Docker 验证通过（见 03 报告 §5）
# 1) 构建前端产物（镜像会 COPY frontend/dist）
cd frontend && npm ci && npm run build && cd ..

# 2) 登录并关联项目
railway login
railway link            # 选择目标 project / environment = staging

# 3) 设置变量（逐条，值不要写进仓库）
railway variables --set POCKETSCORE_ENVIRONMENT=staging \
  --set POCKETSCORE_SESSION_SECRET=... \
  --set POCKETSCORE_TOKEN_ENCRYPTION_KEY=... \
  --set POCKETSCORE_CORS_ORIGINS=https://engernages-lab.github.io \
  --set POCKETSCORE_ALLOW_PRIVATE_NETWORK_SOURCES=false \
  --set POCKETSCORE_DATABASE_URL=sqlite:////data/pocketscore.db \
  --set POCKETSCORE_STORAGE_DIR=/data/storage \
  --set POCKETSCORE_MODEL_PRELOAD=true \
  --set POCKETSCORE_MAX_UPLOAD_MB=50

# 4) 挂载卷到 /data（控制台操作一次）
# 5) 部署
railway up --service pocketscore-api

# 6) 验收
curl -s https://<domain>/health
curl -s https://<domain>/ready | jq '.ready, .checks.model'
curl -s -F "file=@tests/fixtures/melody.wav" https://<domain>/api/v1/audio/upload
# 然后 POST /api/v1/transcription/jobs/{id}/run，检查 events_produced > 0
```

## 4. 成本与影响（不编造金额）

| 项 | 说明 |
| --- | --- |
| 新增资源 | 1 个 Web 服务 + 1 个 Volume（若选方案 B 再加 PostgreSQL） |
| 内存需求 | ≥1 GB（推理峰值 262 MB + Web 常驻 ~180 MB + 余量） |
| CPU | 1 vCPU 可用；并发 1 |
| 计费 | 按 Railway 实际用量计价；**本报告不给出金额估算** |
| 对现有服务的影响 | 无：不触碰当前 GitHub Pages 静态站；不删除任何现有资源 |
| Volume 是否新建 | 是（新环境）；不影响其他环境 |
| 回滚 | 保留上一镜像 tag；Volume 不受回滚影响 |

---

## 5. 结论

- **部署配置已就绪**（`railway.json`、Dockerfile、变量清单、卷布局、验收命令）。
- **部署未执行**，且按门禁**不应执行**：本地 Docker 验证缺失。
- 需要用户决策的两件事：
  1. 是否提供 Docker 环境（或授权我在 GitHub Actions 上跑构建验证）；
  2. 是否授权 Railway Staging 部署，以及采用哪种访问限制方案。

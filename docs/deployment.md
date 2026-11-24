# 部署指南 · PocketScore AI V1.0-A

本项目有两种部署形态，二者都已在本机验证过：

| 形态 | 说明 | 验证方式 |
| --- | --- | --- |
| **单服务（推荐）** | 后端容器同时托管 SPA（`frontend/dist`），同源、无需 CORS | 本机 `production` 模式实测：`/`、`/scores` 返回 HTML，`/api/v1/health` 返回 JSON |
| **前后端分离** | 前端静态托管（Vercel/对象存储），后端独立容器 | 配置已提供（`frontend/vercel.json`），需托管账号 |

---

## 1. 单服务部署（Docker）

```bash
# 1) 构建前端产物
cd frontend && npm ci && npm run build && cd ..

# 2) 构建并启动（API + SPA 同源）
docker compose up --build
# 打开 http://localhost:8000
```

`backend/Dockerfile` 会把 `frontend/dist` 打进镜像；FastAPI 在检测到该目录时
自动把 `/` 交给 SPA（`POCKETSCORE_SERVE_FRONTEND=true`，默认开启）。

### 必需的环境变量

| 变量 | 说明 |
| --- | --- |
| `POCKETSCORE_ENVIRONMENT=production` | 关闭 debug |
| `POCKETSCORE_TOKEN_ENCRYPTION_KEY` | Fernet 密钥，加密第三方令牌。**必须自行生成** |
| `POCKETSCORE_SESSION_SECRET` | 会话密钥 |
| `POCKETSCORE_DATABASE_URL` | 默认 `sqlite:////data/pocketscore.db` |
| `POCKETSCORE_STORAGE_DIR` | 音频/封面/密钥目录，需持久卷 |
| `POCKETSCORE_CORS_ORIGINS` | 分离部署时填写前端域名 |

生成密钥：

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 健康检查

- 存活：`GET /api/v1/health`
- 就绪：`GET /api/v1/health/ready`（数据库 / FFmpeg / MIDI）
- 反向代理/平台探针应指向 `/api/v1/health/ready`

---

## 2. 前后端分离部署

### 2.1 后端（Render / Fly.io / Railway / 自建）

- 使用 `backend/Dockerfile`，监听 `8000`。
- 挂载持久卷到 `/data`（SQLite + 音频资产）。
- 设置上表环境变量，并把前端域名写入 `POCKETSCORE_CORS_ORIGINS`。
- Render 可直接使用仓库根目录的 `render.yaml`（Blueprint）。

### 2.2 前端（Vercel / Netlify / Nginx）

```bash
cd frontend
VITE_API_BASE_URL=https://your-api.example.com npm run build
```

- `VITE_API_BASE_URL` 为空时前端使用同源 `/api`（适合单服务）。
- 分离部署必须设置该变量为后端公网地址。
- `frontend/vercel.json` 已包含 SPA rewrite 与静态资源缓存头。
- Nginx 需要 `try_files $uri $uri/ /index.html;`。

### 2.3 OAuth 回调

第三方回调地址必须与配置一致，例如：

```
POCKETSCORE_SPOTIFY_REDIRECT_URI=https://your-api.example.com/api/v1/sources/spotify/callback
```

回调地址只从配置读取，**不接受请求体指定**。

---

## 3. 数据库迁移

```bash
cd backend
alembic upgrade head          # 建表
alembic revision --autogenerate -m "describe change"   # 改表后生成迁移
```

基线迁移 `0001_initial` 会创建全部 16 张业务表（已在本机验证）。
生产建议用 `alembic upgrade head` 而不是 `create_all`（后者仅用于本地快速启动）。

---

## 4. 部署后自检清单

1. `GET /api/v1/health` → `status: ok`，且 `ffmpeg.available == true`。
2. `GET /api/v1/health/ready` → `status: ready`。
3. 打开首页，左侧导航全部可用（无 404）。
4. 上传一个 WAV → 出现在资料库 → 播放成功。
5. 导入一个 `.mid` → 进入谱面编辑器 → 两谱都渲染。
6. `GET /docs` 可访问 OpenAPI。
7. 检查日志中无 `INTERNAL_ERROR`。

---

## 5. 当前部署状态（如实记录）

| 项 | 状态 |
| --- | --- |
| 本地生产模式（单服务） | ✅ 已实测通过（`/`、`/scores`、`/api/v1/health`、`/docs` 均 200） |
| Docker 镜像构建 | ⚠️ 未实际构建（本机无 Docker） |
| 公网部署 | ❌ **未执行** —— 需要用户的托管账号/域名与凭据 |
| GitHub Push | ❌ **未执行** —— 按任务书要求需用户授权 |

> 任务书要求"不能只提供本地地址并称为公开部署完成"。因此本报告明确标注：
> **公网部署尚未完成**，只完成了可部署产物与本地生产模式验证。
> 提供托管账号（Render/Fly/Vercel 任一）与仓库 Push 权限后即可执行。

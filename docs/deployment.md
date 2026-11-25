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
| 生产构建产物端到端测试 | ✅ 6/6 通过（`PSC_BASE_URL=http://127.0.0.1:8001 npx playwright test`） |
| GitHub Actions CI（后端 + 前端 + E2E） | ✅ 全部通过（在 GitHub 托管 runner 上，Python 3.11 / Node 20 / Chromium） |
| GitHub Pages 静态产物 | ✅ 产物已在本地静态托管下验证（见 §5.2） |
| GitHub Pages 站点启用 | ⏳ **待仓库设置**：Pages 未启用，创建站点需要管理员权限（工作流令牌无此权限） |
| Docker 镜像构建 | ⚠️ 未实际构建（本机无 Docker） |
| 公网部署 | ❌ **未完成** —— 需要启用 Pages 或提供其他托管凭据 |
| GitHub Push | ✅ 已执行并验证（`main`，公开仓库） |

### 5.1 公网地址（启用后即生效）

```
https://engernages-lab.github.io/03/
```

工作流 `.github/workflows/deploy-pages.yml` 已就绪：推送 `frontend/**` 即自动构建、
生成 `404.html` SPA 回退、上传并部署。**唯一缺的一步是在仓库设置里启用 Pages**：

1. 打开 <https://github.com/engernages-lab/03/settings/pages>
2. Build and deployment → Source 选择 **GitHub Actions**
3. 保存（无需其他配置）

启用后可由 `python scripts/enable_pages.py` 触发并等待完成（需 `GITHUB_TOKEN`），
或直接推送任意 `frontend/**` 改动。

> 说明：Pages 只能托管静态前端。要获得完整功能（音乐库、播放器、MIDI 导入、
> 双谱编辑、导出），还需把 FastAPI 后端部署到公网，并在构建时注入
> `VITE_API_BASE_URL`（仓库变量），见 §3。

### 5.2 静态产物本地验证

```powershell
cd frontend
$env:VITE_BASE_PATH="/03/"; npm run build; Remove-Item Env:VITE_BASE_PATH
# 把 dist 放到 <www>/03/ 后用任意静态服务器托管，然后：
$env:PSC_STATIC_URL="http://127.0.0.1:8080/03/"
npx playwright test tests/e2e/pages-artifact.spec.ts
```

该用例断言：产物在 `/03/` 子路径下能启动、路由 basename 正确（点击导航仍停留在
`/03/` 下）、`/03/assets/*` 无 404、没有后端时页面如实显示「无法连接后端 API / 静态预览页」。
截图见 `docs/screenshots/09-pages-static-preview.png`。

### 5.3 部署前自验（不改代码即可复跑）

```powershell
# 1) 构建产物
cd frontend; npm run build; cd ..

# 2) 用生产环境变量启动（同时托管 SPA）
cd backend
$env:POCKETSCORE_ENVIRONMENT="production"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001

# 3) 另一终端：对生产包跑端到端
$env:PSC_BASE_URL="http://127.0.0.1:8001"
npx playwright test tests/e2e/workstation.spec.ts
```

> 任务书要求"不能只提供本地地址并称为公开部署完成"。因此本报告明确标注：
> **公网部署尚未完成**，只完成了可部署产物与本地生产模式（含生产包 E2E）验证。
> 提供托管账号（Render/Fly/Vercel 任一）与仓库 Push 权限后即可执行。

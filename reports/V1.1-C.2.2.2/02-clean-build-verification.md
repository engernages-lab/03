# V1.1-C.2.2.2 · 02 干净上下文构建验证（Phase 2）

> **结论：BLOCKED**
> 阻断点：本机**没有 Docker 守护进程**（也无 Podman / nerdctl / WSL 发行版），
> 因此无法执行真实 `docker build`、无法检查镜像内容、无法启动容器。
> 按本阶段规则「只有真实 Docker 构建和镜像检查均成功才允许 PASS」，只能报 BLOCKED。
>
> **已完成**：干净 Git worktree、构建前 `dist` 缺失确认、`.dockerignore` 规则确认、
> 19 项 Dockerfile/产物静态断言、以及**在干净上下文里真实复现镜像内前端构建阶段**。
> **未完成**：`docker build`、镜像文件检查、容器启动、容器内 `/health` `/ready`、容器内 PORT 注入。

---

## 1. 执行环境

| 项 | 值 |
| --- | --- |
| 日期 | 2026-11-27 |
| 平台 | Windows（工作目录 `D:\AI扒谱工具`） |
| Node / npm | v24.22.0 / 11.19.1 |
| Docker | ❌ `docker: not found`（`docker --version` 无输出，命令不存在） |
| Podman | ❌ not found |
| nerdctl | ❌ not found |
| WSL | ❌ 未安装发行版（`wsl --status` 提示执行 `wsl --install`） |
| 证据文件 | `.run/phase2-evidence.json`、`.run/phase2-static.json` |

原始探测结果：

```json
{
  "docker_version": {"cmd": "docker --version", "rc": null, "out": "", "err": "not found"},
  "podman_version": {"rc": null, "err": "not found"}
}
```

**没有任何本地容器运行时**，这是本阶段唯一的阻断原因。

## 2. Git 与干净上下文

| 项 | 值 |
| --- | --- |
| 分支 | `pocketscore-v1.1-b` |
| Commit SHA | `b326e303247ff4e68eb261812ce64230e9d6e23d` |
| 上下文方式 | `git worktree add --detach <tmp> HEAD`（独立工作树，**未删除主工作区任何文件**） |
| 上下文路径 | `D:\pocketscore-clean-204748`（验证后已移除，主工作区未受影响） |
| worktree 内 `git status --short` | 空（无未跟踪文件、无本地 `node_modules`、无 `dist`） |
| 验证后清理 | `git worktree remove --force`，`git worktree list` 仅剩主工作区 |

```text
$ git worktree add --detach D:\pocketscore-clean-204748 HEAD
HEAD is now at b326e30 test(V1.1-C.2.2.2): Railway post-fix regression gate - PASS with cloud evidence

$ Test-Path D:\pocketscore-clean-204748\frontend\dist
False                     ← 构建开始前 dist 不存在

$ git -C <worktree> status --short
（空）
```

## 3. `.dockerignore` 规则

```text
# frontend/dist is ignored again: the image now builds the bundle in its own
# node stage, so a stale local dist must never leak into the build context.
frontend/dist
```

✅ 规则存在且精确匹配 `frontend/dist`（锚定行首，不会被 `frontend/dist-ssr` 之类误伤）。

## 4. Dockerfile 静态断言（19/19 通过）

脚本：`.run/phase2_static_checks.py`（在干净 worktree 根执行），
结果存 `.run/phase2-static.json`。

| # | 断言 | 实际值 | 结果 |
| --- | --- | --- | --- |
| 1 | 构建前 `frontend/dist` 不存在 | `False`（worktree 创建时） | ✅ |
| 2 | `.dockerignore` 排除 `frontend/dist` | 规则存在 | ✅ |
| 3 | 多阶段：node 前端阶段 | `FROM node:20-slim AS frontend` | ✅ |
| 4 | 镜像内 `npm ci` | `RUN npm ci --no-audit --no-fund` | ✅ |
| 5 | 镜像内 `npm run build` | `RUN npm run build && test -f dist/index.html` | ✅ |
| 6 | 从前端阶段取产物 | `COPY --from=frontend /web/dist ./frontend/dist` | ✅ |
| 7 | 不 COPY 宿主机 dist | 无 `COPY frontend/dist` 指令 | ✅ |
| 8 | 基路径默认 `/` | `ARG VITE_BASE_PATH=/` | ✅ |
| 9 | **无 `VOLUME` 指令** | 全文无 | ✅ |
| 10 | 使用 Railway `$PORT` | `--port "${PORT:-8000}"` | ✅ |
| 11 | HEALTHCHECK 指向 `/health` | `HEALTHCHECK ... /health` | ✅ |
| 12 | 前端产物路径显式 | `ENV POCKETSCORE_FRONTEND_DIST=/app/frontend/dist` | ✅ |
| 13 | 创建 `/data/storage` | `RUN mkdir -p /data/storage && chmod 0777 /data` | ✅ |
| 14 | 产出 `index.html` | 682 B | ✅ |
| 15 | 产出 JS 资源 | `index-BGu74WxJ.js` | ✅ |
| 16 | 产出 CSS 资源 | `index-BcW44oh8.css` | ✅ |
| 17 | HTML 引用 `/assets/` | 根相对路径 | ✅ |
| 18 | HTML 无 `/03/` 前缀 | 无 | ✅ |
| 19 | 被引用的 JS 真实存在 | `index.html → dist/assets` | ✅ |

## 5. 在干净上下文真实复现「镜像内前端阶段」

这不等于 `docker build`，但它**真实执行了 Dockerfile 第 1 阶段的两条命令**，
且运行在无 `node_modules`、无 `dist` 的干净 worktree 上：

```bash
cd <worktree>/frontend
npm ci --no-audit --no-fund          # 39.4 s
VITE_BASE_PATH=/ npm run build       # vite 5.4.21，3.34 s
```

产物：

```text
dist/index.html                   0.64 kB │ gzip:  0.45 kB
dist/assets/index-BcW44oh8.css   37.58 kB │ gzip:  6.82 kB
dist/assets/index-BGu74WxJ.js   390.85 kB │ gzip: 119.80 kB
✓ built in 3.34s
```

磁盘实测：

| 文件 | 大小 | 说明 |
| --- | --- | --- |
| `frontend/dist/index.html` | 682 B | 只有这一份 HTML |
| `frontend/dist/assets/index-BGu74WxJ.js` | **399 033 B** | 与云端实际下发**逐字节同尺寸** |
| `frontend/dist/assets/index-BcW44oh8.css` | **37 581 B** | 同上 |
| `*.map` | 0 个 | 无 sourcemap 泄漏 |

`index.html` 内的引用：

```html
<script type="module" crossorigin src="/assets/index-BGu74WxJ.js"></script>
<link rel="stylesheet" crossorigin href="/assets/index-BcW44oh8.css">
```

→ 根路径 `/assets/…`，**没有** `/03/`（F2 的行为证据）。

**可复现性交叉验证**：云端镜像当前下发的资源名与字节数
（`index-BGu74WxJ.js` 399 033 B、`index-BcW44oh8.css` 37 581 B，见 C.2.2.2 的
`artifacts/frontend-assets-check.json`）与本机干净上下文构建产物**完全一致**。
这说明该阶段在同一输入下产出确定、且与已部署镜像的产物相同
（注意：这是"产物一致性"推断，不是"我构建了镜像"）。

## 6. 无法执行的部分（阻断清单）

| 项目 | 状态 | 原因 |
| --- | --- | --- |
| `docker build -f backend/Dockerfile .` | ⛔ 未执行 | 无 Docker 守护进程 |
| 镜像 ID / 大小 / 层信息 | ⛔ 未获取 | 同上 |
| 镜像内 `/app/frontend/dist/index.html` 实际存在 | ⛔ 未验证 | 同上 |
| 容器启动 | ⛔ 未执行 | 同上 |
| 容器内 `/health`、`/ready` | ⛔ 未执行 | 同上 |
| 容器内 `PORT` 注入（如 `-e PORT=8123`） | ⛔ 未执行 | 同上 |
| 容器内 curl 静态资源 | ⛔ 未执行 | 同上 |

这些项目**一律未标记为通过**。

## 7. 现有可用于交叉印证的证据（非本阶段构建）

| 证据 | 内容 | 与本阶段的关系 |
| --- | --- | --- |
| GitHub Actions run `45972926226`（提交 `4ec2b7c`） | 在 ubuntu runner 的干净上下文中构建同一 Dockerfile：`npm ci` → `npm run build` → `COPY --from` 成功，随后断言镜像内含 `index.html`、`/assets/*`、无 TensorFlow | **他人/CI 环境的历史构建**，不是本阶段本机构建 |
| `git diff 4ec2b7c b326e30 -- backend frontend Dockerfile railway.json .dockerignore` | **0 个文件**变更 | 说明 CI 绿的那次构建与当前 HEAD 的镜像内容相同 |
| Railway 部署 `3359dd35` / `492d9fa7` | 用同一 Dockerfile 在云端构建并成功运行，云端下发 399 033 B JS | 同上，属历史证据 |

> 使用这些证据是为了说明"镜像历史上确实能从干净上下文构建成功"，
> **不能**、也没有被当作本阶段 `docker build` 的替代。

## 8. 一条更快的达标路径（需用户授权）

仓库已有 `.github/workflows/docker-verify.yml`，它执行的动作与本阶段要求一一对应：

1. 干净 checkout（无 `frontend/dist`）
2. `npm ci` + `npm run build`（Pages 产物校验）
3. `docker/build-push-action` 构建镜像（`--load`）
4. `verify-image.sh`：断言 `/app/frontend/dist/index.html`、`/assets/*`、ffmpeg、无 TF
5. 容器内 `PORT` 注入（8123 与 8000）、`/health`、`/ready`、真实扒谱、持久化、优雅退出

触发方式（二者都需要一次明确授权）：

```bash
# A. 授权 push 当前分支（paths 含 scripts/deploy/**，会触发 workflow）
git push origin pocketscore-v1.1-b
```

```text
B. 在 GitHub 页面 Actions → "Docker verify (V1.1-C.2.2.1)" → Run workflow
```

拿到 CI 结果后，本报告即可把 §6 的六项填成实测值并转 PASS。

## 9. 结论

| 判定 | 说明 |
| --- | --- |
| **BLOCKED** | 无 Docker 守护进程 → 无法执行真实镜像构建与镜像检查；按阶段规则不得判 PASS |

已完成且可复现的部分：干净上下文、`dist` 缺失确认、`.dockerignore` 规则、
19 项 Dockerfile/产物断言、镜像内前端阶段的真实复现（产物与线上镜像字节一致）。

未完成：`docker build`、镜像检查、容器运行、容器内健康检查与 PORT 验证。

---

## 附录 A：复现步骤（有 Docker 的机器上）

```bash
# 1. 干净上下文
git worktree add --detach /tmp/ps-clean b326e30
cd /tmp/ps-clean
test ! -d frontend/dist && echo "dist absent: ok"

# 2. 真实构建
docker build -f backend/Dockerfile -t pocketscore-ai:phase2 .

# 3. 镜像检查
docker run --rm --entrypoint sh pocketscore-ai:phase2 -c '
  ls -l /app/frontend/dist/index.html /app/frontend/dist/assets/ &&
  grep -o "/assets/[^\"]*" /app/frontend/dist/index.html &&
  grep -c "03/assets" /app/frontend/dist/index.html || true &&
  python -c "import importlib.util as u; print(\"tensorflow:\", u.find_spec(\"tensorflow\"))"'

# 4. 容器运行 + PORT 注入
docker run -d --name ps-phase2 -e PORT=8123 -p 127.0.0.1:8123:8123 \
  -e POCKETSCORE_ENVIRONMENT=staging \
  -e POCKETSCORE_SESSION_SECRET="$(openssl rand -hex 32)" \
  -e POCKETSCORE_TOKEN_ENCRYPTION_KEY="$(python -c 'from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())')" \
  -e POCKETSCORE_ACCESS_GATE_TOKEN="$(openssl rand -hex 24)" \
  -e POCKETSCORE_CORS_ORIGINS=http://127.0.0.1:8123 \
  -e POCKETSCORE_ALLOW_PRIVATE_NETWORK_SOURCES=false \
  -e POCKETSCORE_DATABASE_URL=sqlite:////data/pocketscore.db \
  -e POCKETSCORE_STORAGE_DIR=/data/storage \
  -v ps-phase2-data:/data pocketscore-ai:phase2

curl -fsS http://127.0.0.1:8123/health && curl -sS http://127.0.0.1:8123/ready | head -c 400
docker exec ps-phase2 sh -c 'python -c "import socket,sys; s=socket.socket(); sys.exit(0 if s.connect_ex((\"127.0.0.1\",8000))==0 else 1)"' \
  && echo "8000 listening (PORT ignored)" || echo "8000 closed: PORT honoured"

# 5. 清理
docker rm -f ps-phase2; docker volume rm ps-phase2-data; docker rmi pocketscore-ai:phase2
git worktree remove --force /tmp/ps-clean
```

## 附录 B：本阶段边界遵守情况

| 边界 | 状态 |
| --- | --- |
| 修改 Railway | ❌ 未触碰 |
| 部署 | ❌ 未执行 |
| Push | ❌ 未执行 |
| 修改 main | ❌ 未执行 |
| 删除现有文件 | ❌ 未删除（仅创建并清理了自己新建的临时 worktree） |
| 输出密钥 | ❌ 无（本报告不含任何密钥） |
| 创建/删除云端资源 | ❌ 未执行 |

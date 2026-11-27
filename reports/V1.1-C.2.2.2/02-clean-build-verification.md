# V1.1-C.2.2.2 · 02 干净上下文构建验证（Phase 2）

- **日期**：2026-11-27
- **目标**：证明镜像构建不再依赖本地预构建的 `frontend/dist`（C.2.2.1 缺陷 F1）

---

## 1. 本机能力声明

```text
$ docker --version
（不存在：Docker / WSL 均未安装）
```

本机**无法**执行 `docker build`。按提示词 §5.2：不得把本地 Docker 构建标记为通过，
必须使用真实 Railway 构建日志作为证据。

## 2. Railway 构建即"干净上下文"构建

`railway up` 只上传 **Git 跟踪的文件 + 未被忽略的文件**，不会上传：

```text
frontend/dist   （.gitignore + .dockerignore 均排除）
node_modules/   （.gitignore）
.playwright/    （.gitignore）
backend/data/   （.gitignore）
```

因此 Railway 的构建上下文**必然不含** `frontend/dist`——这正是 F1 要验证的条件。
上传快照大小 `1.8 MB`（见构建日志首行 `fetched snapshot ... (1.8 MB bytes)`），
可反证未上传 node_modules（154 MB）或 dist。

## 3. 构建结果（真实日志）

证据文件：`artifacts/railway-build.log`

关键片段：

```text
[frontend 1/6] FROM docker.io/library/node:20-slim@sha256:2cf067cf...
[frontend 3/6] COPY frontend/package.json frontend/package-lock.json ./
[frontend 4/6] RUN npm ci --no-audit --no-fund
[frontend 5/6] COPY frontend/ ./
[frontend 6/6] RUN npm run build && test -f dist/index.html
[stage-1 10/11] COPY --from=frontend /web/dist ./frontend/dist
[stage-1 11/11] RUN mkdir -p /data/storage && chmod 0777 /data
====================
Starting Healthcheck
Path: /health
Deploy complete
```

| 检查项 | 结果 |
| --- | --- |
| 前端依赖在镜像内安装 | ✅ `npm ci` 步骤执行（`added 252 packages in 4s`） |
| 前端在镜像内构建 | ✅ `vite v5.4.21 building for production` → `built in 2.92s` |
| 产物经 `COPY --from` 进入运行时镜像 | ✅ `stage-1 10/11` |
| 构建不依赖本地 dist | ✅ 上下文 1.8 MB，dist 未被上传 |
| `VOLUME` 指令 | ✅ 不存在（未触发 Railway 校验错误） |
| 部署结果 | ✅ `Deploy complete` |

## 4. 产物是否真的可用（不在构建日志里断言）

构建日志只能证明"构建成功"。产物是否真的能被浏览器使用，用**真实 HTTP** 验证：

证据文件：`artifacts/frontend-assets-check.json`

```json
{
  "js":  {"path":"/assets/index-BGu74WxJ.js","anonymous":401,"authenticated":200,
          "content_type":"application/javascript","bytes":399033},
  "css": {"path":"/assets/index-BcW44oh8.css","anonymous":401,"authenticated":200,
          "content_type":"text/css; charset=utf-8","bytes":37581}
}
```

| 断言 | 结果 |
| --- | --- |
| `index.html` 存在且被服务 | ✅ `GET /` → 200 text/html（665 B） |
| JS 资源存在（399 KB） | ✅ 200，`application/javascript` |
| CSS 资源存在（37.6 KB） | ✅ 200，`text/css` |
| 资源路径无 `/03/` 前缀 | ✅ 首页 HTML 中无 `/03/assets` |

`/app/frontend/dist/index.html` 这类**容器内路径**无法在 Railway 上直接 `ls`，
但 HTTP 返回的正是该文件（etag `9b4f8e3c...`、`last-modified 08:37:14`，
与镜像构建时间一致），构成等效证据。

## 5. 结论

| 项 | 结论 |
| --- | --- |
| F1（镜像内构建前端） | ✅ 通过（真实 Railway 构建 + HTTP 产物验证） |
| 本机 Docker 构建 | ⛔ 未执行（无 Docker），已在报告中标明，不用 CI 结果冒充 |

> 诚实声明：本报告没有任何"本地 docker build 成功"的断言。
> 构建证据全部来自 Railway 真实构建日志与本机对该构建产物的真实 HTTP 请求。

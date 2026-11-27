# V1.1-C.2.2.1 · 05 部署过程中修复的缺陷

- **日期**：2026-11-27
- **背景**：C.2.1/C.2.2 的验证都在"CI 里构建好的镜像"上完成，而真实云端部署
  （`railway up` 从干净上下文构建）暴露了 5 个在 CI 里看不到的真实缺陷。
- **原则**：只修阻止 Staging 验收的问题，不做大重构。

---

## 汇总

| # | 缺陷 | 严重度 | 谁暴露的 | 提交 |
| --- | --- | --- | --- | --- |
| 1 | Dockerfile 依赖本地预构建的 `frontend/dist`（被 gitignore），干净上下文构建必失败 | **P0 阻断部署** | Railway 首次构建 / 逻辑分析 | `08e55b7` |
| 2 | 镜像内前端用 Pages 的 `/03/` 基路径构建，与后端 `/assets` 不匹配 | P1 | 代码对照 | `08e55b7` |
| 3 | Dockerfile 含 `VOLUME`，Railway 校验直接拒绝 | **P0 阻断部署** | Railway 第 2 次构建 | `f31655a` |
| 4 | 镜像携带 SPA 但**从未托管**：`PROJECT_ROOT` 在容器里解析成 `/` | P1 | 云端 `GET /` 返回 JSON | `7e08dfa` |
| 5 | `/ready` 不检查数据库，且 `access_gate` 状态根本没写进文件（C.2.2 报告描述过但未落地） | **P1 虚假就绪** | 云端 `/ready` 缺字段 | `4ec2b7c` |

---

## 1. 前端产物不在构建上下文里（P0）

**现象**：CI 之所以通过，是因为它在 runner 上先 `npm ci && npm run build`，再用
`docker build` 把 `frontend/dist` COPY 进镜像。任何干净克隆或 `railway up` 都没有这个目录。

**根因**：`frontend/dist` 在 `.gitignore` 里；Dockerfile 却 `COPY frontend/dist`。

**修复**：新增 `node:20-slim` 构建阶段，在镜像内 `npm ci` + `vite build`，
运行时阶段用 `COPY --from=frontend /web/dist` 取产物。构建上下文不再需要 dist，
`.dockerignore` 重新排除它（避免陈旧产物混入）。

**验证**：CI 三次全绿；云端构建日志显示 `[frontend 6/6] RUN npm run build` 成功。

## 2. 前端基路径与后端不匹配（P1）

**现象**：CI 用 `VITE_BASE_PATH=/03/`（GitHub Pages 的子路径）。但后端把 SPA 挂在源根
（`/assets` + catch-all），镜像里的 bundle 会去请求 `/03/assets/*` → 404。

**修复**：Dockerfile `ARG VITE_BASE_PATH=/`（镜像默认根路径），CI 的 Pages 构建仍用 `/03/`。

## 3. Railway 拒绝 `VOLUME` 指令（P0）

**现象**：

```text
dockerfile invalid: docker VOLUME at Line 69 is not supported, use Railway Volumes
```

**根因**：Railway 自己管理卷，禁止镜像声明 `VOLUME`。

**修复**：删除该行；挂载点仍用 `RUN mkdir -p /data/storage && chmod 0777 /data` 创建。
本地与 CI 一直用显式 `-v <name>:/data`，行为不变（C.2.1 的持久化测试仍然通过）。

## 4. SPA 从未被托管（P1）

**现象**：云端 `GET /` 返回 API 描述 JSON，而不是 SPA；镜像里却带着 390 KB 的 bundle。

**根因**：`PROJECT_ROOT` 由 `BACKEND_DIR.parent` 推导。容器内 `BACKEND_DIR=/app`，
于是 `PROJECT_ROOT=/`，`/frontend/dist` 不存在 → 挂载分支被静默跳过。

**修复**：
- 新增 `Settings.frontend_dist_path`：优先 `POCKETSCORE_FRONTEND_DIST`，
  否则 `<project>/frontend/dist`，再否则 `<backend>/frontend/dist`（容器布局）。
  Dockerfile 显式设置 `/app/frontend/dist`。
- `/` 的 API 描述只在**没有**挂载 SPA 时注册：测试与纯 API 部署保持 JSON 根，
  单服务部署返回 `index.html`，catch-all 处理客户端路由。
- 6 个测试覆盖显式/自动/缺失解析与路由。

**验证**：云端 `GET /` → `200 text/html`；`/assets/index-BGu74WxJ.js` → 200（带令牌）/ 401（匿名）。

## 5. 就绪检查存在两处虚假（P1）

**现象**：云端 `/ready` 返回 `ready: true`，但 `checks` 里**没有 `database`**，也**没有 `access_gate`**。

**根因**：
- 容器探针 `/ready`（注册在 SPA catch-all 之前）调用 `readiness_payload()` 时不传 session，
  数据库检查被 `if db is not None` 跳过 → 数据库坏了也会报 ready。
- C.2.2 报告中描述的 `checks["access_gate"]` 实际从未写入文件（那次编辑未生效，报告与代码不一致）。

**修复**：
- `/ready` 用 `session_scope()` 打开会话，真正执行 `SELECT 1`；异常时返回 503 + 错误。
- 补上 `access_gate` 描述（只报 `mode/enabled/token_configured/basic_configured`，不含凭据）。
- 新增 2 个契约测试：`/ready` 必须含 `access_gate` 且含 `database{ok:true}`。

**验证**（云端，修复后）：

```json
"checks": ["database","storage","ffmpeg","librosa","midi","model","inference","access_gate"]
"database": {"ok": true}
"access_gate": {"mode":"token","enabled":true,"token_configured":true}
```

---

## 教训

1. **CI 绿 ≠ 能部署**。CI 预构建了产物、用了本地 dist，掩盖了两个 P0。
2. **"镜像里有" ≠ "服务真的用上了"**：SPA 打包进去了但没挂载，只有真实请求能发现。
3. **报告必须与代码同步**：C.2.2 声称 `/ready` 报门禁状态，实际没有；本轮以云端响应为准修正。
4. 平台校验（Railway 的 Dockerfile 检查）会比本地 `docker build` 更严格——`VOLUME` 就是例子。

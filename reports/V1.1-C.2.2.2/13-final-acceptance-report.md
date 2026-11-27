# PocketScore AI V1.1-C.2.2.2
# Railway Post-Fix Regression & Production Readiness Gate
# Final Acceptance Report

---

## 1. 项目基本信息

| 项 | 值 |
| --- | --- |
| 项目 | PocketScore AI |
| 阶段 | V1.1-C.2.2.2 · Railway Post-Fix Regression & Production Readiness Gate |
| 验收日期 | 2026-11-27 |
| 分支 | `pocketscore-v1.1-b` |
| 最终 HEAD | `b1d3ee1`（部署后新增报告/测试提交见 §14） |
| 工作区 | 提交后干净 |
| Railway Project | `pocketscore-ai`（`286a8f6c-…`） |
| Railway Environment | **`staging`**（`72f62640-…`）；`production` 无服务 |
| Railway Service | `pocketscore-api`（`28d3b430-…`） |
| Deployment（Phase 3） | `3359dd35-7bd5-4bbe-9849-19181db3318b`（SUCCESS，10:46:17Z） |
| Deployment（Phase 12 重新部署） | `492d9fa7-50b8-4444-9ec5-90324b58069e`（SUCCESS，11:00:25Z） |
| Deployment（限额取证） | `90205505-5ad8-4dc0-8c71-0e46b0195cd0`（SUCCESS，12:09:15Z） |
| Deployment Commit | 工作区 `b1d3ee1`（`railway up` 上传工作树） |
| Staging Domain | `https://pocketscore-api-staging.up.railway.app` |
| Volume | `pocketscore-api-volume` → `/data`（≈38.7 MB / 500 MB） |

## 2. 最终结论

```text
PASS
```

依据：五项部署缺陷全部由**真实云端行为**回归通过；WAV 与 MP3 两条音频通道均完成
"上传 → 真实解码 → Basic Pitch 推理 → 音符 → MusicDocument → 保存 → 重启 → 恢复"的完整闭环，
且重启前后 12 个字段逐项一致、音频 SHA256 不变。

未验证项（§13）不属本阶段核心 PASS 条件，且已逐条标注为 `NOT TESTED`。

## 3. 五项部署缺陷回归结果

| 编号 | 修复 | 检查方法（真实证据） | 真实结果 | 证据文件 | 通过 |
| --- | --- | --- | --- | --- | --- |
| F1 | 镜像内构建前端 dist | Railway 干净上下文构建（上传快照 1.8 MB，无本地 dist）+ 云端 HTTP 取产物 | `[frontend 4/6] npm ci` → `[frontend 6/6] npm run build` → `COPY --from=frontend` 成功；云端 JS 399 033 B / CSS 37 581 B 均 200 | `artifacts/railway-build.log`、`artifacts/frontend-assets-check.json` | ✅ |
| F2 | 基路径 `/` | 抓取云端首页 HTML，检查资源路径 | 首页引用 `/assets/index-*.js`，**无 `/03/assets`**；资源直接 200 | `artifacts/homepage.html`、`artifacts/frontend-assets-check.json` | ✅ |
| F3 | 删除 Dockerfile `VOLUME` | Railway 构建校验 | 构建未被拒绝（此前同一指令直接报 `docker VOLUME ... not supported`）；部署 SUCCESS | `artifacts/railway-build.log` | ✅ |
| F4 | SPA 正式托管 | `GET /` + 4 条客户端路由 + 真实浏览器 | `GET /` 200 `text/html`（665 B）；`/dashboard` `/scores` `/transcription` `/settings` 均 200 HTML；浏览器渲染出标题「PocketScore AI · 音乐工作站」，12 个资源全 200，console/network 无错误 | `artifacts/homepage-response-headers.txt`、`artifacts/spa-routes.txt`、`artifacts/browser-network-summary.json` | ✅ |
| F5 | `/ready` 完整检查 | 云端 `/ready` 完整响应 | `checks` 含 8 项，`database {ok:true}`、`access_gate {mode:token, enabled:true, token_configured:true}` | `artifacts/ready-response.json` | ✅ |

## 4. Railway 部署证据

```text
[frontend 6/6] RUN npm run build && test -f dist/index.html
[stage-1 10/11] COPY --from=frontend /web/dist ./frontend/dist
[stage-1 11/11] RUN mkdir -p /data/storage && chmod 0777 /data
====================
Starting Healthcheck
Path: /health
Retry window: 3m0s
Attempt #1 failed with service unavailable. Continuing to retry for 2m49s
Deploy complete
```

- 构建日志：`artifacts/railway-build.log`（首次）、`artifacts/railway-redeploy.log`（重新部署）
- 部署 ID / 状态 / 时间见 §1
- 未使用任何本地 Docker 结果替代（本机无 Docker，已在 02 号报告声明）

## 5. HTTP 回归结果

| 项目 | 结果 |
| --- | --- |
| 首页 `GET /` | 匿名 401；带令牌 200 `text/html`（665 B） |
| 静态资源 | JS 399 033 B / CSS 37 581 B，带令牌 200，匿名 401，Content-Type 正确 |
| SPA 路由 | `/dashboard` `/scores` `/transcription` `/settings` 全部 200 HTML；深链接刷新正常 |
| API | `GET /api/v1/documents` 带令牌 200 |
| Access Gate | 匿名 401（API、上传、`/docs`、`/openapi.json`、静态资源、SPA 根）；错令牌 401；正令牌 200；22 次连续错误 → 21、22 次 **429** |
| CORS | 允许来源 `https://engernages-lab.github.io` 预检 200 + 精确 allow-origin；外来源 400 |
| `/health` | 200（0.87–0.99 s） |
| `/ready` | 200（0.90–1.02 s），8 个检查项全绿 |

汇总：`artifacts/access-gate-check.json`（passed=24, failed=0）。

## 6. WAV 扒谱结果

| 项 | 值 |
| --- | --- |
| 文件 | `tests/fixtures/melody.wav`，79 424 B，SHA256 `f4824273…ec51f6` |
| 上传 | 201，3.256 s，asset `ea92ebce992c`（服务端 checksum 与本地一致） |
| Job ID | `job_5d4a57584e51`，状态 `completed`，14.614 s |
| 引擎 | Basic Pitch 0.4.0 + `nmp.onnx`（onnxruntime），无 TensorFlow |
| 推理 | `inference_seconds 5.267`、`model_load 2.116`、原始 6 音符 → 最终 4 |
| 音符 | **4** 个：音高 `[60,64,67,72]`，起音 `[0,0.75,1.5,2.5]`，时值 `[0.75×4]` |
| 置信度 | 平均 0.6569，低置信 0 |

## 7. MP3 扒谱结果

| 项 | 值 |
| --- | --- |
| 文件 | `melody.mp3`（由同一 WAV 经 libmp3lame 转码，非改扩展名），11 385 B，SHA256 `62250129…8016c` |
| 上传 | 201，1.026 s，asset `5b520fb5abda`（checksum 一致） |
| Job ID | `job_341cfaa8c8b4`，状态 `completed`，2.824 s |
| 解码 | 后端解码出 1.8 s / 22 050 Hz（真实解码，非按扩展名猜测） |
| 推理 | `inference_seconds 0.994`，原始 5 → 最终 4 |
| 音符 | **4** 个：音高 `[60,64,67,72]`，起音 `[0,0.75,1.5,2.5]`，时值 `[0.75×4]` |
| 一致性 | 与 WAV 结果完全相同（同一音频的两种编码） |

## 8. MusicDocument 与项目保存

| 项 | 值 |
| --- | --- |
| 项目标记 | `C2-2-2-STAGING-REGRESSION-20261127T105532Z` |
| Document ID | `6a0c696a7289` |
| 音符 | 4（`[60,64,67,72]`，力度 `[97,96,101,97]`） |
| 重命名 | 200，重读仍为新标题（写入持久化） |
| 编辑 | `transpose +1` → 音高 `[61,65,68,73]`；`-1` → 恢复 `[60,64,67,72]` |
| 网格谱 | `notes=3, unmapped=1`（3+1=4，不丢音符） |
| 数字谱 | `notes=4, unmapped=1`（unmapped 为子集标记） |
| 双谱同源 | ✅ `grid.document_id == jianpu.document_id == 6a0c696a7289` |
| 列表 | 200，`total=8`，包含该文档 |

## 9. 重启前后持久化对比

| 字段 | 重启前 | 重启后 | 一致 |
| --- | --- | --- | --- |
| Project ID | `6a0c696a7289` | `6a0c696a7289` | ✅ |
| Project Name | `C2-2-2-STAGING-REGRESSION-20261127T105532Z` | 同 | ✅ |
| MusicDocument ID | `6a0c696a7289` | 同 | ✅ |
| Note Count | 4 | 4 | ✅ |
| Pitch Sequence | `[60,64,67,72]` | `[60,64,67,72]` | ✅ |
| Onset Sequence | `[0.0,0.75,1.5,2.5]` | `[0.0,0.75,1.5,2.5]` | ✅ |
| Duration Sequence | `[0.75,0.75,0.75,0.75]` | 同 | ✅ |
| Audio SHA256 | `622501298bd9…8016c` | `622501298bd9…8016c` | ✅ |
| Audio File Size | 11 385 | 11 385 | ✅ |

附加：`Velocity Sequence`、`Grid Stats`、`Jianpu Stats` 也一致（共 12 字段）。

- 重启命令：`railway restart --service pocketscore-api --yes`，**31.4 s** 恢复 `/ready` 200；
  新进程证据：`model.load_seconds=1.191` 重新加载、`inference.completed=0` 计数归零。
- **重新部署**（`railway up`，新容器）后再次对比：12 字段仍全部一致。
- 证据：`artifacts/before-restart.json`、`artifacts/after-restart.json`、
  `artifacts/persistence-diff.json`、`artifacts/after-redeploy.json`、
  `artifacts/persistence-diff-redeploy.json`

## 10. 浏览器回归

| 项 | 结果 |
| --- | --- |
| 工具 | Playwright + 系统 Chrome（本机内置浏览器不可用） |
| 首页 / 路由 / 刷新 | ✅ 标题「PocketScore AI · 音乐工作站」，4 条路由渲染，`/scores` 刷新正常 |
| 资源 | ✅ 12 次请求全部 200 |
| Console / Network | ✅ 0 错误、0 失败请求 |
| 匿名浏览器渲染断言 | ⛔ **NOT TESTED**（Chrome 对 401+Basic challenge 直接 `ERR_INVALID_AUTH_CREDENTIALS`，runner 内导航挂起） |
| 匿名 API 401 | ✅（Playwright request） |

## 11. 安全与稳定性

| 项 | 结果 |
| --- | --- |
| 密钥泄露 | ✅ 未发现（仓库 / bundle / 401 响应 / `/ready` / 日志） |
| 上传限制 | ✅ 415（非法类型）、413（超限，实测 `limit_mb:1`）、401（匿名）、201（限额内） |
| 路径穿越文件名 | ✅ 惰性（内容寻址，未新建文件） |
| 服务崩溃 | ✅ 无 |
| CPU 平均 / 峰值 | 0.012 / 0.407 vCPU（上限 2） |
| 内存平均 / 峰值 | 482.6 MB / **650.6 MB**（上限 1024 MB） |
| Volume | 38.7 MB / 500 MB |
| 异常重启 | 0 |

## 12. 本地回归测试

| 项 | 结果 |
| --- | --- |
| 后端 pytest | **354 passed** |
| Ruff | clean |
| 前端 vitest | **103 passed**（12 文件） |
| TypeScript | exit 0 |
| 生产构建 | 11.25 s，0 sourcemap |
| 本地 E2E | **15 passed / 1 skipped** |

## 13. 未完成事项

| # | 项目 | 状态 | 说明 |
| --- | --- | --- | --- |
| 1 | 云端数据库故障注入（`/ready` → 503） | **NOT TESTED** | 按提示词 §8.3 未对真实 Staging 做破坏性注入；代码路径与本地测试覆盖 |
| 2 | 匿名浏览器渲染断言 | **NOT TESTED** | Chrome 行为导致导航挂起；HTTP 层 401 已由 curl/Playwright request/回归脚本三次证明 |
| 3 | 长音频（120 s）推理与内存压力 | **NOT TESTED** | 未在云端跑长素材 |
| 4 | 并发 2 个转录任务（503 队列行为） | **NOT TESTED** | 仅单测覆盖 |
| 5 | 多副本 / 水平扩展 | **NOT TESTED** | 当前单副本 |
| 6 | 小时级稳定性与内存增长曲线 | **NOT TESTED** | 仅 2 小时平台指标窗口 + 5 分钟连续采样 |
| 7 | 网格谱 `unmapped=1` | 记录 | pitch 72 超出默认键盘布局映射，非数据丢失 |

## 14. Git 与部署边界

| 项 | 说明 |
| --- | --- |
| 是否修改产品代码 | ❌ 否（仅新增测试脚本、e2e spec 与报告） |
| 新增文件 | `scripts/deploy/verify-staging-regression.sh`、`verify-staging-audio.py`、`verify-staging-document.py`、`verify-staging-persistence.py`、`compare-staging-persistence.py`、`tests/e2e/staging-regression.spec.ts`、`tests/e2e/staging-anonymous.spec.ts`、`reports/V1.1-C.2.2.2/*` |
| 提交哈希 | 见本报告提交（`git log -1`） |
| 是否 Push | ✅ 推送到 `origin/pocketscore-v1.1-b`（当次授权范围内） |
| 是否 Merge main | ❌ 否（`origin/main` 仍 `9e7cd41`） |
| 是否部署 | ✅ 部署到 **staging**（4 次部署 + 1 次重启） |
| 是否触碰 production | ❌ 否 |
| 是否修改 Volume / 删数据 | ❌ 否 |
| 临时配置变更 | `POCKETSCORE_MAX_UPLOAD_MB` 1 → 50（取证用，**已恢复**并重新部署验证） |

## 15. 下一阶段建议

1. **不要**自动开始 C.2.3；本报告需用户审核。
2. 进入 C.3（PostgreSQL + 对象存储）前建议先做：
   - 长音频（120 s）与 2 并发任务的云端压测（当前内存峰值 650 MB / 1024 MB）
   - `/data` 备份与恢复演练
   - `railway.json` 迁移到 `.railway/railway.ts`（2026-12-01 弃用）
3. staging 仍为共享令牌，不得公开；用户认证仍是 C.5 的前置依赖。

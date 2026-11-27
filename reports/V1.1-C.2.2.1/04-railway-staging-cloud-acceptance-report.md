# V1.1-C.2.2.1 · Railway Staging 云端验收报告

> **结论：PASS**
> 真实 Railway Staging 已部署并通过云端验收：访问门禁、Basic Pitch 真实推理、
> 项目读写、Volume 持久化（重新部署 + 进程重启）、CORS、前端无密钥、
> 限流 429、稳定性观察均取得实测证据。
> 本次执行前该阶段为 BLOCKED（无凭据）；本轮登录后完成部署与验收。

---

## 1. 项目版本信息

| 项 | 值 |
| --- | --- |
| 项目 | PocketScore AI |
| 阶段 | V1.1-C.2.2.1 · Railway Staging Cloud Acceptance |
| 应用版本 | `1.0.0a1`（`/health` 返回 `stage: V1.0-A`） |
| 验收日期 | 2026-11-27（UTC 记录） |

## 2. Git

| 项 | 值 |
| --- | --- |
| 分支 | `pocketscore-v1.1-b` |
| 验收时 HEAD | `4ec2b7c` |
| 部署使用的提交 | `4ec2b7c`（前端内置构建 + SPA 托管 + readiness 修复） |
| 远程 | `origin/pocketscore-v1.1-b` 与本地一致 |
| `origin/main` | `9e7cd41`（未动，未合并） |
| 工作区 | 干净 |

本阶段新增提交（全部已推送）：

```
4ec2b7c fix(health): readiness must report the gate and actually check SQLite
7e08dfa fix(spa): actually serve the bundled frontend in the container
f31655a fix(docker): drop the VOLUME instruction so Railway accepts the Dockerfile
08e55b7 fix(docker): build the SPA inside the image so cloud builds are self-contained
```

## 3. Railway 资源

| 项 | 值 |
| --- | --- |
| Project | `pocketscore-ai`（`286a8f6c-86ff-45f0-97e2-28ba955799d4`） |
| Environment | **`staging`**（`72f62640-3e69-46c7-adb5-81c4fa50a4a1`） |
| 另一个环境 | `production`（默认创建，**未部署任何服务**） |
| Service | `pocketscore-api`（`28d3b430-6b62-4492-b49a-1f29ef2026c2`） |
| Volume | `pocketscore-api-volume`，挂载 `/data`，上限 500 MB，已用 ≈36 MB |
| Builder | Dockerfile（`backend/Dockerfile`，context = 仓库根） |

注：账号在本次执行前**没有任何项目**（`railway list` 为空），本项目/服务/卷/env 均为本次创建。

## 4. Deployment

| 项 | 值 |
| --- | --- |
| 当前 Deployment ID | `052a194e-96eb-4cea-a3a1-c4df43c026cc`（SUCCESS） |
| 首次成功部署 | `faeb4a6a-2c05-4d52-8759-0abb83ad6eea` |
| 失败部署 | `f5773c82-fabb-4565-a35d-d9c491264e0d`（Dockerfile 含 `VOLUME` 被拒） |
| 部署历史 | 3 次成功（首次、SPA 修复、readiness 修复）+ 1 次失败 |

## 5. 云端 URL

```
https://pocketscore-api-staging.up.railway.app
```

域名由 `railway domain` 生成（ID `cfb0dd91-4d8d-4fb7-931f-bf319c5a4852`），非编造。

## 6. 环境变量（仅名称）

已配置 15 项，全部带 `POCKETSCORE_` 前缀：

`ENVIRONMENT` · `DEBUG` · `LOG_JSON` · `SESSION_SECRET` · `TOKEN_ENCRYPTION_KEY` ·
`ACCESS_GATE_TOKEN` · `ACCESS_GATE_MODE` · `CORS_ORIGINS` ·
`ALLOW_PRIVATE_NETWORK_SOURCES` · `DATABASE_URL` · `STORAGE_DIR` ·
`MODEL_PRELOAD` · `MAX_UPLOAD_MB` · `MAX_CONCURRENT_INFERENCES` · `INFERENCE_TIMEOUT_SECONDS`

关键取值（非密钥）：`ENVIRONMENT=staging`、`DATABASE_URL=sqlite:////data/pocketscore.db`（四斜杠）、
`STORAGE_DIR=/data/storage`、`ALLOW_PRIVATE_NETWORK_SOURCES=false`、
`CORS_ORIGINS=https://engernages-lab.github.io`。

镜像内另有 `POCKETSCORE_FRONTEND_DIST=/app/frontend/dist`（本轮新增）。

**密钥未出现在本报告、未提交仓库、未进入前端产物。** 本地仅存于 `.run/`（已 gitignore）。

## 7. Docker 部署结果

| 项 | 结果 |
| --- | --- |
| 构建 | ✅ 成功（前端 node stage + 运行时 stage） |
| 前端构建于镜像内 | ✅ `dist/assets/index-BGu74WxJ.js` 390.85 kB（gzip 119.8 kB） |
| Basic Pitch | ✅ 0.4.0，`--no-deps` 安装，**TensorFlow 未安装** |
| 依赖 | ✅ onnxruntime、librosa、soundsfile、imageio-ffmpeg 全部就绪 |
| 镜像推送 | ✅ `railway.push.duration 21.03s` |

## 8. Healthcheck

| 项 | 结果 |
| --- | --- |
| Railway healthcheck | ✅ `/health` 通过（Retry window 3m0s 内） |
| `/health` | ✅ 200 |
| `/ready` | ✅ 200，`ready: true` |
| `/ready` 内容 | `database{ok}` + `storage` + `ffmpeg` + `librosa` + `midi` + `model{status: ready}` + `inference{capacity:1}` + `access_gate{mode:token, enabled:true, token_configured:true}` |
| 模型加载 | load 1.104 s / warmup 1.03 s（重启后重测） |

## 9. Access Gate 云端测试

| 编号 | 测试 | 预期 | 实测 |
| --- | --- | --- | --- |
| AG-01 | `/health` 无凭据 | 200 | ✅ 200 |
| AG-02 | `/ready` 无凭据 | 200 | ✅ 200 |
| AG-03 | `/docs` 无凭据 | 401 | ✅ 401 |
| AG-04 | 受保护 API 无凭据 | 401 | ✅ 401（`/api/v1/documents`） |
| AG-05 | 错误 Token | 401 | ✅ 401 |
| AG-06 | 正确 Token | 200 | ✅ 200 |
| AG-07 | 连续错误请求 | 429 | ✅ 第 21、22 次返回 429（20 次失败后） |
| AG-08 | OPTIONS 预检 | 符合 CORS | ✅ 200 + `allow-origin: https://engernages-lab.github.io` |
| AG-09 | 门禁状态 | enabled=true | ✅ `mode=token, enabled=true, token_configured=true` |
| AG-10 | Token 不泄漏 | 通过 | ✅ 401 信封仅含 `code/message/details{mode,realm}`；`/ready` 只报布尔 |

附加：上传端点无凭据亦 401；`/openapi.json` 401。
限流测试为**受控 22 次顺序请求**（非压测），随后有效凭据仍 200（授权先于限流判定）。

## 10. 真实音频上传

| 项 | 实测 |
| --- | --- |
| 文件 | `tests/fixtures/melody.wav`（WAV PCM 单声道） |
| 大小 | 79 424 字节 |
| 时长 / 采样率 | 1.8 s / 22 050 Hz |
| 上传耗时 | 2.09 s |
| HTTP | 201 |

## 11. Basic Pitch 云端推理

| 项 | 实测 |
| --- | --- |
| 任务状态 | `completed` |
| 任务总耗时 | 19.34 s（含排队 4.39 s、推理 5.31 s、模型加载 1.14 s、后处理） |
| 音符数 | **4**（`raw_notes 6 → final_notes 4`） |
| 音高 | **60 / 64 / 67 / 72** |
| 是否真实推理 | ✅ 是（onnxruntime + nmp.onnx，无 TensorFlow，无 mock） |

## 12. MusicDocument

| 项 | 实测 |
| --- | --- |
| document_id | `05a5167af333` |
| 标题 | `melody` |
| events | 4 |
| 结构校验 | 音高 0–127、起点 ≥0、时值 >0，`problems: []` |
| 网格谱数据 | `grid.stats.notes = 3`（同一格内的同时音符合并计数） |
| 数字谱数据 | `jianpu.stats.notes = 4` |

## 13. 项目保存 / 读取

| 编号 | 项 | 结果 |
| --- | --- | --- |
| DB-01 | SQLite 写入 | ✅ `/ready` → `database{ok:true}` |
| DB-02 | 项目保存 | ✅ 文档落库 |
| DB-03 | 项目读取 | ✅ `GET /api/v1/documents/05a5167af333` → 200 |
| DB-04 | 音频文件写入 | ✅ 资产 `ea92ebce992c`，79 424 字节 |

## 14. Volume 持久化

| 检查 | 结果 |
| --- | --- |
| Volume 挂载 | ✅ `/data`（`railway deployment list` 显示 `volumeMounts: ["/data"]`） |
| 用量 | 平均 26.7 MB / 当前 36.0 MB / 上限 500 MB |
| 数据库位置 | `/data/pocketscore.db`（四斜杠绝对路径） |
| 音频位置 | `/data/storage/audio/...` |
| 重启后保留 | ✅ 见 §15 |

## 15. 服务重启 / 重新部署后的恢复

| 场景 | 文档 | 资产 | 事件数 | 摘要 |
| --- | --- | --- | --- | --- |
| 首次写入（部署 #1） | 200 | 200 | 4 | `41c1ad47…` |
| **重新部署后**（部署 #2） | 200 | 200 | 4 | `41c1ad47…` |
| **进程重启后** | 200 | 200 | 4 | `41c1ad47…` |
| **再次重新部署后**（部署 #3） | 200 | 200 | 4 | `41c1ad47…` |

摘要基于 `{事件数, 标题, checksum_sha256, 大小}` 计算，四次完全一致。
重启由 `railway restart` 触发（`inference.completed` 计数归零即为新进程证据）。

## 16. CORS

| 项 | 结果 |
| --- | --- |
| Pages 源预检 | ✅ 200，`allow-origin: https://engernages-lab.github.io`，`allow-headers: authorization`，`max-age: 600` |
| 外来源预检 | ✅ 400（拒绝） |
| 是否使用通配符 | ❌ 否（显式单一来源） |
| 是否因此关闭门禁 | ❌ 否（门禁保持启用） |

## 17. 前端 Token 泄漏检查

| 检查 | 结果 |
| --- | --- |
| 云端实际下发 bundle（399 KB）含 `ACCESS_GATE_TOKEN` | ✅ 无 |
| 含 `SESSION_SECRET` / `TOKEN_ENCRYPTION_KEY` | ✅ 无 |
| 含 `Bearer ` 构造 | ✅ 无 |
| 构建产物 sourcemap | ✅ 0 |
| 共享令牌是否放入 `VITE_*` | ✅ 无 |
| SPA 是否可匿名访问 | ❌ 401（资产同样受门禁保护） |

## 18. 安全检查

| 风险 | 结果 |
| --- | --- |
| 门禁关闭 | ✅ 不可能（缺凭据拒绝启动；显式 off 被拒） |
| 默认 Session Secret / Encryption Key | ✅ 拒绝启动 |
| 密钥泄漏 | ✅ 无（仓库、日志、报告、前端均无） |
| 私有网络音频源 | ✅ `false` |
| CORS 任意来源 | ✅ 显式单一来源 |
| SQLite 写入临时目录 | ✅ `sqlite:////data/...` 绝对路径（已验证落点） |
| 上传超限 | ✅ 415 实测（非法扩展名） |
| 未授权访问 | ✅ 401（含 `/docs`、`/openapi.json`、资产） |
| 错误凭据 | ✅ 401 |
| 启动失败可诊断 | ✅ 启动期逐条打印 `configuration error` |

## 19. Railway 资源指标（实测，1 小时窗口）

| 指标 | 值 |
| --- | --- |
| CPU 平均 | 0.031 vCPU（上限 2） |
| CPU 峰值 | 0.670 vCPU |
| 内存平均 | 285.6 MB |
| 内存峰值 | **589.5 MB**（上限 1024 MB，利用率 56.8%） |
| Volume | 36 MB / 500 MB |
| 出网流量峰值 | 0.87 MB |
| 重启次数 | 0（观察窗口内无异常重启） |

## 20. 自动化测试统计

| 层级 | 结果 | 执行位置 |
| --- | --- | --- |
| 后端 pytest | **354 passed** | 本地 |
| 前端 vitest | **103 passed** | 本地 |
| TypeScript | exit 0 | 本地 |
| 生产构建 | 9.92 s，0 sourcemap | 本地 |
| Ruff | All checks passed | 本地 |
| Docker CI | ✅ 3 次连续全绿（`f31655a`、`7e08dfa`、`4ec2b7c`） | GitHub Actions |
| **Playwright staging smoke** | **3 passed（56.1 s）** | **真实云端** |
| 云端门禁脚本 | ✅ rc=0（6 项断言） | 真实云端 |
| 云端扒谱脚本 | ✅ 4 音符 | 真实云端 |

## 21. 人工 / 脚本化验证记录

| 项 | 记录 |
| --- | --- |
| Railway 登录 | 浏览器 OAuth，账号 `Engernages` |
| 部署方式 | `railway up --ci --service pocketscore-api`（3 次成功） |
| 稳定性观察 | 2026-11-27 09:24:46Z → 09:29:59Z，10 次采样，间隔 30 s，**失败 0**，API 响应 0.87–2.22 s |
| 门禁限流 | 22 次顺序错误请求，第 21 次起 429 |
| 持久化对比 | 4 个时间点摘要一致 |

## 22. 遗留风险

| # | 风险 | 等级 | 说明 |
| --- | --- | --- | --- |
| 1 | 共享令牌 ≠ 用户认证 | P1 | 持令牌者可读写全部项目；无用户隔离（C.5） |
| 2 | SQLite 单实例 | P2 | 写并发有锁风险，不适合高并发生产 |
| 3 | 内存峰值 58% 上限 | P2 | 589 MB / 1024 MB；长音频或并发可能触顶 |
| 4 | 限流状态在内存 | P3 | 重启清零；多副本不共享 |
| 5 | 推理线程不可中断 | P2 | 重启会丢弃进行中的任务（状态保留原样） |
| 6 | 容器以 root 运行 | P2 | Volume 由 root 拥有，权限可用但非最佳实践 |
| 7 | 稳定性观察仅 5 分钟 | P3 | 不足以证明长期稳定 |
| 8 | Railway `railway.json` 弃用警告 | P3 | 2026-12-01 后需迁移到 `.railway/railway.ts` |
| 9 | 云端 bundle 与 Pages bundle 基路径不同 | P3 | 镜像用 `/`，Pages 用 `/03/`，各自正确 |

## 23. 未执行测试

1. 长音频（120 s）云端推理与内存压力测试
2. 并发 2 个转录任务的 503 行为（仅单测覆盖）
3. 多副本 / 水平扩展（当前单副本）
4. 长时间（小时级）稳定性与内存增长曲线
5. 真实用户浏览器端到端（前端无凭据，按设计不开放）
6. Railway 计费金额（未读取账单）

## 24. 最终验收结论

### PASS

23 项 PASS 条件逐项满足：Git 版本确认、环境变量核实、Staging 环境确认（另一个 `production` 环境为空）、
服务与卷确认、镜像真实部署、Healthcheck 通过、`/health`+`/ready` 正常（含数据库与门禁状态）、
门禁云端生效（401/200/429 全部实测）、真实 WAV 上传、Basic Pitch 真实推理（4 音符）、
MusicDocument 生成、项目读写、Volume 持久化、**重新部署与进程重启后数据完整**、
CORS 正确、前端无共享令牌、无敏感信息泄漏、自动化回归通过（354/103/3）、部署证据完整。

非致命缺口已登记于 §22/§23（共享令牌非认证、5 分钟观察窗口、无长音频压测）。

## 25. 下一阶段建议

1. **C.3 · PostgreSQL & Object Storage Migration**（用户此前指明 C.3 前需先完成本阶段，现已完成）
2. 迁移前建议先加：长音频内存压测、`/data` 备份策略
3. 不要在本阶段之后立刻公开 staging：仍是共享令牌，须等 C.5 用户认证
4. `railway.json` 在 2026-12-01 前迁移到 IaC，否则弃用

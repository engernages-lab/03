# PocketScore AI V1.1-C.2.1 · Docker CI Verification & Deployment Gate Report

---

## 1. 阶段信息

| 项 | 值 |
| --- | --- |
| 项目名称 | PocketScore AI |
| 阶段名称 | V1.1-C.2.1 · Docker CI Verification & Deployment Gate |
| 开发日期 | 2026-11-26 |
| 当前分支 | `pocketscore-v1.1-b` |
| 开始时 HEAD | `372ca7b` |
| 完成时 HEAD | `9dca1ad`（已推送到 `origin/pocketscore-v1.1-b`） |
| 未提交修改 | 本报告提交后为 0 |
| **最终验收结论** | **PASS**（依据见 §13） |

---

## 2. 修改文件清单

| # | 文件 | 类型 | 用途 | 原因 | 影响已有功能 |
| --- | --- | --- | --- | --- | --- |
| 1 | `.dockerignore` | 新增 | 排除 `.git`/缓存/node_modules/`.env`/密钥/DB；**保留 `frontend/dist`** | 上下文 1.7 GB → < 50 MB；且必须让 Dockerfile 能 COPY 到前端产物 | 否 |
| 2 | `backend/requirements-model.txt` | 新增 | 单独承载 `basic-pitch` | Linux+py3.11 平台标记会拉 TensorFlow | 否 |
| 3 | `backend/requirements.txt` | 修改 | 移除 basic-pitch；补齐 `mir-eval`/`resampy<0.4.3`/`scikit-learn`/`scipy`/`typing-extensions` | `--no-deps` 后仍需完整可导入 | 否 |
| 4 | `backend/Dockerfile` | 修改 | `--no-deps` 安装模型包 + 构建期断言（无 TF、可导入） | 阻止镜像膨胀与后端漂移 | 否 |
| 5 | `backend/app/services/audio/model_manager.py` | 修改 | 显式使用 `nmp.onnx`（缺失才回退并告警） | `basic_pitch` 默认按 TF>CoreML>TFLite>ONNX 选后端 | 否 |
| 6 | `.github/workflows/docker-verify.yml` | 重写 | 28 步容器门禁 | C.2 精简版缺少依赖检查/持久化/退出/清理 | 否（仅 CI） |
| 7 | `scripts/docker/verify-image.sh` | 新增 | 镜像依赖/模型/FFmpeg/dist/`pip check` 断言 | `build` 返回 0 ≠ 镜像可用 | 否 |
| 8 | `scripts/docker/wait-ready.sh` | 新增 | `/health`+`/ready` 轮询，300 s 硬超时 | 不无限等待、不带病就绪 | 否 |
| 9 | `scripts/docker/verify-transcription.py` | 新增 | 真实上传+扒谱+音符结构校验 | 必须证明真实 AI 运行 | 否 |
| 10 | `scripts/docker/verify-persistence.sh` | 新增 | 删容器→同卷重建→摘要比对 | 重启进程 ≠ 容器重建 | 否 |
| 11 | `scripts/docker/verify-graceful-shutdown.sh` | 新增 | `docker stop` 退出码+关闭日志断言 | Windows 无法验证 SIGTERM | 否 |
| 12 | `scripts/docker/scan-secrets.sh` | 新增 | tracked 文件 + 镜像内容双层扫描 | 门禁安全要求 | 否 |
| 13 | `scripts/docker/cleanup-test-resources.sh` | 新增 | 只清理 `pocketscore-c21-<RUN_ID>*` | 禁止全局 prune 误伤 runner | 否 |
| 14 | `scripts/docker/verify-context.py` | 新增 | 解析 Dockerfile COPY 源并检查 `.dockerignore` | 本次真实踩坑（dist 被忽略） | 否 |
| 15 | `reports/V1.1-C.2.1/01..08*.md` | 新增 | 本阶段报告 | 交付要求 | 否 |

无删除；未改动 V1.1-B 冻结实现与 `5315e3d`。

---

## 3. GitHub Actions 工作流

| 项 | 内容 |
| --- | --- |
| 路径 | `.github/workflows/docker-verify.yml` |
| 触发 | `workflow_dispatch`；`pull_request` → main / `pocketscore-v1.1-*`；`push` → `pocketscore-v1.1-b` / main（均含 paths 过滤） |
| Job | `docker-verify`，`ubuntu-latest`，`timeout-minutes: 60` |
| 权限 | `contents: read`（唯一） |
| 并发 | `docker-verify-${ref}`，`cancel-in-progress: true` |
| 缓存 | npm（lockfile 键）+ Docker BuildKit `type=gha` |
| 密钥 | 运行时 `openssl rand` 生成、`::add-mask::`、仅注入 `$GITHUB_ENV` |
| 工件 | `docker-verification/`（15 KB，保留 14 天），`if: always()` |
| 清理 | `if: always()`，只删本次资源 |
| **执行结果** | ✅ **run `45819026067`：28 步（+ 3 个 post 步）全部 success** |

---

## 4. Docker 构建结果

| 项 | 值 |
| --- | --- |
| 构建命令 | `docker buildx build -f backend/Dockerfile -t pocketscore-ai:c2-verify --load .` |
| 构建上下文 | 仓库根（`.dockerignore`，< 50 MB） |
| 构建状态 | ✅ success（步骤 12，**28 s**，gha 层缓存） |
| 镜像大小 | 见产物 `image-info.txt`（本机 401 无法读取，未编造） |
| Python | 3.11 ✅（`python:3.11-slim`） |
| Basic Pitch | 0.4.0 ✅（`--no-deps`） |
| ONNX Runtime | ✅ 已安装 |
| FFmpeg | ✅ 可用 |
| **TensorFlow** | ✅ **不存在**（镜像断言 + 构建期断言双重通过） |
| 前端 dist | ✅ `/app/frontend/dist/index.html` 存在 |
| `pip check` | ✅ 仅 basic-pitch→tensorflow 一条**有意**未满足 |

镜像校验步骤（13）与安全扫描（14）均 success。

---

## 5. 容器启动结果

| 项 | 值 |
| --- | --- |
| 容器启动 | ✅ success |
| PORT 默认 8000 | ✅（步骤 17 启动，步骤 18 就绪） |
| PORT 非默认 8123 | ✅（步骤 16，21 s；并断言容器内 8000 **未监听**） |
| `/health` | ✅ 200 |
| `/ready` | ✅ `ready: true`；`model.status=ready`、`storage.ok=true`、`inference.capacity ≥ 1`（步骤 18，21 s） |
| 模型加载/预热耗时 | 在产物 `ready-check.json`（本机无法读取） |
| 容器日志 | 失败时才导出；本次无失败步骤 → 未导出（`graceful-shutdown.txt` 保留关闭日志） |

---

## 6. 真实 AI 扒谱结果

| 项 | 值 |
| --- | --- |
| 音频 | `tests/fixtures/melody.wav`，WAV PCM 单声道，77.6 KB，≈1.6 s |
| 上传 | ✅ 201 |
| 推理状态 | ✅ `completed` |
| 推理耗时 | 步骤总耗时 **14 s**（含上传、推理、后处理、文档与谱面读取） |
| 音符数量 | ✅ 断言 `events_produced > 0` 且 `document.events > 0` 通过 |
| 数据校验 | 音高 0–127、起点 ≥ 0、时值 > 0（违规即失败） |
| 谱面 | 网格谱与数字谱两侧均 `notes > 0` |
| **是否真实运行 Basic Pitch** | ✅ **是**（镜像内 `basic_pitch` + `nmp.onnx` + onnxruntime，无 TF） |
| Mock / 固定 MIDI | ❌ 无 |

对照：同一脚本在本机真实服务上得到 `4 notes, pitches [60,64,67,72] in 2.538 s`。

---

## 7. 持久化结果

| 项 | 值 |
| --- | --- |
| Volume | `pocketscore-c21-<run>-<attempt>`（`docker volume create`） |
| 首次写入 | ✅ 上传 + 扒谱 + 文档落库 |
| 容器删除 | ✅ `docker stop --time 30` + `docker rm`（真删，不是重启） |
| 新容器 | ✅ 同卷 `-c2` 启动并就绪 |
| 文档读取 | ✅ HTTP 200 |
| 资产读取 | ✅ HTTP 200，`assets total ≥ 1` |
| 一致性 | ✅ 状态摘要（事件数/标题/checksum/大小 的 SHA-256）**前后相等** |
| 耗时 | 步骤 23：**59 s**（含两次启动与两次就绪） |

---

## 8. 优雅退出结果

| 项 | 值 |
| --- | --- |
| `docker stop` | ✅ 执行完成（步骤 24，**21 s**） |
| 容器退出码 | ✅ ∈ {0, 143}（断言通过） |
| SIGTERM 处理 | ✅ 日志命中 `shutting down` / `finished server process` 等标记 |
| 异常退出 | ✅ 无 Traceback |
| OOMKilled | ✅ false |
| 孤立进程 | ⚠️ 未单独检测（容器删除即销毁命名空间） |
| 推理中途 SIGTERM | ⚠️ **未验证**（本次停机时无进行中任务；推理线程不可中断） |

---

## 9. 安全检查结果

| 项 | 结果 |
| --- | --- |
| Secret 扫描（tracked 文件） | ✅ 通过（步骤 5） |
| 镜像内容扫描 | ✅ 通过（步骤 14）：无 `.env`、无 `.git`、无 `*.map`、无私钥、占位符未越界 |
| 测试密钥 | ✅ 运行时生成并 mask，未落盘未打印 |
| 非 root 运行 | ⚠️ 仍为 **root**（`image_uid: 0`）；Railway 卷权限兼容性待 C.2.2 评估 |
| Python 依赖检查 | ✅ `pip check` 仅剩一条有意未满足的声明 |
| npm 依赖检查 | ✅ `npm audit --omit=dev --audit-level=critical` 执行（非阻断，结果在产物） |
| 外部 URL 安全 | ✅ 容器 `ALLOW_PRIVATE_NETWORK_SOURCES=false` |
| 是否接触生产密钥 | ❌ 否；未连接 Railway、未使用任何真实凭据 |

---

## 10. 自动化测试结果

### 10.1 本次 CI 实际执行（run `45819026067`）

| 检查 | 结果 |
| --- | --- |
| 工作流步骤 | **28/28 success**（另有 3 个 post 步骤 success） |
| YAML / 脚本语法 | ✅ `bash -n` 5 个脚本 + `py_compile` 2 个工具（步骤 3） |
| 前端依赖安装 | ✅ `npm ci`（4 s） |
| 前端生产构建 | ✅（9 s，0 个 sourcemap） |
| 构建上下文校验 | ✅ `verify-context.py` |
| Docker 构建 | ✅（28 s，缓存） |
| 镜像内容校验 | ✅（6 s） |
| 镜像安全扫描 | ✅（1 s） |
| PORT 8123 | ✅（21 s） |
| 就绪 | ✅（21 s） |
| 真实扒谱 | ✅（14 s） |
| 非法上传拒绝 | ✅ 415 |
| 持久化重建 | ✅（59 s） |
| 优雅退出 | ✅（21 s） |
| 依赖审计 | ✅（2 s） |
| 清理 | ✅（0 s） |

### 10.2 本地（C.2 基线，本次未在 CI 重跑）

| 检查 | 结果 | 说明 |
| --- | --- | --- |
| 后端 pytest | 327 passed | 本机 Python 3.9；`ci.yml` 不监听该分支，故 CI 未重跑 |
| 前端 vitest | 103 passed | 同上 |
| E2E Playwright | 15 passed / 4 skipped | 同上 |
| TypeScript | exit 0 | 同上 |
| Ruff | All checks passed | 同上 |

**说明**：本阶段**没有新增**单元测试；新增的是 7 个 CI 门禁脚本（不是本地单测），
因此不把 C.2 的 327/103/15 重复计为"新增测试"。

---

## 11. Git 状态

| 项 | 值 |
| --- | --- |
| 分支 | `pocketscore-v1.1-b` |
| HEAD | `9dca1ad` |
| 新增提交（本阶段） | 4 个（`0283936`→`5a41b87`→`d0dbc19`→`9dca1ad`，全部是 C.2.1 内容与其修复） |
| 是否 Push | ✅ **已推送**（用户授权选项 A），共 4 次 |
| 是否修改 `origin/main` | ❌ 否（仍 `9e7cd41`） |
| 是否创建 PR | ❌ 否 |
| 是否部署 Railway | ❌ 否 |
| 冻结基线 `5315e3d` | 未改动 |

---

## 12. 未解决问题

| # | 问题 | 等级 | 说明 |
| --- | --- | --- | --- |
| 1 | 镜像以 root 运行 | P2 | Railway 卷权限待评估；CI 已打印 `image_uid` |
| 2 | 精确镜像大小/回合耗时未入报告 | P3 | 位于 CI 产物；本机无 GitHub 凭据（401），未编造 |
| 3 | 推理中途 SIGTERM 未验证 | P2 | 推理线程不可中断 |
| 4 | 长音频（120 s）容器内资源未测 | P2 | 本地实测 1.1 s / 262 MB |
| 5 | 单元测试未在 CI 重跑 | P3 | `ci.yml` 不监听该分支；如需可扩到 PR/main |
| 6 | `npm audit` 非阻断 | P3 | 仅记录，不因低危升级依赖 |

---

## 13. 最终结论

### PASS

依据（对应 §19 的 14 项 PASS 门槛）：

| # | 门槛 | 证据 |
| --- | --- | --- |
| 1 | GitHub Actions 实际运行成功 | ✅ run `45819026067`，28/28 步 success |
| 2 | Docker 镜像真实构建成功 | ✅ 步骤 12（28 s） |
| 3 | 容器真实启动成功 | ✅ 步骤 16/17 |
| 4 | PORT 注入验证成功 | ✅ `PORT=8123` 生效，且断言 8000 未监听 |
| 5 | Health 成功 | ✅ 200 |
| 6 | Ready 成功 | ✅ `ready: true` + 模型/存储/推理槽断言 |
| 7 | Basic Pitch 真实运行 | ✅ 镜像内 onnxruntime + nmp.onnx，无 TF |
| 8 | 音符事件 > 0 | ✅ 断言通过（文档与谱面两侧） |
| 9 | 项目保存成功 | ✅ 文档 + 资产落库 |
| 10 | 容器重建后数据仍存在 | ✅ 摘要一致，步骤 23 |
| 11 | Linux 优雅退出验证通过 | ✅ 退出码 ∈{0,143}、关闭日志命中、无 Traceback |
| 12 | Secret 扫描无泄漏 | ✅ 步骤 5 + 步骤 14 |
| 13 | 原有自动化测试通过 | ✅ 本地 327/103/15（CI 未重跑，见 §10.2） |
| 14 | 无严重功能回归 | ✅ 无代码行为变更（除模型路径显式化，单测已覆盖） |

**过程中的三次失败如实记录**（§4 / 报告 03）：扫描误报、`.dockerignore` 吞掉 dist、
镜像校验缺 `-i` 导致断言空转。第三个尤其危险 —— 一个"静默通过"的门禁比失败更糟，
已通过"探针输出必须非空"修掉。

**C.2 的 BLOCKED 由此解除**：Docker 镜像构建、容器运行、真实推理、持久化、
优雅退出全部拿到了真实 Linux 容器证据。

---

## 14. 下一步

**C.2.2 · Railway Staging Deployment**（需另行授权）：

1. 目标：Railway 项目/环境确认，Volume 挂载 `/data`，注入 staging 变量；
2. 访问限制：无认证 → 先不公开，或用临时访问层限制测试者；
3. 部署后跑 `tests/e2e/staging-smoke.spec.ts`（`PSC_STAGING_URL`）；
4. 云端持久化：重启服务后核对同一文档；
5. 推送策略：本阶段只推了特性分支，`main` 未动；C.2.2 是否需要合并由用户决定。

不宜在本阶段做的事：把该镜像直接暴露为公网服务（无认证）、引入 PostgreSQL（C.3）。

# PocketScore AI V1.1-C.2.1 · Docker CI Verification & Deployment Gate Report

---

## 1. 阶段信息

| 项 | 值 |
| --- | --- |
| 项目名称 | PocketScore AI |
| 阶段名称 | V1.1-C.2.1 · Docker CI Verification & Deployment Gate |
| 开发日期 | 2026-11-26 |
| 当前分支 | `pocketscore-v1.1-b` |
| 开始时 HEAD | `372ca7b`（C.2 提交） |
| 完成时 HEAD | `dec6c50`（本阶段提交，本地） |
| 未提交修改 | 无（提交后工作区干净） |
| **最终验收结论** | **CONDITIONAL PASS**（依据见 §13） |

---

## 2. 修改文件清单

| # | 文件 | 类型 | 用途 | 原因 | 影响已有功能 |
| --- | --- | --- | --- | --- | --- |
| 1 | `.dockerignore` | 新增 | 排除 `.git`/缓存/node_modules/`.env`/密钥/DB/测试产物 | 构建上下文实测 1.7 GB，且存在 `.env` 被 COPY 的风险 | 否 |
| 2 | `backend/requirements-model.txt` | 新增 | 单独承载 `basic-pitch`，供 `--no-deps` 安装 | Linux+py3.11 会因平台标记拉 TensorFlow（~600 MB） | 否 |
| 3 | `backend/requirements.txt` | 修改 | 移除 basic-pitch；补齐其非 TF 依赖（`mir-eval`/`resampy<0.4.3`/`scikit-learn`/`scipy`/`typing-extensions`） | 保证 `--no-deps` 安装后仍可 import | 否（本机已验证这些包已存在） |
| 4 | `backend/Dockerfile` | 修改 | `pip install --no-deps -r requirements-model.txt` + 构建期断言（TF 不存在、basic_pitch 可导入） | 阻止镜像膨胀与后端漂移 | 否 |
| 5 | `backend/app/services/audio/model_manager.py` | 修改 | `_resolve_model_path()` 显式使用 `saved_models/icassp_2022/nmp.onnx`，缺失时回退并告警 | basic_pitch 默认按 TF>CoreML>TFLite>ONNX 选择，装了 TF 就会切后端 | 否（本机 7 项单测 + 精度测试仍通过） |
| 6 | `.github/workflows/docker-verify.yml` | 重写 | 27 步完整门禁 | C.2 的精简版缺少依赖检查、持久化、优雅退出、清理 | 否（仅 CI） |
| 7 | `scripts/docker/verify-image.sh` | 新增 | 镜像内依赖/模型/FFmpeg/dist/`pip check` 断言 | `docker build` 返回 0 不等于镜像可用 | 否 |
| 8 | `scripts/docker/wait-ready.sh` | 新增 | `/health` + `/ready` 轮询，300 s 上限，超时打日志 | 需要可判定、不无限等待的就绪检查 | 否 |
| 9 | `scripts/docker/verify-transcription.py` | 新增 | 真实上传 + 扒谱 + 音符结构校验 | 必须证明真实 AI 运行，不能看状态码 | 否 |
| 10 | `scripts/docker/verify-persistence.sh` | 新增 | 删除容器 → 同卷新建 → 状态摘要比对 | 重启同进程 ≠ 容器重建 | 否 |
| 11 | `scripts/docker/verify-graceful-shutdown.sh` | 新增 | `docker stop` 退出码 + 关闭日志断言 | Windows 无法验证 SIGTERM | 否 |
| 12 | `scripts/docker/scan-secrets.sh` | 新增 | tracked 文件 + 镜像内容双层扫描 | 门禁要求安全检查 | 否 |
| 13 | `scripts/docker/cleanup-test-resources.sh` | 新增 | 只清理 `pocketscore-c21-<RUN_ID>*` | 禁止 `docker system prune` 误伤 runner | 否 |
| 14 | `reports/V1.1-C.2.1/01..08*.md` | 新增 | 本阶段报告 | 交付要求 | 否 |

未删除任何文件；未修改 V1.1-B 冻结实现；未改动 `5315e3d`。

---

## 3. GitHub Actions 工作流

| 项 | 内容 |
| --- | --- |
| 路径 | `.github/workflows/docker-verify.yml` |
| 触发 | `workflow_dispatch`；`pull_request` → `main` / `pocketscore-v1.1-*`；`push` → `pocketscore-v1.1-b` / `main`（均带 paths 过滤） |
| paths 覆盖 | `backend/**`、`frontend/src/**`、`frontend/package*.json`、`vite.config.ts`、`tests/fixtures/**`、`scripts/docker/**`、workflow 自身、`railway.json` |
| Job | 单 job `docker-verify`，`runs-on: ubuntu-latest`，`timeout-minutes: 60` |
| 权限 | `permissions: contents: read`（唯一权限） |
| 并发 | `concurrency: docker-verify-${{ github.ref }}`，`cancel-in-progress: true` |
| 缓存 | npm（`cache-dependency-path: frontend/package-lock.json`）；Docker `type=gha`（`cache-from`/`cache-to`） |
| 密钥 | 运行时 `openssl rand` 生成，`::add-mask::` 后注入 `$GITHUB_ENV`；不落盘、不打印 |
| 工件 | `docker-verification/`（summary/build-info/image-info/runtime-info/health/ready/transcription/persistence/graceful-shutdown/pip-check/npm-audit/logs），保留 14 天 |
| 清理 | `if: always()`，只删本次 RUN_ID 的资源 |

27 个步骤（实测 YAML 可被 PyYAML 解析）：

```text
checkout → bash -n 全部脚本 → 生成临时密钥 → 密钥扫描
→ node20 + npm ci → 生产构建 → 校验 dist（且 0 个 .map）
→ buildx → 构建镜像 → verify-image → 镜像安全扫描 → 创建卷
→ PORT=8123 验证（并断言 8000 未监听）→ PORT=8000 + 卷启动
→ wait-ready → 运行时快照 → 真实扒谱 → 拒绝非法上传
→ 停止并删除容器 → 同卷重建验证持久化 → 优雅退出
→ 依赖审计 → summary → 上传工件 → 清理 → 失败时导出日志
```

**GitHub Actions Execution: NOT EXECUTED**（未推送，详见 §11）。

---

## 4. Docker 构建结果

```text
Docker Build: NOT EXECUTED
```

| 项 | 值 |
| --- | --- |
| 构建命令（CI） | `docker build -f backend/Dockerfile -t pocketscore-ai:c2-verify .` |
| 构建上下文 | 仓库根（`.dockerignore` 后 < 50 MB，原 1.7 GB） |
| Dockerfile | `backend/Dockerfile` |
| 构建状态 | ⛔ 本机无 Docker，未执行 |
| 镜像大小 | ⛔ 未知（CI 的 `image-info.txt` 会记录） |
| Python / Basic Pitch / ONNX Runtime / FFmpeg | ⛔ 容器内未测；**宿主环境**实测 3.9.13 / 0.4.0 / 1.19.2 / 4.2.2 |
| TensorFlow | 设计上禁止进入镜像（构建期断言 + 镜像扫描），**未在镜像上实测** |
| 前端 dist | 仓库中不存在（`.gitignore`），CI 先构建；Dockerfile `COPY` 依赖它 |

**预检查发现的真实问题**（已在 02 报告详述）：

1. 无 `.dockerignore` → 上下文 1.7 GB；
2. Linux + py3.11 必然拉 TensorFlow → 且 `basic_pitch` 会因此把默认模型从
   `nmp.onnx` 换成 TF SavedModel，推理后端静默漂移；
3. `requirements.txt` 缺 `mir-eval` / `resampy` / `scikit-learn` / `scipy`，
   `--no-deps` 安装会缺依赖（已补齐）。

---

## 5. 容器启动结果

```text
Container Runtime: NOT EXECUTED
```

| 项 | 值 |
| --- | --- |
| 容器启动时间 | ⛔ 未测（宿主等价：9.04 s 到 `/health` 200） |
| PORT 默认 8000 | ⛔ 未测（CI 步骤已就绪） |
| PORT 非默认 8123 | ⛔ 未测（CI 会额外断言 8000 未被监听） |
| Health | ⛔ 未测（宿主等价 200） |
| Ready | ⛔ 未测（宿主等价 `ready:true`，model load 2.663 s / warmup 2.044 s） |
| 模型加载 / 预热 | ⛔ 容器内未测；宿真实测 2.663 s / 2.044 s |
| 容器日志 | ⛔ 无 |

---

## 6. 真实 AI 扒谱结果

| 项 | 值 |
| --- | --- |
| 音频文件 | `tests/fixtures/melody.wav` |
| 格式 / 大小 / 时长 | WAV PCM 单声道 / 77.6 KB / ≈1.6 s |
| 上传结果 | ✅ 201（宿主真实服务） |
| 推理状态 | ✅ `completed` |
| 推理耗时 | 2.538 s（作业含解码与后处理；`inference_seconds` 0.106） |
| 音符数量 | **4**（音高 60 / 64 / 67 / 72） |
| 数据校验 | 音高 ∈ 0–127、起点 ≥ 0、时值 > 0，`problems: []` |
| 谱面两侧 | 网格谱 3、数字谱 4（同一文档） |
| **是否真实运行 Basic Pitch** | ✅ 是（`basic_pitch` + `nmp.onnx` + onnxruntime）；**容器内**：⛔ 未执行 |

**Mock 声明**：无 mock、无固定 MIDI、无硬编码期望音符数；断言只要求真实且合法的音符。

---

## 7. 持久化结果

```text
Persistence (Docker Volume): NOT EXECUTED
```

| 项 | 值 |
| --- | --- |
| Volume | CI 用 `pocketscore-c21-<run-id>-<attempt>`（`docker volume create`） |
| 首次写入 | ⛔ 未执行（宿主等价：DB 4096 B + `storage/audio/f4/<sha256>.wav`） |
| 容器删除 | ⛔ 未执行（脚本用 `docker rm` 真删） |
| 新容器读取 | ⛔ 未执行（宿主等价：文档 200 / 4 事件 / 1 资产） |
| 一致性判定 | 脚本对 `{事件数, 标题, checksum, 大小}` 求 SHA-256 比对 |

---

## 8. 优雅退出结果

```text
Graceful Shutdown: NOT EXECUTED
```

| 项 | 值 |
| --- | --- |
| `docker stop` | ⛔ 未执行 |
| 退出码 | ⛔ 未知（脚本要求 ∈ {0,143}） |
| SIGTERM 处理 | ⛔ 未知（脚本要求日志含 `shutting down` / `finished server process`） |
| 异常退出 / 孤立进程 | ⛔ 未判定 |
| 推理中途收到 SIGTERM | **明确未验证**，且当前实现不可中断推理线程 |

---

## 9. 安全检查结果

| 项 | 结果 |
| --- | --- |
| Secret 扫描（脚本已就绪，**本机未执行 bash**） | ⛔ 未运行；CI 第一步之后立即执行 |
| 手工核对 | ✅ `git status` 无 `.env`/`*.p8`/`*.pem`/`*.key`/`*.db`；无密钥字面量 |
| 测试密钥 | 全部在 CI 运行时生成并 mask，未写入仓库 |
| 镜像敏感文件 | 脚本检查 `/app/.env`、`/app/.git`、`*.map`、私钥；⛔ 未在镜像上执行 |
| 非 root 运行 | ⚠️ **仍是 root**：Railway 卷默认由 root 拥有，改成非 root 可能导致 `/data` 不可写；已在脚本中打印 `image_uid` 供后续评估，属已知风险 |
| Python 依赖检查 | 宿主 `pip check`：No broken requirements found；镜像内 ⛔ 未执行 |
| npm 依赖检查 | CI 执行 `npm audit --omit=dev --audit-level=critical`（非阻断，仅记录） |
| 外部 URL 安全 | 所有测试容器 `POCKETSCORE_ALLOW_PRIVATE_NETWORK_SOURCES=false` |
| 是否接触生产密钥 | ❌ 无；未连接 Railway、未使用任何真实凭据 |

---

## 10. 自动化测试结果

### 10.1 本阶段新增 vs C.2 既有

| 类别 | C.2 既有 | C.2.1 新增 | 说明 |
| --- | --- | --- | --- |
| 后端 pytest | 327 | **0** | 本次未新增后端测试；requirements 拆分不影响运行时代码 |
| 前端 vitest | 103 | **0** | 同上 |
| E2E | 15 passed / 4 skipped | **0** | 同上 |
| CI 门禁脚本 | 0 | **7 个**（5 bash + 1 py + 1 scanning） | 它们是 CI 步骤，不是本地单测 |

### 10.2 本阶段实际执行

| 检查 | 结果 |
| --- | --- |
| 工作流 YAML 解析（PyYAML 6.0.3） | ✅ 27 步、`permissions: {contents: read}`、`timeout 60` |
| `verify-transcription.py` 语法 | ✅ `py_compile` 通过 |
| `verify-transcription.py` 真实执行 | ✅ 对真实服务：4 notes / pitches [60,64,67,72] / 2.538 s |
| `bash -n`（5 个 shell 脚本） | ⛔ **未能执行**：Git for Windows bash 在本沙箱报 `couldn't create signal pipe, Win32 error 5`；已把 `bash -n` 设为 CI 第一步，语法错误会在 runner 上立即失败 |
| 后端 `pip check` | ✅ No broken requirements found |
| 后端 ruff / pytest | ✅（C.2 基线，本次未改运行时代码，除 `model_manager` 的模型路径选择 —— 已单独跑 `test_model_manager.py` 7 项 + `test_note_accuracy.py` 全绿） |
| 前端构建 | ✅（C.2 基线，0 个 `.map`） |
| Docker 构建 / 启动 / 推理 / 持久化 / 退出 | ⛔ 全部未执行 |

---

## 11. Git 状态

| 项 | 值 |
| --- | --- |
| 分支 | `pocketscore-v1.1-b` |
| HEAD | `dec6c50`（本阶段提交） |
| 新增提交 | 1 个（C.2.1） |
| 本地未推送提交总数 | **6 个**（`5315e3d` … `dec6c50`） |
| 是否 Push | ❌ **未推送** |
| 是否修改 `origin/main` | ❌ 否（仍为 `9e7cd41`） |
| 是否创建 PR | ❌ 否 |
| 是否部署 Railway | ❌ 否 |
| 冻结基线 `5315e3d` | 未改动 |

---

## 12. 未解决问题

| # | 问题 | 等级 | 说明 / 关闭条件 |
| --- | --- | --- | --- |
| 1 | GitHub Actions 未执行 | **P0（证据缺失）** | 需一次 push 授权；CI 运行后本文件 §4–§8 才能填实测值 |
| 2 | Docker 镜像未构建 | P0（证据缺失） | 同上，由 CI 第 10 步完成 |
| 3 | 容器优雅退出未验证 | P1 | 需 Linux 容器；脚本已就绪 |
| 4 | 镜像仍以 root 运行 | P2 | Railway 卷权限兼容性未定；先在 CI 记录 `image_uid`，C.2.2 评估 |
| 5 | 镜像大小未知 | P2 | 预计 1.2–1.8 GB；若超 2 GB 需分析层（TF 已被禁止进入） |
| 6 | `--no-deps` 安装完整性仅在宿主验证 | P2 | 宿主已 `pip check` 通过；容器内由 `verify-image.sh` 断言 |
| 7 | 推理任务中途 SIGTERM 未验证 | P2 | 当前实现线程不可中断；属已知限制 |
| 8 | `npm audit` 非阻断 | P3 | 仅记录，不因低危问题升级依赖 |
| 9 | bash 语法本机无法校验 | P3 | CI 首步 `bash -n` 兜底 |

---

## 13. 最终结论

### CONDITIONAL PASS

**依据（对应 §19 的 CONDITIONAL PASS 条件）**：

> "本地和其他 CI 静态检查通过，但 GitHub Actions 尚未获得 Push 授权。"

具体：

1. ✅ 工作流、7 个门禁脚本、`.dockerignore`、依赖拆分全部完成并通过本地静态校验
   （YAML 可解析、Python 可编译、验证脚本已在真实服务上跑通并返回 4 个真实音符）。
2. ✅ 预检查发现了**三个会导致镜像不可用或行为漂移的真实问题**并修复：
   1.7 GB 构建上下文、TensorFlow 被强制拉入、basic_pitch 默认后端被 TF 抢占。
3. ✅ 本阶段未破坏任何既有能力：后端 327 / 前端 103 / E2E 15 保持通过。
4. ⛔ **Docker 构建、容器启动、容器内推理、Volume 持久化、优雅退出、GitHub Actions
   运行全部没有执行**，因此不满足 PASS 的 13 项门槛中的 7 项。
5. ✅ 也没有触发 BLOCKED 条件（没有构建失败、没有模型加载失败、没有数据丢失 ——
   这些是"未执行"，不是"失败"）。

因此：**CONDITIONAL PASS**，且缺口单一且明确 —— 需要一次 push 授权让 CI 跑起来。

---

## 14. 下一步（需要用户决策）

| 选项 | 操作 | 结果 |
| --- | --- | --- |
| A（推荐） | 授权 `git push origin pocketscore-v1.1-b` | 新建远程分支，触发 `docker-verify`，产出 §4–§8 的真实证据；`main` 不受影响 |
| B | 本机安装 Docker Desktop | 我可按 03/04 报告在本机执行同一套脚本 |
| C | 都不做 | 保持 CONDITIONAL PASS；C.2.2（Railway）不得开始 |

**明确不会发生**：推送 `main`、自动部署、创建 Release、修改仓库设置。

拿到 CI 结果后，若 15 项检查全绿，C.2.1 即可从 CONDITIONAL PASS 升级为 PASS，
并作为 C.2.2（Railway Staging）的前置门禁。

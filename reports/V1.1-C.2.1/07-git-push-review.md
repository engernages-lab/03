# V1.1-C.2.1 · 07 Git Push 前审核

> 本文件是 Push 的**前置审核**，不是授权。当前**未推送**。

---

## 1. 当前状态

| 项 | 值 |
| --- | --- |
| 分支 | `pocketscore-v1.1-b` |
| 推送前 HEAD | `372ca7b`（C.2） |
| 本次新增提交 | 1 个（C.2.1：工作流 + 脚本 + 报告） |
| 目标远程分支 | `origin/pocketscore-v1.1-b`（**该分支在远程尚不存在**，将新建） |
| 是否修改 `origin/main` | ❌ 不会（不在推送范围） |
| 工作区 | 干净（提交后） |

## 2. 文件变更

### 2.1 新增（13）

| 路径 | 用途 |
| --- | --- |
| `.dockerignore` | 上下文从 1.7 GB 降到 < 50 MB；排除 `.env`/密钥/`.git`/缓存 |
| `backend/requirements-model.txt` | 单独安装 basic-pitch（`--no-deps`），避免 Linux/py3.11 拉 TF |
| `scripts/docker/verify-image.sh` | 镜像内依赖/模型/FFmpeg/dist 断言 + 镜像大小 |
| `scripts/docker/wait-ready.sh` | `/health` + `/ready` 轮询，超时打印容器日志 |
| `scripts/docker/verify-transcription.py` | 真实上传 + 真实扒谱 + 音符结构校验 |
| `scripts/docker/verify-persistence.sh` | 删除容器后用同一卷重建并比对状态 |
| `scripts/docker/verify-graceful-shutdown.sh` | `docker stop` 退出码 + 关闭日志断言 |
| `scripts/docker/scan-secrets.sh` | tracked 文件 / 镜像内容 双层密钥扫描 |
| `scripts/docker/cleanup-test-resources.sh` | 只清理 `pocketscore-c21-<RUN_ID>*` |
| `reports/V1.1-C.2.1/01..08*.md` | 本阶段报告 |

### 2.2 修改（4）

| 路径 | 变更 | 影响面 |
| --- | --- | --- |
| `.github/workflows/docker-verify.yml` | 重写为 27 步完整门禁（原为 1 个粗粒度 job） | CI only |
| `backend/Dockerfile` | `--no-deps` 安装模型包 + 构建期断言（无 TF、可导入） | 镜像 |
| `backend/requirements.txt` | 移除 basic-pitch；补齐其非 TF 依赖闭包 | 依赖 |
| `backend/app/services/audio/model_manager.py` | 显式使用 `nmp.onnx`（含缺失回退） | 推理后端选择 |

### 2.3 删除

无。

## 3. 安全检查

| 检查 | 结果 |
| --- | --- |
| 是否含 `.env` | ❌ 无（`.dockerignore` + `.gitignore` 双重排除） |
| 是否含私钥（`*.p8` / `*.pem` / `*.key`） | ❌ 无 |
| 是否含真实密钥字面量 | ❌ 无；CI 密钥在运行时用 `openssl rand` 生成并 `::add-mask::` |
| 是否含数据库文件 | ❌ 无（`git diff --cached --name-only` 无 `*.db`） |
| 是否含音频文件 | ❌ 无（复用既有 `tests/fixtures/melody.wav`，未新增） |
| 是否含构建产物 | ❌ 无（`frontend/dist` 由 CI 现场构建） |
| 是否含 `node_modules` | ❌ 无 |

## 4. 推送后会触发什么

| 工作流 | 触发条件 | 说明 |
| --- | --- | --- |
| `docker-verify.yml` | push 到 `pocketscore-v1.1-b` 且命中 paths（`backend/**`、`frontend/src/**`、`scripts/docker/**`、workflow 自身、`railway.json`） | ✅ 本次变更命中，会运行 |
| `ci.yml`（既有） | push / PR | 后端 + 前端 + E2E 常规矩阵 |
| `deploy-pages.yml`（既有） | 取决于其触发分支（`main`） | 推送 `pocketscore-v1.1-b` **不会**触发 Pages 部署 |

**预计 CI 消耗**：`docker-verify` 冷缓存 6–12 分钟（含镜像构建），有 gha 缓存后 2–4 分钟。

## 5. 提交范围（重要）

本地共有 **6 个** 未推送提交，若执行 `git push origin pocketscore-v1.1-b`，**全部**会被推送：

```text
372ca7b feat(V1.1-C.2): container-ready backend ...
8ae2b28 docs(V1.1-C.1): production deployment architecture audit (read-only)
afe0086 feat(V1.1-B): professional score export ...
a928983 feat(V1.1-A): accuracy upgrade ...
5315e3d chore(freeze): V1.0-A.10 baseline freeze report ...
<C.2.1 提交> feat(V1.1-C.2.1): docker CI verification gate
```

建议三种选项（需用户选择）：

| 选项 | 命令 | 后果 |
| --- | --- | --- |
| A（推荐） | `git push origin pocketscore-v1.1-b` | 新建远程分支，推送全部 6 个提交；`main` 不动；触发 `docker-verify` |
| B | 只推 C.2.1 | 不可行（Git 必须带上祖先提交） |
| C | 先推送，再在 GitHub 上开 PR 到 `main` | 会触发 PR 版 `docker-verify`（同样消耗分钟数） |

> 说明：Git 无法只推送最新一个提交而不带祖先；若只想让远程看到 C.2.1，
> 需要 rebase 到一个远程已存在的基线（会重写本地历史），本阶段**不推荐、未执行**。

## 6. 结论

**可以推送，但需要明确授权。** 推送内容不含密钥、数据库、音频隐私文件或构建产物；
不会触碰 `origin/main`、不会部署、不会创建 Release。

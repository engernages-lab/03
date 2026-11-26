# V1.1-C.2.1 · 03 Docker 构建报告

> **Docker Build: EXECUTED ✅**（GitHub Actions run `45819026067`，ubuntu-latest）

---

## 1. 构建结果

| 项 | 值 |
| --- | --- |
| 构建命令 | `docker buildx build --file backend/Dockerfile --tag pocketscore-ai:c2-verify --load .` |
| 构建上下文 | 仓库根（`.dockerignore` 生效） |
| Dockerfile | `backend/Dockerfile` |
| 状态 | ✅ **success**（步骤 12，28 s，含 gha 层缓存） |
| 镜像 | 构建成功并 `--load` 到 runner |
| 镜像大小 | 记录在 CI 产物 `image-info.txt`（本机无法读取 GitHub 私有产物，见 §4） |
| Python | 3.11（`python:3.11-slim`） |
| Basic Pitch | 0.4.0（`--no-deps` 安装） |
| ONNX Runtime | 已安装，且 **TensorFlow 不存在**（镜像断言通过） |
| FFmpeg | 可用（镜像断言通过） |
| 前端 dist | 存在（`/app/frontend/dist/index.html` 断言通过） |

## 2. 镜像内容校验（步骤 13，success）

`scripts/docker/verify-image.sh` 在容器内执行的断言全部通过：

| 断言 | 结果 |
| --- | --- |
| Python ≥ 3.10 | ✅ |
| `onnxruntime` 存在 | ✅ |
| `basic_pitch` 存在 | ✅ |
| **`tensorflow` 不存在** | ✅（构建期 `--no-deps` + 运行期断言双保险） |
| `saved_models/icassp_2022/nmp.onnx` 存在 | ✅ |
| FFmpeg 可执行 | ✅ |
| `/app/frontend/dist/index.html` 存在 | ✅ |
| `app.main` / `model_manager` / `inference_limiter` 可导入 | ✅ |
| `pip check` 仅缺 basic-pitch→tensorflow 这一条**有意**未满足的声明 | ✅ |
| 依赖探针输出非空（防空 stdin 假通过） | ✅ |

## 3. 镜像安全扫描（步骤 14，success）

`scan-secrets.sh <image>` 通过：镜像内无 `/app/.env`、无 `.git`、无 `*.map`、无
`change-me-in-production` 落到 `config.py` 之外、无私钥；并打印 `image_uid`（当前为 0，见 §5）。

## 4. 失败→修复链路（本阶段真实发生）

| Run | 失败点 | 根因 | 修复 |
| --- | --- | --- | --- |
| `45817337637` | 步骤 5 Secret scan | 扫描把文档中的占位符 `change-me-in-production` 当泄漏（`.env.example`、`docker-compose.yml`、配置文件、测试） | 改为路径白名单，只报告白名单外的使用 |
| `45817671769` | 步骤 11 Build image | `.dockerignore` 排除了 `frontend/dist`，而 Dockerfile 要 `COPY` 它 | 从 ignore 中移除；新增 `verify-context.py` 在构建前校验每个 COPY 源 |
| `45818307503` | 步骤 13 Verify image | `docker run ... - <<PY` 缺少 `-i` → python 收到空 stdin，断言**静默通过**；随后 `pip check` 因 basic-pitch 声明 TF 而失败 | 加 `-i` 并校验探针输出非空；`pip check` 精确放行 basic-pitch→tensorflow 一条，其余仍失败 |
| `45819026067` | — | — | ✅ 全绿 |

> 第 3 条尤其关键：一个"静默通过"的门禁比失败的门禁更危险。这也是为什么
> `verify-image.sh` 现在会检查探针是否真的产出了 JSON。

## 5. 已知问题

| 项 | 说明 |
| --- | --- |
| 镜像内以 root 运行 | `image_uid: 0`。Railway 卷默认 root 拥有，贸然改非 root 可能导致 `/data` 不可写；C.2.2 评估 |
| 精确镜像大小 | 在产物 `docker-verification/image-info.txt`，本机无 GitHub 凭据无法读取（HTTP 401），未编造数值 |
| 冷构建耗时 | 本次 28 s 是复用 gha 层缓存；首次冷构建（run 2）在 2 分钟内失败于 COPY，未得到完整冷构建时长 |

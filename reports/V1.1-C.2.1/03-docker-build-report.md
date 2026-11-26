# V1.1-C.2.1 · 03 Docker 构建报告

> **Docker Build: NOT EXECUTED**（本机无 Docker Engine / CLI / WSL）

---

## 1. 状态

| 项 | 值 |
| --- | --- |
| 构建命令（CI 将执行） | `docker build -f backend/Dockerfile -t pocketscore-ai:c2-verify .` |
| 构建上下文 | 仓库根（已加 `.dockerignore`，< 50 MB） |
| Dockerfile | `backend/Dockerfile` |
| 本机构建 | ⛔ 未执行 |
| 镜像大小 | ⛔ 未知 |
| 镜像依赖检查 | ⛔ 未执行（由 CI 的 `verify-image.sh` 执行） |

**不会**把"读了一遍 Dockerfile"当作构建成功。

## 2. CI 上会被强制检查的内容

`scripts/docker/verify-image.sh`（工作流第 11 步）会对镜像做容器内断言：

| 检查 | 失败条件 |
| --- | --- |
| Python 版本 | < 3.10 |
| `onnxruntime` | 缺失 |
| `basic_pitch` | 缺失 |
| **TensorFlow** | **存在即失败**（膨胀 + 后端漂移） |
| `nmp.onnx` | 文件缺失 |
| FFmpeg | `imageio_ffmpeg.get_ffmpeg_exe()` 不存在 |
| 前端 dist | `/app/frontend/dist/index.html` 缺失 |
| 应用导入 | `app.main` / `model_manager` / `inference_limiter` 任一导入失败 |
| `pip check` | 依赖不一致 |
| 镜像内容 | `/app/.env`、`.git`、`*.map`、私钥 → 失败 |

输出 `docker-verification/build-info.json`（Python / 依赖版本 / `tensorflow_present`）、
`image-info.txt`（镜像 Id、大小、Top 12 层）。

## 3. 预期结果（不是实测，标记为预测）

| 指标 | 预测 | 依据 |
| --- | --- | --- |
| 镜像大小 | 1.2–1.8 GB | 无 TF；onnxruntime + librosa + numpy + 前端 0.4 MB |
| 构建耗时（冷） | 6–12 分钟 | pip 安装 librosa/numba/onnxruntime；使用 gha 缓存后 2–4 分钟 |
| Python | 3.11.x | `python:3.11-slim` |
| 推理后端 | onnxruntime CPU | `--no-deps` + 显式 `nmp.onnx` |
| TF | 不存在 | 构建期断言 + 镜像检查双保险 |

若实际超出上述范围，报告将改为实测值并分析原因（不允许为了缩小镜像删除运行依赖）。

## 4. 已知风险

| 风险 | 说明 |
| --- | --- |
| `requirements.txt` 新增的 `scikit-learn` / `mir-eval` / `resampy` 与 py3.11 wheel 兼容性 | 均有 cp311 wheel；CI 会以实际安装结果为准 |
| `--no-deps` 安装可能缺少某个隐式依赖 | 由 `import basic_pitch` + 真实推理双重验证；缺依赖会直接失败而不是静默降级 |
| 前端 dist 未生成导致 COPY 失败 | 工作流第 7 步先断言 `index.html` 存在 |

## 5. 关闭条件

在 GitHub Actions 上出现一次绿色 `docker-verify` 运行，且产物中：

- `build-info.json.tensorflow_present == false`
- `image-info.txt` 有镜像大小
- `verify-image` 步骤输出 `IMAGE VERIFY OK`

即视为本报告通过。当前不具备该证据。

# V1.1-C.2.1 · 02 Docker 构建前检查

- **日期**：2026-11-26
- **目的**：在写 CI 之前，先弄清真实构建流程与三类会被 CI 放大的问题（上下文、依赖、模型后端）

---

## 1. 构建上下文（发现 1.7 GB 浪费）

| 目录 | 大小 | 是否应进入镜像 |
| --- | --- | --- |
| `.git` | 210 MB | ❌ |
| `.playwright` | 743 MB | ❌ |
| `.npm-cache` | 299 MB | ❌ |
| `.pip-cache` | 265 MB | ❌ |
| `node_modules`（根） | 41 MB | ❌ |
| `frontend/node_modules` | 154 MB | ❌ |

**实测**：仓库原本**没有 `.dockerignore`**。`docker build -f backend/Dockerfile .` 会把上述
约 **1.7 GB** 全部发给 daemon（CI 上每次构建都付一次），并且存在把 `.env`、`*.p8`
误 COPY 进镜像的风险。

**修复**：新增 `.dockerignore`，排除 VCS、缓存、node_modules、`.env*`（保留 `.env.example`）、
密钥、数据库、测试产物、docs/reports/tests/scripts。上下文降到 **< 50 MB**。

## 2. 前端产物如何进入镜像

`backend/Dockerfile` 有 `COPY frontend/dist ./frontend/dist`。

| 问题 | 结论 |
| --- | --- |
| `frontend/dist` 在仓库中吗？ | ❌ 未跟踪（`.gitignore`）且刚清理时不存在 |
| CI 必须先构建吗？ | ✅ 必须先 `npm ci && npm run build`，否则 `COPY` 直接失败 |
| 是否有重复构建？ | 只构建一次：CI 构建 → Dockerfile COPY，Dockerfile 内不再跑 node |
| 锁文件安装 | ✅ CI 用 `npm ci`（`frontend/package-lock.json` 存在） |

## 3. Python 依赖（发现 TensorFlow 会被意外拉入）

### 3.1 平台标记实测

```text
$ python -c "import importlib.metadata as md; print(md.distribution('basic-pitch').requires)"
librosa>=0.8.0, mir-eval>=0.6, numpy>=1.18, pretty-midi>=0.2.9,
resampy<0.4.3,>=0.2.2, scikit-learn, scipy>=1.4.1, typing-extensions,
tensorflow<2.15.1,>=2.4.1 ; platform_system != "Darwin" and python_version >= "3.11"
coremltools ; platform_system == "Darwin"
tensorflow-macos... ; platform_system == "Darwin" and python_version > "3.11"
tflite-runtime ; platform_system == "Linux" and python_version < "3.11"
onnxruntime ; platform_system == "Windows" and python_version < "3.11"
```

**结论**：镜像基础是 `python:3.11-slim`（Linux）→ 命中第一条标记 →
`pip install basic-pitch` 会安装 **TensorFlow（约 600 MB + 依赖）**，
而本项目跑的是 ONNX 图。C.1 预测的"镜像膨胀"在这里被证实为**必然发生**。

### 3.2 更深一层：默认模型后端会被 TF 抢走

`basic_pitch/__init__.py` 的选择顺序：

```python
if TF_PRESENT:      _default_model_type = tf
elif CT_PRESENT:    _default_model_type = coreml
elif TFLITE_PRESENT: _default_model_type = tflite
elif ONNX_PRESENT:  _default_model_type = onnx
ICASSP_2022_MODEL_PATH = .../_default_model_type
```

即：一旦容器里装了 TensorFlow，`ICASSP_2022_MODEL_PATH` 会指向 TF SavedModel，
**推理后端会从 ONNX 静默切到 TensorFlow** —— 与我们声称的运行时、以及 V1.1-A 的
准确率基线都不是同一个东西。

### 3.3 修复（两项，互相独立）

1. **依赖**：把 `basic-pitch` 移出 `requirements.txt`，单独放 `requirements-model.txt`；
   Dockerfile 用 `pip install --no-deps -r requirements-model.txt`，
   并把它的非 TF 依赖闭包（`mir-eval`、`resampy<0.4.3`、`scikit-learn`、`scipy`、
   `typing-extensions`）显式写进 `requirements.txt`。
   构建期断言：`assert find_spec('tensorflow') is None`。
2. **代码**：`model_manager._resolve_model_path()` 显式指向 wheel 里的
   `saved_models/icassp_2022/nmp.onnx`（实测存在，230 444 字节），
   仅在缺失时回退到 `ICASSP_2022_MODEL_PATH` 并告警。

本机验证：`_resolve_model_path()` → `.../nmp.onnx`，`exist=True`；
`tests/test_model_manager.py` 7 项与 `test_note_accuracy.py` 全部通过。

## 4. 模型与 FFmpeg 资源

| 资源 | 检查结果 |
| --- | --- |
| `nmp.onnx` | ✅ 230 444 字节（wheel 内） |
| `nmp.tflite` | 204 448 字节（不使用） |
| `nmp`（TF SavedModel 目录） | 存在，但采用 `--no-deps` 后不会被选中 |
| FFmpeg | wheel `imageio-ffmpeg` 提供；`resolve_ffmpeg()` 顺序：env → PATH → 捆绑 |
| libsndfile | Dockerfile 已 `apt-get install libsndfile1` |

## 5. 构建命令与上下文

```bash
docker build -f backend/Dockerfile .        # context = 仓库根（需要 frontend/dist）
```

Dockerfile 内 `COPY backend/... frontend/dist ...` 均相对仓库根，与上下文一致，
**不需要**修改 COPY 路径。

## 6. 结论

| 项 | 修复前 | 修复后 |
| --- | --- | --- |
| 构建上下文 | ~1.7 GB | < 50 MB（`.dockerignore`） |
| 容器内 TF | 会被安装（~600 MB） | 不会安装（`--no-deps` + 构建期断言） |
| 推理后端 | 由"装了什么"决定 | 显式 `nmp.onnx`，确定 |
| dist 依赖 | 无 CI 保证 | CI 先构建并断言 `index.html` 存在 |

# V1.1-C.2.1 · 05 真实 AI 扒谱报告

> **容器内真实推理：EXECUTED ✅**（GitHub Actions run `45819026067`，步骤 20，14 s）

---

## 1. 执行内容

工作流在容器上执行 `scripts/docker/verify-transcription.py`：

1. `POST /api/v1/audio/upload`（`tests/fixtures/melody.wav`，multipart）
2. `POST /api/v1/transcription/jobs`
3. `POST /api/v1/transcription/jobs/{id}/run`（503 时退避重试，最多 3 次）
4. `GET /api/v1/documents/{id}` → 逐音符校验
5. `GET /api/v1/notation/{id}/both` → 网格谱与数字谱都必须有音符

## 2. 结果

| 项 | 值 |
| --- | --- |
| 步骤状态 | ✅ success（14 s，含上传 + 推理 + 后处理 + 两次谱面读取） |
| 是否真实运行 Basic Pitch | ✅ 是 —— 镜像内 `basic_pitch` + `nmp.onnx` + onnxruntime；无 TensorFlow |
| 音符事件 | 断言 `events_produced > 0` 且 `document.events > 0` → 通过 |
| 音符合法性 | 音高 0–127、起点 ≥ 0、时值 > 0；违规会列在 `problems` 并失败 |
| 谱面 | 网格谱与数字谱两侧均断言 `notes > 0` |
| Mock / 固定 MIDI | ❌ 无（脚本只做 HTTP 调用，不断言具体音符数） |
| 精确音符数量与耗时 | 在产物 `transcription-result.json`（本机 401 无法读取） |

## 3. 同一脚本的本机真实结果（可对照）

在本机对真实服务运行同一脚本（2026-11-26）：

```text
TRANSCRIPTION VERIFY OK: 4 notes, pitches [60, 64, 67, 72] in 2.538 s (model load 3.015 s)
```

说明脚本本身的行为是确定的；容器内只有环境不同（Linux + 镜像依赖）。

## 4. 附加校验

| 检查 | 结果 |
| --- | --- |
| 非法扩展名拒绝 | 步骤 21：`evil.exe` → **415**，断言通过 |
| 上传大小上限 | `POCKETSCORE_MAX_UPLOAD_MB=50` 注入容器 |
| 推理并发 | `POCKETSCORE_MAX_CONCURRENT_INFERENCES=1` |
| 推理超时 | `POCKETSCORE_INFERENCE_TIMEOUT_SECONDS=300` |

## 5. 未覆盖

- 长音频（120 s）在容器内的耗时/内存未测（本地实测 1.13 s / 262 MB 峰值）。
- 并发 2 个作业时 503 的行为由单元测试覆盖，容器内未压测。

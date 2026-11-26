# V1.1-C.2.1 · 05 真实 AI 扒谱报告

- **状态**：验证脚本已在**真实运行的 API**上执行通过（宿主进程），
  **容器内执行**：NOT EXECUTED（CI 未触发）

---

## 1. 验证手段

`scripts/docker/verify-transcription.py`（新增）——只用标准库，对真实 HTTP API 执行：

1. `POST /api/v1/audio/upload`（multipart，真实 WAV）
2. `POST /api/v1/transcription/jobs`
3. `POST /api/v1/transcription/jobs/{id}/run`（遇到 503 会退避重试，最多 3 次）
4. `GET /api/v1/documents/{id}` → 校验每个音符事件
5. `GET /api/v1/notation/{id}/both` → 网格谱/数字谱两侧都必须有音符

**没有任何 mock**、没有硬编码期望音符数；断言只要求"存在真实、结构合法的音符"。

## 2. 本机真实执行结果（2026-11-26）

对 staging 配置启动的真实服务（`MODEL_PRELOAD=true`，端口 8200）执行：

```text
TRANSCRIPTION VERIFY OK: 4 notes, pitches [60, 64, 67, 72] in 2.538 s (model load 3.015 s)
```

产物摘录（`.run/c21-transcription.json`）：

```json
{
  "state": "completed",
  "events_reported": 4,
  "document_events": 4,
  "distinct_pitches": [60, 64, 67, 72],
  "problems": [],
  "analysis": { "inference_seconds": 0.106, "queue_wait_seconds": 0.0 },
  "pipeline": { "raw_notes": 6, "final_notes": 4, "removed_harmonic": 0, "split_extra": 0 },
  "notation_http": 200,
  "grid_notes": 3,
  "jianpu_notes": 4
}
```

| 校验项 | 结果 |
| --- | --- |
| 任务状态 | `completed` |
| 事件数 | 4（> 0） |
| 音高范围 | 60/64/67/72，均在 0–127 |
| 起点/时值 | 全部合法（`problems: []`） |
| 网格谱/数字谱 | 3 / 4 个音符（同一文档，两种表示） |
| 真实模型 | `basic_pitch` + `nmp.onnx`（ONNX Runtime） |

> 注：`grid_notes=3` 而 `jianpu_notes=4`，因为网格谱把同一格内的同时音符计为一个格子；
> 两者都大于 0，断言成立。这是本项目既有表示差异，不是缺陷。

## 3. 音频样本

| 项 | 值 |
| --- | --- |
| 路径 | `tests/fixtures/melody.wav` |
| 格式 | WAV / PCM 单声道 |
| 大小 | 77.6 KB |
| 时长 | 约 1.6 s |
| 用途 | 仓库内公开测试素材，无版权风险 |

## 4. 容器内执行（待 CI）

工作流第 17–21 步会在容器里执行同一个脚本，并把
`docker-verification/transcription-result.json` 作为产物上传。
除上传源不同（`127.0.0.1:8000` 指容器映射端口）外，逻辑完全一致。

## 5. 结论

| 项 | 状态 |
| --- | --- |
| 验证脚本正确性 | ✅ 真实服务上跑通 |
| Basic Pitch 真实推理 | ✅ 宿主环境 |
| 音符事件 > 0 | ✅ 4 |
| 容器内真实推理 | ⛔ 待 CI |

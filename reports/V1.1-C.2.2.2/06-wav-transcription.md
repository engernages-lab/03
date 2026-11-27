# V1.1-C.2.2.2 · 06 WAV 真实云端扒谱（Phase 6）

- **日期**：2026-11-27
- **脚本**：`scripts/deploy/verify-staging-audio.py`
- **证据**：`artifacts/wav-upload-response.json`、`artifacts/wav-transcription-result.json`

---

## 1. 输入文件（仓库真实素材）

| 项 | 值 |
| --- | --- |
| 文件 | `tests/fixtures/melody.wav` |
| 格式 | WAV PCM |
| 大小 | 79 424 字节 |
| SHA256 | `f4824273ba04a1afbc3946327507097e4af507d0cb675a1c3dcc45fa55ec51f6` |
| 采样率 / 声道 | 22 050 Hz / 1（单声道） |
| 帧数 / 时长 | 39 690 / 1.8 s |

## 2. 上传（真实 HTTPS + 令牌）

| 项 | 值 |
| --- | --- |
| 请求 | `POST /api/v1/audio/upload`（multipart） |
| HTTP | **201** |
| 耗时 | 3.256 s |
| asset_id | `ea92ebce992c` |
| 服务端回报时长 / 大小 | 1.8 s / 79 424 字节 |
| 服务端回报 checksum | 与本地 SHA256 **完全一致** |

## 3. 推理（真实 Basic Pitch）

| 项 | 值 |
| --- | --- |
| Job ID | `job_5d4a57584e51` |
| 状态 | **completed** |
| 任务耗时 | 14.614 s |
| 推理引擎 | `basic_pitch` 0.4.0 + `nmp.onnx`（onnxruntime），镜像内**无 TensorFlow** |
| inference_seconds | 5.267 s |
| model_load_seconds | 2.116 s |
| queue_wait_seconds | 0.0 s |
| 原始音符 → 最终音符 | 6 → 4（后处理 V1.1-A：合并 4） |
| 平均置信度 | 0.6569（低置信 0 个） |

服务端 `analysis.pipeline` 摘要：

```json
{"raw":6,"onsets":8,"removed_harmonic":0,"filtered":0,"split_extra":0,"merged":4,"final":4}
```

## 4. 识别结果（真实音符）

| 项 | 值 |
| --- | --- |
| 音符数 | **4** |
| 音高序列 | `[60, 64, 67, 72]`（C4 / E4 / G4 / C5） |
| 起音序列 | `[0.0, 0.75, 1.5, 2.5]` s |
| 时值序列 | `[0.75, 0.75, 0.75, 0.75]` s |
| 唯一音高数 | 4 |
| 音高范围 | 60–72 |

合理性检查：

| 检查 | 结果 |
| --- | --- |
| 音符数 > 0 | ✅ 4 |
| 音高在 0–127 | ✅ |
| 起音不全部相同 | ✅ 4 个不同起音 |
| 时值 > 0 | ✅ |
| 无 NaN / Infinity | ✅ |
| 文档可解析 | ✅ `GET /api/v1/documents/{id}` 200 |

## 5. MusicDocument

| 项 | 值 |
| --- | --- |
| document_id | `6a0c696a7289`（与 MP3 共用，见 08 号报告；MP3 另建一份） |
| 谱面 | 网格谱 3 音符 + 数字谱 4 音符，`same_document: true` |
| 来源标记 | `source_metadata.provider = basic_pitch`，`recognition_version = 0.4.0` |

## 6. 是否 Mock？

| 检查 | 结论 |
| --- | --- |
| 是否有 `mock`/`fake` 转录器 | ❌ 无 |
| 是否返回预置音符 | ❌ 无（原始 6 音符 → 去重合并 4，符合真实后处理特征） |
| 推理耗时是否非零 | ✅ 5.267 s（真实 ONNX 前向） |
| 音符时值是否全为常数 | 是（0.75 s × 4）——因为测试音频是等长音符的合成旋律，属输入特性，非伪造 |

> 说明：该素材为**合成测试音频**（等长音符），因此"时值全部 0.75 s"是预期结果，
> 不代表对真实音乐录音的识别质量。本报告不把合成音频结果包装成真实歌曲准确率。

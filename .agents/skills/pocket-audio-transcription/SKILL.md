---
name: pocket-audio-transcription
description: PocketScore AI 的 MIDI 解析与音频输入/预处理管线。定义 MIDI→MusicDocument 提取规则、音频格式校验/探测/标准化、以及扒谱作业（TranscriptionJob）状态机与"不伪造AI结果"的边界；改音频或 MIDI 输入前必读。
---

# pocket-audio-transcription

## 1. 职责

处理**输入侧**的一切，不负责音源接入（→ `pocket-music-source`）也不负责谱面（→ grid / jianpu）。

- MIDI：解析 `.mid/.midi`，提取音符起止、时值、音高、力度、轨道、通道、拍号、速度、和弦。
- 音频：接收**用户拥有处理权**的音频文件，做校验、格式检测、时长/采样率/声道检测、标准化、
  波形与频谱特征提取。
- 扒谱作业：记录真实的分析结果与置信度，状态机可追踪。

### 明确的边界（V1.0-A）

- 本阶段交付**输入架构 + 真实可行的信号分析**（节拍/BPM 估计、音高轮廓、起音点）。
- **不得**把单音高检测（如 librosa `piptrack`/`pyin`）包装成"完整歌曲级复音 AI 扒谱"。
- 任何自动生成的事件必须带 `confidence` 与 `method`，前端必须显示"建议/待确认"，
  且不允许默认写入用户文档。
- 没有真实 AI 模型时，接口返回 `NOT_IMPLEMENTED` 或 `REQUIRES_MODEL`，**绝不返回假音符**。

## 2. 核心数据结构

### 2.1 TranscriptionJob

| 字段 | 说明 |
| --- | --- |
| `job_id` / `document_id` | 作业与目标文档 |
| `source` | `local_upload` / `music_source` / `midi` |
| `status` | `queued`/`validating`/`preprocessing`/`analyzing`/`completed`/`failed`/`cancelled` |
| `progress` | 0–100（按阶段推进，不做假动画） |
| `analysis` | `{bpm, beat_times, duration, sample_rate, channels, onsets, pitch_track}` |
| `events_produced` | 生成的候选事件数（0 表示没有可用模型） |
| `confidence` | 0–1，整体置信度 |
| `method` | `librosa.beat` / `librosa.pyin` / `midi_import` / `none` |
| `warnings` / `error` | 人类可读 |

### 2.2 AudioAsset

`{asset_id, filename, stored_path, mime, ext, size_bytes, duration, sample_rate, channels,
bitrate, codec, checksum_sha256, artwork_path, created_at}`

## 3. MIDI 解析规则（`app/services/midi/importer.py`）

1. 用 `mido` 逐轨读取，跳过 `drum` 通道（channel 9）并记录 warning。
2. `note_on(velocity>0)` → `note_off` 之间为音符；**支持重叠**（同音高重复触发时，
   按事件队列配对，取最近的 note_off）。
3. 有 `duration` 的 `note_on`（如 mido 的 `note_on` + `note_off` 双事件）优先用实际时长。
4. 时间换算：以 `tick → 秒 → 拍` 转换；`tempo` 取第一个 `set_tempo`，后续变拍
   记录 warning 并按段落近似。
5. 拍号取第一个 `time_signature`；缺省 4/4。
6. `pretty_midi` 与 `music21` 用于交叉校验（同一文件中音高集合一致性），任一方解析失败
   不阻塞主流程，但写入 warning。
7. 和弦识别：同 `track_id` 且 `|start 差| < EPS` 的事件共享 `chord_id`。
8. 输出：`MusicDocument`（`source_metadata.kind="midi"`），`mapped_key` 由键盘引擎填充。

## 4. 音频预处理（`app/services/audio/`）

| 步骤 | 实现 | 失败行为 |
| --- | --- | --- |
| 校验大小 | `POCKETSCORE_MAX_UPLOAD_MB` | `PAYLOAD_TOO_LARGE` 413 |
| 扩展名白名单 | mp3/wav/flac/m4a/aac/ogg/opus | `UNSUPPORTED_MEDIA_TYPE` 415 |
| 真实格式检测 | FFmpeg `-i` 解析 + `mutagen` 标签 | 不一致时以 FFmpeg 为准并记录 |
| 时长/采样率/声道 | FFmpeg probe → 回退 `soundfile` → 回退 `wave` | 全部失败 `AUDIO_PROBE_FAILED` |
| 解码为单声道 22.05k | FFmpeg → `librosa.load` | 缺 FFmpeg `DEPENDENCY_MISSING` 501 |
| 峰值标准化 | 峰值归一到 -1 dBFS | 全静音返回 `AUDIO_SILENT` |
| 特征 | BPM、beat times、onsets、RMS、频谱质心 | 局部失败降级并写 warning |

**所有预处理结果都落库/落盘，不缓存在内存里跨请求。**

## 5. 输入 / 输出与 API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/v1/midi/inspect` | 只解析元信息（不自建文档） |
| POST | `/api/v1/midi/import` | 解析并创建 `MusicDocument` |
| POST | `/api/v1/audio/upload` | 上传音频，返回 `AudioAsset` |
| POST | `/api/v1/audio/probe` | 仅探测（不落盘） |
| GET | `/api/v1/audio/assets` / `/{id}` | 资产管理 |
| GET | `/api/v1/audio/{id}/waveform?buckets=800` | 真实峰值波形数据 |
| POST | `/api/v1/transcription/jobs` | 创建扒谱作业 |
| GET | `/api/v1/transcription/jobs/{id}` | 查询状态与真实结果 |

## 6. 开发流程

1. 读本 Skill 与 `pocket-music-core`。
2. 修改 `app/services/midi/` 或 `app/services/audio/`。
3. 运行 `pytest tests/test_midi_import.py tests/test_audio_pipeline.py`。
4. 用真实样例（`tests/fixtures/*.mid`、正弦波 WAV）验证，不用硬编码期望值。

## 7. 技术约束

- 文件写入使用 `storage/audio/{sha256[:2]}/{sha256}.{ext}`，天然去重。
- 单文件 ≤ `POCKETSCORE_MAX_UPLOAD_MB`（默认 200MB）。
- 音频分析在 `asyncio.to_thread` 中跑，避免阻塞事件循环。
- 生成候选事件时必须限制上限（≤ 5,000），并标记 `provisional=true`。
- 所有时长/时间单位对外统一：`duration` 秒，事件 `start_time` 拍。

## 8. 禁止事项

- ❌ 把 `librosa.piptrack`/`pyin` 的逐帧结果直接当"音符"写入文档而不标注 method/置信度。
- ❌ 声称完成"歌曲级复音扒谱"而实际只做了节拍/单音轮廓。
- ❌ 用随机数或模板生成"看起来像"的音符。
- ❌ 处理 Spotify 等 `PROVIDER_RESTRICTED` 来源的音频（必须被资格服务拦截）。
- ❌ 未经用户同意上传或长期保留其本地文件。

## 9. 错误处理

| 场景 | 错误码 | HTTP |
| --- | --- | --- |
| 文件过大 | `PAYLOAD_TOO_LARGE` | 413 |
| 扩展名/内容不支持 | `UNSUPPORTED_MEDIA_TYPE` | 415 |
| 无法解析 MIDI | `MIDI_PARSE_ERROR` | 422 |
| MIDI 无音符 | `MIDI_EMPTY` | 422 |
| 音频探测失败 | `AUDIO_PROBE_FAILED` | 422 |
| 音频全静音 | `AUDIO_SILENT` | 422 |
| 缺 FFmpeg | `DEPENDENCY_MISSING` | 501 |
| 作业不存在 | `TRANSCRIPTION_JOB_NOT_FOUND` | 404 |
| 模型不可用 | `REQUIRES_MODEL` | 501 |
| 来源不允许 | `PROVIDER_RESTRICTED` | 403 |

## 10. 测试规范

- `tests/test_midi_import.py`：生成式 MIDI（程序合成二叉树/和弦/跨轨）导入后
  音高、时值、轨道、拍号、速度、和弦分组全部断言；重叠音高配对正确。
- `tests/test_audio_pipeline.py`：合成 440Hz 正弦 WAV（2s / 44.1k / 立体声），
  断言 duration≈2.0、sample_rate=44100、channels=2、标准化后峰值 ≤1.0；
  非法扩展名/超大文件/空音频分别命中对应错误码。
- 所有测试必须能在无网络、无外部服务的环境下通过。

## 11. 验收标准

- [ ] `.mid/.midi` 可导入并生成正确 `MusicDocument`。
- [ ] 音频格式校验、探测、标准化、资产管理可用且错误可读。
- [ ] 波形接口返回真实数据（非随机）。
- [ ] 状态机与真实进度一致，失败有原因。
- [ ] 不存在任何"伪造 AI 识别结果"的代码路径。

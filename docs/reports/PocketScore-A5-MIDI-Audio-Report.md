# PocketScore A.5 — MIDI 与音频输入基础报告

- **版本**：V1.0-A
- **阶段**：A.5 MIDI 解析 + 音频预处理管线
- **结论**：**PASS**（17 项 MIDI 测试 + 15 项音频测试通过）

---

## 1. 交付内容

| 目标 | 状态 | 位置 |
| --- | --- | --- |
| `.mid/.midi` 解析 | ✅ | `services/midi/importer.py` |
| 起点/结束/时值/音高/力度/轨道/通道/拍号/速度/和弦 | ✅ | 同上 |
| 多速度、多拍号、未闭合音符处理 | ✅ 带 warning | 同上 |
| 常见音频格式接收 | ✅ mp3/wav/flac/m4a/aac/ogg/opus | `services/audio/probe.py` |
| 文件验证 / 格式检测 | ✅ 扩展名白名单 + FFmpeg/mutagen 探测 | 同上 |
| 时长 / 采样率 / 声道检测 | ✅ soundfile → FFmpeg → wave 三级回退 | 同上 |
| 音频标准化 | ✅ 峰值归一到 −1 dBFS | 同上 |
| 音频资产管理 | ✅ sha256 去重、封面提取、SQLite 索引 | `services/audio/assets.py` |
| 不把传统分析冒充 AI 扒谱 | ✅ 作业终态为 `analysis_only` 且 `events_produced=0` | `services/transcription.py` |

## 2. MIDI 解析实现要点

1. **时间换算**：先扫描全部轨道构建 tempo map（绝对 tick → 微秒/拍），再用**分段积分**把 tick 换成秒，最后按文档 tempo 换成拍。
   - 这是本项目唯一的 `tick → 秒 → 拍` 实现。
   - 多速度文件：`tempo` 取首个，时间轴仍按真实速度换算，并写 warning。
2. **音符配对**：按 `(channel, pitch)` 维护 FIFO 队列，天然支持同音高重叠；未闭合的 `note_on` 按轨道末尾补齐并 warning。
3. **打击乐**：channel 10（索引 9）跳过并 warning。
4. **拍号**：取首个 `time_signature`；非 4/4 时写入 `TimeSignature`。
5. **和弦**：转换后由 `MusicDocument.reindex()` 按 `(track_id, start_time)` 分组赋 `chord_id`。
6. **字符集**：mido 默认 latin-1；导入时用 `repair_text()` 尝试 UTF-8 还原，导出时以 `charset="utf-8"` 写 `MidiFile`。
7. **导出**：`document_to_midi_bytes()`，同 tick 的 `note_off` 先于 `note_on`，避免重复音被抵消。

## 3. 音频管线

| 阶段 | 实现 | 失败行为 |
| --- | --- | --- |
| 大小校验 | `POCKETSCORE_MAX_UPLOAD_MB`（默认 200） | `PAYLOAD_TOO_LARGE` 413 |
| 扩展名白名单 | 7 种 | `UNSUPPORTED_MEDIA_TYPE` 415 |
| 探测 | soundfile → FFmpeg 解析 stderr → stdlib wave | `AUDIO_PROBE_FAILED` 422 |
| 解码 | FFmpeg → 单声道 22050Hz WAV → soundfile；回退 librosa | `AUDIO_DECODE_FAILED` |
| 标准化 | 峰值 → −1 dBFS，`clip(-1,1)` | 全静音 `AUDIO_SILENT` |
| 波形 | 分桶取 `max(abs())`（真实样本） | 空音频返回空数组 |
| 特征 | `librosa.beat.beat_track` + `onset_detect` + RMS | 局部失败降级并写 warning |
| 存储 | `storage/audio/{sha[:2]}/{sha}.{ext}` | 去重命中直接复用 |

封面提取支持：MP3 `APIC`、FLAC `Picture`、M4A `covr`、OGG `METADATA_BLOCK_PICTURE`。

## 4. 接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/midi/inspect` | 元信息预览（不建文档） |
| POST | `/midi/import?title&artist&layout_id&save` | 解析并入库 |
| GET | `/midi/{document_id}/export` | 导出 `.mid` |
| POST | `/audio/upload` | 上传并入库（去重） |
| POST | `/audio/probe` | 仅探测，不落盘 |
| GET | `/audio/assets` · `/{id}` | 资产列表/详情 |
| DELETE | `/audio/assets/{id}` | 删除（含文件） |
| GET | `/audio/assets/{id}/waveform?buckets` | 真实峰值波形 |
| POST | `/audio/assets/{id}/analyze` | 信号分析（明确标注不是扒谱） |
| GET | `/audio/assets/{id}/stream` | 支持 `Range` 的流（206） |

## 5. 测试证据

```text
$ .\.venv\Scripts\python.exe -m pytest tests/test_midi_import.py -q
.................                            (17 passed)

$ .\.venv\Scripts\python.exe -m pytest tests/test_audio_pipeline.py -q
...............                              (15 passed)
```

关键断言：

- 合成 MIDI（120 BPM，4 拍音）→ `duration == 2.0s`，`start_time/duration` 转拍正确。
- 60 BPM 文件 → 1 拍音时值 1.0s，证明 tempo map 生效。
- 重叠同音高两个音符 → 解析出 2 个音符、各 1.0s。
- 多轨 + 中文轨名（`声部1`）→ 2 条轨道且名称正确（UTF-8 修复生效）。
- 坏文件 → `MIDI_PARSE_ERROR`；空文件 → `MIDI_EMPTY`。
- 导出后再解析：3 个音高与速度保持一致；休止符不导出。
- 合成 2s/44.1k/立体声 WAV → 探测 `duration≈2.0`、`sample_rate=44100`、`channels=2`。
- 解码 → 单声道 22050；标准化峰值 = 10^(−1/20)；静音输入 `AUDIO_SILENT`。
- 波形 600 桶、值域 [0,1]、最大 > 0.1（真实信号）。
- API：上传去重（同字节同 asset_id）、Range 请求返回 206 且长度精确 1024 字节、删除后 404。

## 6. 已知问题

| 问题 | 影响 | 处理 |
| --- | --- | --- |
| 系统 PATH 无 ffmpeg | — | 由 `imageio-ffmpeg` 提供内置二进制（探测到 4.2.2） |
| 多速度 MIDI 仅记录首个 tempo 为文档速度 | 复合拍号曲子时值近似 | 时间轴按真实 tempo map 换算，已写 warning |
| mido 1.3 无 `set_charset` API | 需私有属性 | 改为 `MidiFile(charset="utf-8")` + 导入侧 mojibake 修复 |
| 无内置扒谱模型 | 不产音符 | 作业标记 `analysis_only` + `REQUIRES_MODEL`，绝不伪造 |

## 7. 验收

- [x] `.mid/.midi` 可导入并生成正确 MusicDocument
- [x] 音频格式校验、探测、标准化、资产管理可用且错误可读
- [x] 波形接口返回真实数据
- [x] 不存在伪造 AI 识别结果的代码路径（`test_models_endpoint_is_honest` 与 `test_job_runs_and_produces_analysis_not_notes` 双重断言）

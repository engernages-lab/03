# A.10 · MusicDocument 集成报告

## 1. 契约扩展（向后兼容，`schema_version` 仍为 1）

| 位置 | 新增字段 | 类型 | 说明 |
| --- | --- | --- | --- |
| `NoteEvent` | `confidence` | `Optional[float] 0..1` | 模型置信度，手写/MIDI 事件为 `None` |
| `SourceMetadata` | `recognition_model` | `Optional[str]` | 例：`basic_pitch` |
| `SourceMetadata` | `recognition_version` | `Optional[str]` | 例：`0.4.0` |
| `SourceMetadata` | `source_audio_asset_id` | `Optional[str]` | 溯源到 `AudioAsset` |

均为可选字段且带默认值，旧文档与旧客户端**不需要迁移**即可通过校验。

## 2. 音符写入规则

`app/services/audio/note_extraction.build_document()`：

| 字段 | 来源 |
| --- | --- |
| `pitch` | 模型输出的 MIDI 音高（0..127） |
| `start_time` | `seconds_to_beats(model_start, tempo)` → 量化到 1/16 拍 |
| `duration` | `seconds_to_beats(end-start, tempo)` → 量化，并裁剪到小节内 |
| `velocity` | `round(amplitude × 127)`，钳制 1..127 |
| `confidence` | `round(amplitude, 4)` |
| `track_id` | 单一轨 `t1`（"扒谱旋律"，instrument=piano） |
| `measure` / `beat` | `locate_beat()` 从 start_time 推导 |
| `chord_id` | `_assign_chords()`：起点差 ≤ 1/8 拍的事件共享一个 chord |
| `mapped_key` | `reindex()` → `KeyboardMappingEngine` 按当前布局填充 |

文档级字段：

| 字段 | 来源 |
| --- | --- |
| `tempo` | 信号分析 `bpm`（缺失时 120），钳制 20..300 |
| `time_signature` | 默认 4/4（模型不输出拍号） |
| `key_signature` | 默认 `C`（模型不输出调号） |
| `duration` | 引擎按 `beats_to_seconds(max_end_beat)` 计算（秒） |
| `source_metadata.kind` | `"transcription"` |
| `source_metadata.notes` | `"由 Basic Pitch 0.4.0 识别"` |

## 3. 两条输入路径进入同一份文档

```
音频 → FFmpeg 解码 → Basic Pitch → build_document() ─┐
                                                    ├→ MusicDocument（唯一真源）
MIDI → mido 解析 → importer.build_document() ───────┘
                                                    ↓
                            格子谱 / 数字谱 / 键盘映射 / 播放 / 导出
```

两条路径**分别有独立测试与独立 E2E**，互不冒充（`test_note_accuracy.py` vs `test_midi_import.py`）。

## 4. 一致性保证

- 两种谱面都由 `reindex()` 后从同一文档编译，不存在第二份音符数据。
- 导出图片（A.10-S）也读取 `/notation/{id}/both` 的编译结果，不重新解析文档。
- 新增测试 `test_document_conversion_preserves_musical_data` 断言：
  - 事件数 == 模型输出数
  - 每个事件有 pitch / duration / confidence / measure
  - 起点落在 1/16 网格上
  - `source_metadata.recognition_model == "basic_pitch"`

## 5. 兼容性验证

```text
$ python -m pytest tests/test_music_document.py tests/test_documents_api.py -q
49 passed
```

旧文档（无 confidence / recognition_*）仍可读写；序列化往返不变。

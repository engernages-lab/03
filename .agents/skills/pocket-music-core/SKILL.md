---
name: pocket-music-core
description: PocketScore AI 的统一音乐数据契约。定义 MusicDocument、Track、NoteEvent、时间轴与序列化/校验/版本兼容规则；任何修改音符结构的开发都必须先读本 Skill。
---

# pocket-music-core

## 1. 职责

`pocket-music-core` 是 PocketScore AI 的**唯一音符数据来源**。它负责：

- 定义 `MusicDocument` / `MusicTrack` / `NoteEvent` / `TimeSignature` / `KeySignature`。
- 定义时间单位、拍号换算、小节与拍位的推导规则。
- 提供 JSON 序列化、反序列化、数据校验、版本兼容与错误恢复。
- 提供不可变编辑原语（增删改音符、移调、量化、合并轨道），供上层谱面引擎调用。

它**不负责**：音高到键位的映射（→ `pocket-keyboard-mapping`）、谱面渲染（→
`pocket-grid-notation` / `pocket-jianpu-notation`）、音频解析（→
`pocket-audio-transcription`）、音源接入（→ `pocket-music-source`）。

## 2. 核心数据结构

### 2.1 MusicDocument（`app/schemas/music_document.py`）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `schema_version` | `int` | 文档结构版本，当前 `1`；读取时就地升级 |
| `document_id` | `str` (uuid) | 文档唯一标识 |
| `title` | `str` | 曲名 |
| `artist` | `str` | 艺人 |
| `tempo` | `float` | BPM，范围 20–400 |
| `time_signature` | `{numerator, denominator}` | 拍号，分母限 1/2/4/8/16 |
| `key_signature` | `str` | 调号，如 `C`、`F#m` |
| `duration` | `float` | 总时长（**秒**，由事件与 tempo 推导） |
| `tracks` | `MusicTrack[]` | 至少一条轨道 |
| `events` | `NoteEvent[]` | 扁平事件表，用 `track_id` 归属 |
| `keyboard_layout` | `KeyboardLayout` | 文档内嵌布局快照（自包含） |
| `notation_settings` | `NotationSettings` | 两种谱面的显示/编辑参数 |
| `source_metadata` | `SourceMetadata` | 来源（local/midi/subsonic/apple…）、原始文件名、导入时间 |
| `created_at` / `updated_at` | ISO-8601 UTC | 时间戳 |

### 2.2 NoteEvent

| 字段 | 类型 | 约束 |
| --- | --- | --- |
| `event_id` | `str` | 文档内唯一（uuid4 hex 前 12 位） |
| `pitch` | `int \| null` | MIDI 音高 0–127；`kind="rest"` 时为 `null` |
| `start_time` | `float` | **拍**为单位，≥0 |
| `duration` | `float` | **拍**为单位，>0 |
| `velocity` | `int` | 1–127 |
| `track_id` | `str` | 必须存在于 `tracks` |
| `measure` | `int` | 1 起；由 `start_time` + 拍号推导，保存前重算 |
| `beat` | `float` | 小节内拍位，1 起；同上 |
| `mapped_key` | `str \| null` | 键位 ID；**派生值**，由键盘引擎重算，不参与编辑 |
| `kind` | `"note" \| "rest"` | 休止符是显式事件，保证时值不丢失 |
| `chord_id` | `str \| null` | 同时发声的音符共享，用于和弦渲染与选择 |
| `tie_group` | `str \| null` | 连音线分组 |

### 2.3 时间模型

- **存储单位是拍（beat）**，不是秒。`seconds = beats * 60 / tempo`。
- 小节边界由拍号决定：`beats_per_measure = numerator * 4 / denominator`。
- 浮点比较统一使用 `EPSILON = 1e-6`；量化到 `1/divisions` 网格（divisions 默认 4，
  即 16 分音符）。
- 禁止在不同模块各自实现拍号换算；只能调用 `app/services/music_document/timing.py`。

## 3. 输入 / 输出规范

- 输入：MIDI 导入器产出的事件列表、谱面编辑器的编辑指令、项目文件、API 请求体。
- 输出：`MusicDocument` 实例；`to_dict()` 得到可 JSON 序列化的 dict；
  `MusicDocument.model_validate_json()` 用于反序列化。
- 所有跨模块传递一律用 `MusicDocument`（或其只读视图），禁止传“裸事件数组”。

## 4. 开发流程

1. 读本 Skill 与 `pocket-keyboard-mapping`（`mapped_key` 的归属方）。
2. 修改 `app/schemas/music_document.py` 的模型或 `app/services/music_document/` 的引擎。
3. 若改结构：`schema_version` +1，并在 `migrations.py` 增加升级函数与单测样本。
4. 运行 `pytest tests/test_music_document.py`，再运行全量后端测试。
5. 更新 `docs/architecture/system-overview.md` 中受影响的数据流描述。

## 5. 技术约束

- Pydantic v2 模型；`model_config = ConfigDict(extra="forbid")`（防止拼写错误的字段被静默丢弃）。
- 文档体积上限：50,000 事件；超出返回 `DOCUMENT_TOO_LARGE`。
- `duration` 不允许客户端直接写入最终值，由引擎计算。
- 序列化必须稳定：同一文档两次 `to_dict()` 结果字节一致（键顺序固定、时间戳不刷新）。
- uuid 使用 `uuid4().hex[:12]`，仅保证文档内唯一，不保证全局唯一。

## 6. 禁止事项

- ❌ 在 `MusicDocument` 之外保存音符数据（格子谱/数字谱不得有自己的音符表）。
- ❌ 在事件里保存像素坐标、DOM 尺寸、渲染状态。
- ❌ 用秒作为存储单位，或在两个模块里各写一套 BPM 换算。
- ❌ 变更字段而不升 `schema_version`，或删字段而不写迁移。
- ❌ 让 `mapped_key` 反向影响 `pitch`（改布局绝不能改音高）。

## 7. 错误处理

| 场景 | 错误码 | HTTP | 行为 |
| --- | --- | --- | --- |
| 文档不存在 | `MUSIC_DOCUMENT_NOT_FOUND` | 404 | 返回 id |
| 结构校验失败 | `VALIDATION_ERROR` | 422 | 字段级原因 |
| 未知 `schema_version` | `DOCUMENT_VERSION_UNSUPPORTED` | 422 | 返回文档版本与支持范围 |
| 事件引用不存在的轨道 | `DOCUMENT_TRACK_MISSING` | 422 | 返回 `track_id` |
| 事件重叠不可解析 | `DOCUMENT_EVENT_OVERLAP` | 422 | 返回冲突事件 id 列表 |
| 超过事件上限 | `DOCUMENT_TOO_LARGE` | 413 | 返回实际数量 |

错误恢复：反序列化失败时不允许“部分成功”；要么完整返回文档，要么抛错。
数据库读取到坏 JSON 时记录 `DOCUMENT_CORRUPT` 日志并返回 500，不静默返回空文档。

## 8. 测试规范

- `tests/test_music_document.py`
  - 构造覆盖：单音 / 和弦 / 多轨 / 不同时值 / 休止 / 跨小节 / 重叠音 / 高八度。
  - 往返：`to_dict → parse → to_dict` 字节一致。
  - 校验：非法 pitch、负 start_time、零 duration、未知 track_id 全部报错。
  - 版本：v0 样本升级到 v1 后数据等价。
  - 时间：4/4 与 3/4、6/8 下 measure/beat 推导正确（含跨小节长音）。
- 覆盖率要求：`app/services/music_document/` ≥ 90%。

## 9. 验收标准

- [ ] `MusicDocument` 字段与上表一致，缺一不可。
- [ ] 一份文档可同时驱动格子谱与数字谱，且两谱来自同一事件表。
- [ ] 序列化往返无损，坏数据有明确错误码。
- [ ] 拍号/速度/小节/拍位换算只有一处实现。
- [ ] 全部单元测试通过，无跳过用例。

# PocketScore A.3 — MusicDocument 核心数据引擎报告

- **版本**：V1.0-A
- **阶段**：A.3 统一音乐数据引擎
- **结论**：**PASS**（32 项单元测试 + 16 项 API 测试通过）

---

## 1. 交付内容

| 目标 | 状态 | 实现位置 |
| --- | --- | --- |
| 统一 `MusicDocument` | ✅ | `backend/app/schemas/music_document.py` |
| 必填字段齐备 | ✅ | 见 §2 字段表 |
| 音符事件字段齐备 | ✅ | `NoteEvent` |
| 单音/和弦/多轨/时值/休止/小节/拍号/速度/音高/八度/重叠/时间轴 | ✅ | 引擎 + 测试逐项覆盖 |
| 两种谱面同源 | ✅ | 谱面引擎只读文档（A.6/A.7） |
| JSON 序列化 / 反序列化 | ✅ | `serialization.py` |
| 数据校验 | ✅ | Pydantic v2 + 交叉引用校验 |
| 版本兼容 | ✅ | `schema_version` + v0→v1 迁移 |
| 错误恢复 | ✅ | 类型化错误码，拒绝“部分成功” |

## 2. 数据契约

### 2.1 MusicDocument

`schema_version` · `document_id` · `title` · `artist` · `tempo` · `time_signature{numerator,denominator}` ·
`key_signature` · `duration`（秒，派生）· `tracks[]` · `events[]` · `keyboard_layout`（内嵌快照）·
`notation_settings{grid,jianpu}` · `source_metadata` · `created_at` · `updated_at`

### 2.2 NoteEvent

`event_id` · `pitch`（MIDI 0–127，休止为 null）· `start_time`（**拍**）· `duration`（**拍**）·
`velocity`（1–127）· `track_id` · `measure`（派生）· `beat`（派生）· `mapped_key`（派生）·
`kind`（`note`/`rest`）· `chord_id` · `tie_group`

### 2.3 时间模型（唯一实现：`services/music_document/timing.py`）

- 存储单位是**拍**，`秒 = 拍 × 60 / tempo`。
- `beats_per_measure = numerator × 4 / denominator`。
- `locate_beat()` 返回 1 起的小节号与小节内拍位；边界用 `EPSILON=1e-6` 修正。
- `quantize(value, divisions)` 吸附到 `1/divisions` 网格。
- 全项目仅此一处做拍号算术，格子谱/数字谱/MIDI 导入均调用它。

## 3. 不变量与校验

| 规则 | 违反时 |
| --- | --- |
| 至少一条轨道 | `ValueError: a document must contain at least one track` |
| `track_id` 唯一且事件必须引用已存在轨道 | 校验失败（422） |
| `event_id` 文档内唯一 | 校验失败 |
| `kind=note` 必须有 pitch；`kind=rest` 必须无 pitch | 校验失败 |
| `start_time ≥ 0`、`duration > 0` | `INVALID_EVENT_TIME` |
| 事件数 ≤ 50,000 | `DOCUMENT_TOO_LARGE`（413） |
| 调号必须属于受支持集合 | `unsupported key_signature` |

`reindex(document)` 统一刷新 `measure`/`beat`/`duration`/`mapped_key`/和弦分组，并稳定排序事件。

## 4. 编辑原语（`services/music_document/engine.py`）

`add_event` · `update_event` · `delete_event` · `move_event_to_key` · `transpose`（MIDI 越界钳制）·
`quantize_events` · `set_tempo` · `set_time_signature` · `add_track` · `delete_track` ·
`find_overlaps` · `validate_document` · `track_summary`

编辑统一收敛于此，任何 mutate 后自动 `reindex()`，因此 `measure/beat` 不会过期。

## 5. 数据库

三张规范化表（不存在“文档 JSON + 事件表”双份数据）：

| 表 | 关键列 / 索引 |
| --- | --- |
| `music_documents` | `id` PK、标题、艺人、tempo、拍号、调号、duration、`keyboard_layout_json`、`notation_settings_json`、`source_metadata_json`；索引 `title`、`updated_at` |
| `music_tracks` | `document_id` FK(CASCADE)、`track_id`、名称、乐器、通道、顺序、颜色；唯一 `(document_id, track_id)` |
| `music_events` | `document_id` FK、`event_id`、`track_id`、pitch、start_time、duration、velocity、measure、beat、mapped_key、kind、chord_id、tie_group；唯一 `(document_id,event_id)`；索引 `(document_id,start_time)`、`(document_id,pitch)`、`(document_id,track_id)` |

`save_document()` 在同一事务内替换子表；`load_document()` 反向装配并校验，坏 JSON 抛 `DOCUMENT_CORRUPT`(500)。

## 6. 接口（`/api/v1/documents`）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/documents?q&limit&offset` | 列表（摘要） |
| POST | `/documents` | 新建空文档 |
| POST | `/documents/import` | 导入 JSON（总是分配新 id） |
| GET | `/documents/{id}` | 完整文档 |
| PUT | `/documents/{id}` | 整体替换（撤销/重做使用） |
| PATCH | `/documents/{id}` | 元数据 / 布局 / 谱面设置 |
| DELETE | `/documents/{id}` | 删除 |
| POST | `/documents/{id}/duplicate` | 复制（新文档 id + 新事件 id） |
| POST | `/documents/{id}/edits` | 批量编辑（原子） |
| GET | `/documents/{id}/summary` | 摘要 + 校验发现 + 轨道统计 |
| GET | `/documents/{id}/export` | 导出 JSON / `.pocketscore` |

## 7. 测试证据

```text
$ .\.venv\Scripts\python.exe -m pytest tests/test_music_document.py -q
................................            (32 passed)

$ .\.venv\Scripts\python.exe -m pytest tests/test_documents_api.py -q
.................                           (17 passed)
```

覆盖要点：

- 4/4、3/4、6/8 下小节与拍位推导（含 3.5 拍跨小节长音）。
- tempo 变化只影响 `duration`，不改事件相对位置。
- 和弦：同起点音符共享 `chord_id`，单音 `chord_id=None`。
- 休止符是显式事件（`pitch=None, kind="rest"`），时值不丢失。
- 多轨 + 不同时值；八度音在单八度半音阶布局下正确判为“超出键盘”。
- 重叠检测：同轨同音高重叠返回 `overlap_beats`。
- 序列化：`to_json → from_json → to_json` **字节一致**。
- 迁移：v0（`time`/`length`）→ v1（`start_time`/`duration`/`kind`）成功。
- 错误：非法 pitch、未知调号、未知版本、坏 JSON 全部有明确错误码。

## 8. 已知问题

| 问题 | 影响 | 处理 |
| --- | --- | --- |
| `updated_at` 由 ORM `onupdate` 维护，内存对象不自动刷新 | 导出前需重新读取 | 编辑接口返回从库读回的结果 |
| 序列化稳定性依赖 Pydantic 字段声明顺序 | 字段重排会改变字节输出 | 视为契约，字段只追加不重排 |
| SQLite 单写者 | 高并发写入需排队 | V1.0-A 单用户场景可接受，已留 Alembic 迁移能力 |

## 9. 未完成 / 下一阶段

- 多段速度（tempo map）暂只支持单一 tempo（MIDI 导入会给出 warning）。
- 下一阶段：A.4 键盘映射引擎直接消费 `mapped_key` 派生规则。

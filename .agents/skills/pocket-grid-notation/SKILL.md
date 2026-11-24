---
name: pocket-grid-notation
description: PocketScore AI 的格子谱引擎。定义 GridViewModel、小节/时值/和弦/休止符的格子化规则、键位行映射与编辑指令；开发或修改格子谱渲染与编辑前必读。
---

# pocket-grid-notation

## 1. 职责

把 `MusicDocument` + `KeyboardLayout` + `GridSettings` 编译成**格子谱视图模型**，
使前端可以纯渲染（不含音乐逻辑）。同时定义格子谱上的编辑指令如何回写到
`MusicDocument`。

- 唯一实现：`app/services/notation/grid.py`。
- 前端只消费 `GridViewModel`，不计算音高、小节、时值。

## 2. 核心数据结构

### 2.1 GridViewModel

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `document_id` | `str` | 来源文档 |
| `layout_id` / `layout_name` | `str` | 使用的键盘布局 |
| `tempo` / `time_signature` / `key_signature` | 同文档 | 谱面头部信息 |
| `divisions` | `int` | 每拍切分数（默认 4 → 16 分音符网格） |
| `measures` | `MeasureCell[][]` | 按小节分组的列 |
| `rows` | `GridRow[]` | 每个键一行（顺序 = `KeyDefinition.index`） |
| `unmapped` | `UnmappedNote[]` | 超出键盘范围的音符（单独提示，不丢弃） |
| `stats` | `{notes, rests, chords, measures}` | 谱面统计 |

### 2.2 GridRow

`{key_id, label, index, color, pitch_or_offset, cells: GridCell[]}`

### 2.3 GridCell

| 字段 | 说明 |
| --- | --- |
| `measure` | 小节号（1 起） |
| `slot` | 该小节内第几个网格位（0 起） |
| `start_time` / `duration` | 拍 |
| `state` | `"empty" \| "note" \| "rest" \| "continuation"` |
| `event_id` / `chord_id` | 关联事件（`empty` 为 null） |
| `span` | 占用的格子数（音符宽度） |
| `velocity` | 力度（用于透明度） |
| `label` / `color` | 冗余自布局，便于前端直接绘制 |
| `selected` | 由前端本地管理，后端恒为 `false` |

### 2.4 编译规则

1. `beats_per_measure = numerator * 4 / denominator`。
2. `slots_per_measure = round(beats_per_measure * divisions)`。
3. 事件起点 `slot = round((start_time - measure_start) * divisions)`；
   `span = max(1, round(duration * divisions))`。
4. 一个音符占 `span` 个格子：第一格 `state="note"`，其后为 `"continuation"`。
5. 休止符 `kind="rest"` 渲染为 `state="rest"`，占位符按 `span` 展开。
6. 同一 `chord_id` 的事件在同一列、不同行同时显示（和弦在格子谱中天然并列）。
7. `mapped_key` 为空的事件进入 `unmapped[]`，并在 `stats` 中计数。
8. 跨小节长音：按小节切分，后续小节对应格子仍标 `continuation`。

## 3. 输入 / 输出

- 输入：`MusicDocument`、`KeyboardLayout`、`GridSettings{divisions, show_key_names, show_velocity, color_mode}`。
- 输出：`GridViewModel`（JSON）。
- API：`GET /api/v1/notation/{document_id}/grid?layout_id=...&divisions=...`
- 编辑 API 通过通用文档编辑端点实现（见 §4），保证两种谱面走同一条写入路径。

## 4. 编辑指令（与数字谱共用）

```json
{ "op": "add_note",    "pitch": 64, "start_time": 4.0, "duration": 1.0, "track_id": "t1" }
{ "op": "update_note", "event_id": "ab12...", "patch": { "start_time": 4.5, "duration": 0.5 } }
{ "op": "delete_note", "event_id": "ab12..." }
{ "op": "move_note",   "event_id": "ab12...", "from_key": "k3", "to_key": "k5" }
```

`move_note` 由后端把目标键位换算成音高再写回 —— 前端**不得**自行换算。
所有编辑都落在 `MusicDocument` 上，随后两种谱面重新编译。

## 5. 开发流程

1. 读本 Skill、`pocket-music-core`、`pocket-keyboard-mapping`。
2. 修改 `app/services/notation/grid.py`。
3. 运行 `pytest tests/test_grid_notation.py` + `tests/test_notation_sync.py`。
4. 前端改动后运行 `npm run test` 并手工验证 `/scores/{id}` 页面。

## 6. 技术约束

- 编译是纯函数：相同输入必须得到相同输出（无时间、无随机、无全局状态）。
- 单谱面格子总数 ≤ 20,000（`slots_per_measure × measures × rows`），超出返回
  `NOTATION_TOO_LARGE`，前端提示缩小范围。
- 禁止在视图模型里出现像素值；尺寸由前端决定。
- 每个音符在 `rows` 中最多出现一次（不能同时命中两个键）。

## 7. 禁止事项

- ❌ 在格子谱引擎里重新推导音高→键位（必须调用 `pocket-keyboard-mapping`）。
- ❌ 丢弃 `unmapped` 音符或悄悄改其 pitch。
- ❌ 把颜色/文案硬编码在引擎里（来源必须是布局）。
- ❌ 为格子谱单独维护一份可编辑音符数组。

## 8. 错误处理

| 场景 | 错误码 | HTTP |
| --- | --- | --- |
| 文档不存在 | `MUSIC_DOCUMENT_NOT_FOUND` | 404 |
| 布局不存在 | `KEYBOARD_LAYOUT_NOT_FOUND` | 404 |
| `divisions` 不在 1/2/4/8/16 | `INVALID_DIVISIONS` | 422 |
| 谱面过大 | `NOTATION_TOO_LARGE` | 413 |
| 编辑引用不存在的事件 | `EVENT_NOT_FOUND` | 404 |
| 编辑产生负时间/零时值 | `INVALID_EVENT_TIME` | 422 |

## 9. 测试规范

- `tests/test_grid_notation.py`
  - 4/4、division=4：一个整拍音符占 4 格、半拍占 2 格、16 分占 1 格。
  - 3/4 与 6/8 的小节格数正确。
  - 和弦：3 个同 `chord_id` 音符出现在同一列的 3 个行。
  - 休止符：`state="rest"` 且不被省略。
  - 超范围音符进入 `unmapped` 且 `stats.notes` 与文档一致。
  - 跨小节长音：跨入下一小节后 `state="continuation"`。
  - 确定性：连续两次编译结果深度相等。
  - 与键盘布局联动：切换布局后 `rows` 顺序与 `label` 随之变化。

## 10. 验收标准

- [ ] 格子谱完整反映小节、拍号、时值、休止、和弦、键位名称、颜色。
- [ ] 切换键盘布局后格子谱行与键名同步更新。
- [ ] 支持选择、增加、删除、移动音符，且全部写回 `MusicDocument`。
- [ ] 缩放与滚动由前端实现，后端只提供稳定视图模型。
- [ ] 导出（SVG/JSON）可用。

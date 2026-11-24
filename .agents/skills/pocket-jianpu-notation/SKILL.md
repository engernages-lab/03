---
name: pocket-jianpu-notation
description: PocketScore AI 的数字谱（简谱）引擎。定义 JianpuViewModel、音高转数字、八度点、时值/附点/连音符号与双格式同步契约；改数字谱或同步逻辑前必读。
---

# pocket-jianpu-notation

## 1. 职责

把 `MusicDocument` 编译成**数字谱（简谱）视图模型**，并保证与格子谱
同源、双向同步。

- 唯一实现：`app/services/notation/jianpu.py`。
- 双格式同步：`app/services/notation/sync.py`（两谱共用同一编辑指令集）。

## 2. 核心数据结构

### 2.1 JianpuViewModel

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `document_id` | `str` | 来源文档 |
| `key_signature` / `tonic` / `mode` | `str` / `int` / `"major"\|"minor"` | 调式决定 1 的绝对音高 |
| `tempo` / `time_signature` | 同文档 | 头部信息 |
| `systems` | `JianpuMeasure[][]` | 按行（system）排版的小节 |
| `measure_lines` | `{measure, start_beat, beats}` | 小节线信息 |
| `key_labels` | `{pitch: label}` | 键位名称（与格子谱一致） |
| `unmapped` | 同格子谱 | 无键位但有音高的音符照常显示数字 |
| `stats` | `{notes, rests, chords, measures, accidentals}` | 统计 |

### 2.2 JianpuNote

| 字段 | 说明 |
| --- | --- |
| `event_id` | 关联事件 |
| `degree` | 1–7；变音为 `#4` / `b7` |
| `accidental` | `null` / `"#"` / `"b"` |
| `octave` | 相对中音区偏移：`-2..+2`（负=下方点，正=上方点） |
| `duration_label` | 简谱时值符号：`""`(四分)、`"_"`(八分)、`"="`(十六分)、`"-"`(二分)、`"—"`(全音符) |
| `dots` | 附点数 0/1/2 |
| `tie` | `"start" \| "stop" \| "continue" \| null` |
| `is_rest` | 休止为 `0` |
| `chord_id` / `chord_degree` | 和弦纵向堆叠信息 |
| `mapped_key` | 键位名（同步展示） |
| `width` | 占用的排版单位（前端按此分配横向空间） |

### 2.3 音高 → 数字（唯一算法）

```
tonic_pc = pitch_class(key_signature 的主音)
scale = 大调 [0,2,4,5,7,9,11] / 小调自然音阶 [0,2,3,5,7,8,10]
rel = (pitch - tonic_pc) mod 12
若 rel 属于音阶 → degree = 音阶中的序号 + 1，accidental = None
否则取最近的音阶音，degree 为该音级，accidental = "#" 或 "b"
octave = floor((pitch - tonic_pc - rel_adjusted) / 12)  相对中音区
```

- 中音区（无点）定义为主音所在八度（默认 `C4` 起）。
- 时值符号由 `duration（拍）` 推导：`4.0→—`、`2.0→-`、`1.0→无`、`0.5→_`、`0.25→=`；
  非整倍数取最接近的合法组合并标记 `dotted`。

## 3. 输入 / 输出

- 输入：`MusicDocument`、`JianpuSettings{show_key_labels, octave_style, max_notes_per_line}`。
- 输出：`JianpuViewModel`。
- API：`GET /api/v1/notation/{document_id}/jianpu?layout_id=...`

## 4. 双格式同步机制

```
        ┌───────────────┐
        │ MusicDocument │  ← 唯一数据源
        └───────┬───────┘
      compile   │   compile
    ┌───────────┴───────────┐
    ▼                       ▼
GridViewModel        JianpuViewModel
    │                       │
    └──── edit op (JSON) ───┘
              │
              ▼
   apply_edit(MusicDocument) → 保存 → 两谱重新编译
```

- 任一谱面的编辑都转成 §4 的编辑指令，经 `POST /api/v1/documents/{id}/edits` 落到文档。
- 不做“局部 Patch 视图模型”的捷径 —— 视图模型永远整体重编译，保证两谱不可能分叉。
- 撤销/重做在前端以**文档快照栈**实现（`zustand` 中保存最近 50 个 `MusicDocument`），
  因为文档是唯一真源，快照即可还原两种谱面。

## 5. 开发流程

1. 读本 Skill、`pocket-music-core`、`pocket-grid-notation`。
2. 修改 `app/services/notation/jianpu.py`（音高→数字）或 `sync.py`（编辑应用）。
3. 运行 `pytest tests/test_jianpu_notation.py tests/test_notation_sync.py`。
4. 前端 `useDocumentEditor` 改动后运行 `npm run test`。

## 6. 技术约束

- 音高→数字只允许在 `jianpu.py` 实现一次；格子谱、MIDI 导出不得自行换算。
- 调号解析支持 12 个大调 + 12 个自然小调；不支持的调号返回
  `UNSUPPORTED_KEY_SIGNATURE`。
- 变音记号最多一个（重升/重降不支持，遇到则降级为最接近的单个变音并记录 warning）。
- 连音（tie）：同音高跨事件且首尾相接（`|start2 - (start1+dur1)| < EPS`）自动识别。

## 7. 禁止事项

- ❌ 数字谱单独保存音符数组或“数字字符串”；数字永远由音高推导。
- ❌ 在渲染层做音高→数字换算。
- ❌ 编辑数字谱时直接改 `degree` 而不改 `pitch`。
- ❌ 两种谱面各自维护撤销栈（必须共用文档快照栈）。

## 8. 错误处理

| 场景 | 错误码 | HTTP |
| --- | --- | --- |
| 文档不存在 | `MUSIC_DOCUMENT_NOT_FOUND` | 404 |
| 调号不支持 | `UNSUPPORTED_KEY_SIGNATURE` | 422 |
| 编辑指令未知 `op` | `UNKNOWN_EDIT_OP` | 422 |
| 编辑后产生非法音高 | `INVALID_PITCH` | 422 |
| 同步冲突（版本不匹配） | `DOCUMENT_VERSION_CONFLICT` | 409 |

## 9. 测试规范

- `tests/test_jianpu_notation.py`
  - C 大调：C4→`1`、D4→`2`、B4→`7`、C5→`1`（上一点）。
  - 升降号：`F#4`→`#4`、`Bb4`→`b7`。
  - 小调：A 小调 A4→`1`。
  - 八度：C3→`1` 下一点、C6→`1` 上两点。
  - 时值：4 拍→`—`、2 拍→`-`、1 拍→无、0.5→`_`、0.25→`=`；附点 1.5 拍→`1.`。
  - 休止：`0` 且时值符号正确。
  - 和弦：同 `chord_id` 的音符堆叠。
- `tests/test_notation_sync.py`
  - 改格子谱 → 数字谱对应音符变化。
  - 改数字谱（音高/时值）→ 格子谱位置变化。
  - 改布局 → 两谱的键位标记都更新，音高序列不变。
  - 撤销/重做 5 步后两谱完全回到初态。

## 10. 验收标准

- [ ] 数字谱正确渲染音高、八度、时值、附点、连音、休止、小节线、拍号、速度、和弦、多轨。
- [ ] 两种谱面任意一侧编辑，另一侧立即同步。
- [ ] 切换键盘布局后两谱键位标记同步，音高不变。
- [ ] 撤销/重做在两种谱面视图上均生效。
- [ ] 全部单元测试通过。

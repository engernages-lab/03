# PocketScore A.6 — 格子谱引擎报告

- **版本**：V1.0-A
- **阶段**：A.6 GridNotationEngine
- **结论**：**PASS**（19 项测试通过，含 SVG 导出）

---

## 1. 交付内容

| 要求 | 状态 | 说明 |
| --- | --- | --- |
| 格子谱绘制 | ✅ | `GridViewModel` + `GridScore.tsx` |
| 小节划分 | ✅ | `measures[]`（start_beat / beats / slots / start_slot） |
| 音符定位 | ✅ | `(row=键位, slot=网格)` |
| 时值显示 | ✅ | `span` = 占格数，尾格 `continuation` |
| 休止符显示 | ✅ | 独立休止轨道 `*rest*` |
| 和弦显示 | ✅ | 同一列不同行 + 共享 `chord_id` |
| 音符颜色 | ✅ | 来自键位 `color` |
| 键位名称 | ✅ | 行标签 = `KeyDefinition.label` |
| 选择/编辑/删除/新增 | ✅ | 点击选中 / 工具栏删除 / 点空格写入 |
| 缩放 | ✅ | 前端 60%–200% |
| 滚动 | ✅ | 容器横纵滚动 |
| 谱面导出 | ✅ | `GET /notation/{id}/grid.svg` |

## 2. 编译规则（`services/notation/grid.py`）

```
slots_per_measure = round(numerator × 4 / denominator × divisions)
slot_start        = round(start_time × divisions)
span              = max(1, round(duration × divisions))
```

- 首格 `state="note"`（或 `"rest"`），其余 `"continuation"`。
- 跨小节长音：切分到后续小节的格子，仍为 `continuation`。
- `mapped_key` 为空 → 进入 `unmapped[]`，**不丢弃、不改音高**，前端单独提示。
- 编译是纯函数：同输入两次编译深度相等（测试断言）。
- 规模保护：格子总数上限 40,000，超出 `NOTATION_TOO_LARGE`(413)。

## 3. 视图模型

`GridViewModel{document_id,title,artist,layout_id,layout_name,tempo,time_signature,key_signature,`
`divisions,slots_per_measure,measures[],rows[],rest_row,unmapped[],stats}`

`GridRow{key_id,label,index,color,pitch,pitch_name,cells[]}` ·
`GridCell{measure,slot,state,start_time,duration,event_id,chord_id,span,velocity,pitch,label,color}`

## 4. 前端渲染

`components/notation/GridScore.tsx`：

- 顶部小节标尺；左侧键位列（色块 + 键名 + 音名）。
- 每格按 `slot % divisions === 0` 区分强弱拍底色。
- 音符块按布局颜色填充，选中时白色描边。
- 点击空格 → 以该行音高在该拍写入 1 拍音符；点击音符 → 选中。
- 只消费后端数据，**不计算音高、小节、时值**。

## 5. 导出

`render_grid_svg(view, cell)` 服务端生成 SVG：标题/艺人/速度/拍号/调号/键盘名、小节线、键位行、音符块、超出范围提示。

## 6. 接口

| 方法 | 路径 |
| --- | --- |
| GET | `/api/v1/notation/{document_id}/grid?divisions&layout_id` |
| GET | `/api/v1/notation/{document_id}/grid.svg?divisions&layout_id&cell` |

## 7. 测试证据

```text
$ .\.venv\Scripts\python.exe -m pytest tests/test_grid_notation.py -q
...................                          (19 passed)
```

覆盖：

- 4/4 → 16 格/小节；3/4 → 12 格；6/8 → 12 格。
- 整拍音符占 4 格（首格 note + 3 continuation），第 5 格为空。
- 二分音符 span=8、十六分音符 span=1。
- 三音和弦落在同一 slot 的 3 行，`stats.chords == 1`。
- 休止符在休止轨道渲染，`stats.rests == 1`；无休止时 `rest_row is None`。
- 3.5 拍起 2 拍长音：slot 14/15 后延续到下一小节 slot 0..5，slot 22 为空。
- 超出布局的 C#4 进入 `unmapped`，且所有格子仍为空。
- 切换十二键布局后 C#4 落在 `k1` 行、`unmapped` 归零。
- 两次编译 `model_dump()` 深度相等。
- SVG 导出：`200`、`image/svg+xml`、包含标题、以 `</svg>` 结束。

## 8. 已知问题

| 问题 | 说明 |
| --- | --- |
| 未实现拖拽调整时值 | 当前通过工具栏「时值 ×2 / ÷2」修改，拖拽编辑器留待 V1.0-B |
| 极大谱面（>40k 格）拒绝编译 | 由 `NOTATION_TOO_LARGE` 明确报错，前端可降低 divisions |
| SVG 为静态快照 | 交互编辑在浏览器内完成，导出用于分享/打印 |

## 9. 验收

- [x] 格子谱完整反映小节、拍号、时值、休止、和弦、键位名称、颜色
- [x] 切换键盘布局后行与键名同步更新
- [x] 选择 / 新增 / 删除音符均写回 `MusicDocument`
- [x] 缩放与滚动可用，导出可用
- [x] 无“音符位置与键位对应关系错误”（由 `unmapped` 机制与测试保证）

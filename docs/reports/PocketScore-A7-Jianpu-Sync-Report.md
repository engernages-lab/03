# PocketScore A.7 — 数字谱与双格式同步报告

- **版本**：V1.0-A
- **阶段**：A.7 JianpuNotationEngine + 双格式同步
- **结论**：**PASS**（30 项测试通过，含双向同步与撤销重做）

---

## 1. 交付内容

| 要求 | 状态 | 说明 |
| --- | --- | --- |
| 数字谱渲染 | ✅ | `JianpuScore.tsx` |
| 音高转数字 | ✅ | `degree_for_pitch()`（唯一实现） |
| 高低八度标记 | ✅ | `octave` 相对中音区，上下点 |
| 时值标记 | ✅ | `—` / `-` / 无 / `_` / `=` |
| 附点 | ✅ | `dots` 0–2 |
| 连音 | ✅ | `tie` = start / stop / continue |
| 休止符 | ✅ | `token="0"` |
| 小节线 | ✅ | 按 `measures[]` 分块渲染 |
| 拍号 / 速度 | ✅ | 头部 `1=C 4/4 ♩=100` |
| 和弦 | ✅ | 纵向堆叠（`ChordStack`） |
| 多轨道 | ✅ | 所有轨道合并渲染（按时间排序，和弦按音高堆叠） |
| 双格式同步 | ✅ | 同一文档重编译 |
| 修改格子谱 → 数字谱更新 | ✅ | 测试覆盖 |
| 修改数字谱 → 格子谱更新 | ✅ | 数字谱支持 ±半音编辑 |
| 修改键盘布局 → 两谱键位同步 | ✅ | 测试覆盖 |
| 撤销 / 重做 | ✅ | 文档快照栈（前端 50 步 + 服务端 PUT 还原） |

## 2. 音高 → 数字算法

```
tonic_reference = 60 + tonic_pc          # 中音区
relative        = (pitch - tonic_pc) % 12
scale           = 大调 [0,2,4,5,7,9,11] / 自然小调 [0,2,3,5,7,8,10]
若 relative ∈ scale → degree = 序号+1，无变音
否则取最近音级 ±1 个半音 → "#"/"b"
octave = (pitch - tonic_reference) // 12   # 上/下加点
```

- 调号解析支持 12 大调 + 12 自然小调（`parse_key_signature`）。
- 变音拼写可配置（`JianpuSettings.accidental_style = sharp|flat`），默认升号：
  C#4 → `#1`，F#4 → `#4`，Bb4 → `#6`（`flat` 模式为 `b7`）。
  *说明：半音音符与两个音级等距，拼写属约定问题，因此做成可配置并在此记录。*
- 时值符号按拍数映射，非整倍数标记 `approximate=true`（前端虚线下划线提示）。

## 3. 双格式同步机制

```text
        MusicDocument（唯一真源）
        ├── compile_grid()   → GridViewModel
        └── compile_jianpu() → JianpuViewModel
                  ▲
   任一谱面编辑 → EditOperation[] → POST /documents/{id}/edits
                  → 服务端原子应用 → 两谱整体重编译
```

- **不存在**“局部 patch 视图模型”的捷径；每次编辑都整体重编译，两谱不可能分叉。
- 编辑指令集：`add_note` · `add_rest` · `update_note` · `delete_note` · `move_note` ·
  `transpose` · `quantize` · `set_tempo` · `set_time_signature` · `add_track` · `delete_track` · `set_layout`。
- 批量编辑**原子**：任一操作失败则整批不生效（测试 `test_failed_batch_leaves_document_untouched`）。
- 撤销/重做：前端 `document` store 保存快照栈（上限 50），撤销时 `PUT /documents/{id}` 还原后重编译。

## 4. 接口

| 方法 | 路径 |
| --- | --- |
| GET | `/api/v1/notation/{id}/jianpu?layout_id&key_signature` |
| GET | `/api/v1/notation/{id}/jianpu.txt` |
| GET | `/api/v1/notation/{id}/both?divisions&layout_id` |
| POST | `/api/v1/documents/{id}/edits`（两谱共用） |
| PUT | `/api/v1/documents/{id}`（撤销/重做还原） |

`/both` 返回 `{document, grid, jianpu, findings}`，前端一次拿到两谱，天然同帧。

## 5. 测试证据

```text
$ .\.venv\Scripts\python.exe -m pytest tests/test_jianpu_notation.py -q
.............................                (29 passed)

$ .\.venv\Scripts\python.exe -m pytest tests/test_notation_sync.py -q
.............                                (13 passed)
```

数字谱断言：

- C 大调：C4→`1`、B4→`7`、C5→`1`(oct+1)、C3→`1`(oct−1)；C#4→`#1`、F#4→`#4`。
- A 小调：A4→`1`，C4→`3`(oct−1)，C5→`3`。
- G 大调：G4→`1`，C4→`4`(oct−1)。
- 时值：4 拍 `—`、2 拍 `-`、1 拍 空、0.5 `_`、0.25 `=`、1.5 `(空,点1)`、3 拍 `(-,点1)`。
- 休止 `0`；和弦 3 音堆叠 `chord_index 0/1/2`、token `1/3/5`。
- 连音：相邻同音高 → start/stop，`stats.ties==2`；不相邻无 tie。
- 键位标签来自布局（E4→`k2`/`E4`）；超出布局的音符仍显示数字（`#1`）。

同步断言：

- 加音符 → 格子谱首格 + 数字谱 `1`，同一个 `event_id`。
- 改音高 60→67 → 格子谱从 `k0` 移到 `k4`，数字谱 `1`→`5`。
- 改时值 1→2 拍 → 格子 span 8、数字谱 `-`。
- 删除 → 两谱同时清空。
- tempo 84 → 两谱头部同步。
- 3/4 → 格子 12 格、数字谱 `3/4` 且拍位重算（beat 6 → 第 3 小节第 1 拍）。
- 切换十二键布局 → 键位标签 `C#4`、音高仍 61、格子落在 `k1`。
- 撤销：恢复快照后两谱 `stats` 与 token 序列与基线完全一致。
- 失败批次：加入一条非法 `delete_note` → 404，两谱统计不变。

## 6. 前端实现

- `ScoreEditorPage`：标题/元信息、撤销重做、缩放、视图切换（双谱/格子/数字）、
  布局与网格切换、BPM 与拍号、插入休止、时值 ×2/÷2、±半音、量化、删除、四种导出。
- `JianpuScore`：八度点、附点、时值横线与下划线、连音标记、和弦纵向堆叠、键位小字。
- 选中态在两谱之间共享（同一 `event_id`），选中信息条显示 pitch/拍位/小节/键位。

## 7. 已知问题

| 问题 | 说明 |
| --- | --- |
| 变音拼写默认升号 | 与部分教材的 `b7` 习惯不同，已提供 `flat` 模式 |
| 连音只做识别与标记 | 未把 tie 合并为单一“延长音”符号，渲染为标记 |
| 撤销栈仅前端 | 刷新后栈清空；文档本身已持久化，不影响数据 |
| 多轨道数字谱合并显示 | 未做声部分行（V1.0-B 计划） |

## 8. 验收

- [x] 数字谱正确渲染音高、八度、时值、附点、连音、休止、小节线、拍号、速度、和弦、多轨
- [x] 任一侧编辑另一侧立即同步（整体重编译保证）
- [x] 切换布局后两谱键位同步、音高不变
- [x] 撤销/重做在两谱视图中均生效
- [x] 全部单元测试通过

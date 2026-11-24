# PocketScore A.4 — 自定义口袋键盘系统报告

- **版本**：V1.0-A
- **阶段**：A.4 KeyboardMappingEngine
- **结论**：**PASS**（25 项单元 + API 测试通过）

---

## 1. 交付内容

| 目标 | 状态 | 位置 |
| --- | --- | --- |
| 自定义布局（键数/排列/名称/音高/八度/颜色） | ✅ | `schemas/keyboard.py` |
| 键位数量与排列 | ✅ `key_count` 1–36、`index/row/col` 连续校验 | 同上 |
| 音高对应关系 | ✅ `midi_pitch` 或 `semitone_offset` 二选一 | 同上 |
| 八度设置与折叠 | ✅ `root_note`、`octave_span` 折叠算法 | `keyboard/mapping.py` |
| 键位颜色 | ✅ `#RRGGBB` 校验 + 派生调色板 | 同上 |
| 键位预览 | ✅ `GET /keyboard-layouts/{id}/preview` + 前端 `/keyboard` | API + `KeyboardPage.tsx` |
| 布局保存 / 导入 / 导出 | ✅ CRUD + `/import` + `/export` | `keyboard/repository.py` |
| 多布局切换 / 恢复默认 | ✅ 列表 + `restore-default` | 同上 |
| 布局与谱面解耦 | ✅ 文档内嵌快照，切换不改音高 | `apply_layout()` |
| 可视化编辑器 | ✅ `/keyboard` 页：预览条、键位表、颜色选择、增删键 | 前端 |

## 2. 内置布局（真实可用，非占位）

| layout_id | 键数 | 说明 |
| --- | --- | --- |
| `builtin:7-key-c-major` | 7 | C4–B4 自然音阶（默认） |
| `builtin:12-key-chromatic` | 12 | C4–B4 半音阶 |
| `builtin:10-key-folded` | 10 | do–mi' 双八度折叠 |

## 3. 映射算法（唯一实现）

```
绝对音高 = midi_pitch                       if 存在
         = root_note + semitone_offset      otherwise
```

- **直接命中**优先；`octave_span > 1` 时启用折叠：按音高类匹配，取八度距离最小的键，平局取 `index` 小者。
- 找不到键位 → `mapped_key = null`，事件进入格子谱 `unmapped[]`，**绝不修改 pitch**。
- 确定性：同一 `(layout, pitch)` 恒得同一 `key_id`。

## 4. 布局变更的影响

```text
apply_layout(document, new_layout)
  ├── document.keyboard_layout = new_layout      ← 只换布局快照
  └── 对每个事件重算 mapped_key                   ← pitch/start_time/duration 不变
```

测试证明：C4–B4 七键布局下 `pitch=65` → `k3`；切换到十二键半音阶后同一事件 `pitch` 仍为 65，`mapped_key` 变为 `k5`；再切回恢复 `k3`。

## 5. 接口（`/api/v1/keyboard-layouts`）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `` | 内置 + 自定义布局 |
| POST | `` | 创建（id 冲突返回 409） |
| GET | `/{id}` | 单布局 |
| PUT | `/{id}` | 更新（内置返回 403 `LAYOUT_READONLY`） |
| DELETE | `/{id}` | 删除（内置 403） |
| POST | `/{id}/duplicate` | 复制为新 id |
| GET | `/{id}/preview` | 键位预览 + pitch_map |
| GET | `/{id}/export` | 导出 `{pocketscore_layout, version, layout}` |
| POST | `/import` | 导入（id 冲突自动重命名） |
| POST | `/restore-default` | 恢复默认布局 |
| GET | `/{id}/pitch-map` | 全音高→键位映射表 |

## 6. 前端可视化编辑器

`/keyboard`：

- 左栏布局列表（内置标记、键数、八度跨度）；导入按钮。
- 预览条：按键位顺序渲染，顶部色条 + 键名 + 实际音名。
- 键位表：名称 / MIDI 音高 / 相对半音 / 颜色 / 删除，支持新增键。
- 只读保护：内置布局显示“复制为可编辑”，保存时自动创建副本。
- 导出 JSON、复制布局、删除布局、恢复默认。

## 7. 测试证据

```text
$ .\.venv\Scripts\python.exe -m pytest tests/test_keyboard_mapping.py -q
.........................                   (25 passed)
```

覆盖：

- 默认七键 / 十二键 / 十键折叠布局的 `pitch → key` 与 `key → pitch`。
- 折叠布局：72 命中显式键 `k7`（`fallback=false`）；84 折叠到 `k7`（`fallback=true`）。
- 越界音高（127）返回 `None`，`apply_layout` 后 pitch 不变。
- 校验：重复 `key_id`、`key_count` 不符、index 不连续、非法颜色、缺少音高来源全部拒绝。
- API：创建/更新/删除/复制/预览/导出/导入/恢复默认；内置 PUT 返回 403；重复 id 返回 409。
- `move_note` 通过键位改音高：`k4` → pitch 67，`mapped_key` 同步。

## 8. 已知问题

| 问题 | 说明 |
| --- | --- |
| 折叠布局的 `fallback` 仅用于 UI 提示 | 未在数据模型中标记“折叠命中”，因为不影响音高正确性 |
| 布局颜色不参与谱面语义 | 颜色仅用于区分键位，不影响可读性判断 |
| 单布局最多 36 键 | 与移动端口袋键盘尺寸匹配，超出返回校验错误 |

## 9. 验收

- [x] 可创建、编辑、复制、删除、导入、导出、切换、恢复默认布局
- [x] 改布局后音符键位重算，原始音高不受影响
- [x] 格子谱行序与键名完全来自布局（A.6 联测）
- [x] 可视化编辑器可用（E2E 用例 5 通过：复制内置布局 → 改键名 → 保存 → 预览更新）

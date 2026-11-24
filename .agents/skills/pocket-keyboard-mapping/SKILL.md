---
name: pocket-keyboard-mapping
description: PocketScore AI 的口袋键盘布局与音高↔键位映射引擎。定义 KeyboardLayout 结构、映射算法、布局编辑器契约与默认布局；改布局相关代码前必读。
---

# pocket-keyboard-mapping

## 1. 职责

- 定义 `KeyboardLayout` / `KeyDefinition`（自定义布局、键数、排列、名称、音高、八度、颜色）。
- 实现 `KeyboardMappingEngine`：`pitch → mapped_key` 与 `mapped_key → pitch`。
- 提供默认布局、布局校验、导入/导出（JSON）、多布局切换、恢复默认。
- 在布局变更后**重新计算**所有事件的 `mapped_key`。

不负责：谱面渲染（→ grid / jianpu）、文档存储（→ music-core）。

## 2. 核心数据结构

### 2.1 KeyboardLayout

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `layout_id` | `str` | 标识；内置布局以 `builtin:` 前缀 |
| `name` | `str` | 显示名，1–40 字符 |
| `description` | `str` | 可选说明 |
| `root_note` | `int` | MIDI 根音（默认 60 = C4） |
| `key_count` | `int` | 键数，1–36；必须等于 `len(keys)` |
| `octave_span` | `int` | 纵向跨越八度数，1–4 |
| `keys` | `KeyDefinition[]` | 按视觉顺序（从上到下、从左到右）排列 |
| `is_builtin` | `bool` | 内置布局不可删除，可复制 |

### 2.2 KeyDefinition

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `key_id` | `str` | 布局内唯一，如 `k0`、`low-C` |
| `label` | `str` | 键位名称（显示在谱面上） |
| `index` | `int` | 视觉序号，0 起，决定格子谱行序 |
| `row` | `int` | 行号，0 起 |
| `col` | `int` | 列号，0 起 |
| `midi_pitch` | `int \| null` | 绝对音高；空则用 `semitone_offset` |
| `semitone_offset` | `int \| null` | 相对 `root_note` 的半音偏移，可负 |
| `color` | `str` | `#RRGGBB`，用于格子谱音符底色 |
| `octave` | `int \| null` | 覆盖默认八度（仅显示用途） |

### 2.3 映射算法（唯一实现：`app/services/keyboard/mapping.py`）

```
绝对音高 = midi_pitch            if midi_pitch is not None
         = root_note + semitone_offset * factor   otherwise
```

- `factor` 支持 `octave_span > 1` 的“口袋键盘”折叠：当布局声明多八度时，
  用 `pitch_class` 匹配 + 八度偏移，选择**音高距离最小**的键（平局取 `index` 小者）。
- 同一音高匹配到多个键时按 `index` 升序取第一个，保证确定性。
- 找不到键位时 `mapped_key = null`（该音符在格子谱中显示为“超出键盘范围”，
  在数字谱中照常显示数字）—— **绝不修改 pitch 来凑键**。

## 3. 输入 / 输出

- 输入：`KeyboardLayout`、MIDI 音高集合、布局编辑指令。
- 输出：`{pitch: key_id}` 映射表；`MappingResult{mapped_key, key, fallback: bool}`。
- API：
  - `GET /api/v1/keyboard-layouts` 列表
  - `POST /api/v1/keyboard-layouts` 创建
  - `PUT /api/v1/keyboard-layouts/{id}` 更新
  - `DELETE /api/v1/keyboard-layouts/{id}` 删除（内置返回 403）
  - `POST /api/v1/keyboard-layouts/{id}/duplicate`
  - `GET /api/v1/keyboard-layouts/{id}/preview?octaves=2` 键位预览
  - `POST /api/v1/keyboard-layouts/import` / `GET .../{id}/export`
  - `POST /api/v1/keyboard-layouts/{id}/restore-default`

## 4. 开发流程

1. 读本 Skill 与 `pocket-music-core`（`mapped_key` 字段契约）。
2. 修改后在文档级重算 `mapped_key`（`KeyboardMappingEngine.apply(document, layout)`）。
3. 运行 `pytest tests/test_keyboard_mapping.py`。
4. 前端编辑器改动后运行 `npm run test`。

## 5. 技术约束

- 键位 ID 在布局内唯一；`index` 连续且从 0 开始（校验器强制）。
- `key_count == len(keys)`；`1 ≤ key_count ≤ 36`。
- 颜色必须是 `#RRGGBB`；未指定时由 `index` 派生色板，保证视觉可区分。
- 布局与谱面解耦：文档只保存布局快照，切换布局不改变 `pitch/start_time/duration`。
- 映射必须确定性：同一 `(layout, pitch)` 永远得到同一 `key_id`。

## 6. 禁止事项

- ❌ 修改布局时改动音符 `pitch` / 时值。
- ❌ 在前端重复实现映射算法（前端只渲染后端返回的 `mapped_key` 与 `key` 元数据）。
- ❌ 允许重复 `key_id`、重复 `index`、重复绝对音高（校验器拒绝）。
- ❌ 删除内置默认布局；不提供“恢复默认”入口。

## 7. 错误处理

| 场景 | 错误码 | HTTP |
| --- | --- | --- |
| 布局不存在 | `KEYBOARD_LAYOUT_NOT_FOUND` | 404 |
| `key_count` 与 `keys` 不一致 | `LAYOUT_KEY_COUNT_MISMATCH` | 422 |
| `key_id` / `index` 重复 | `LAYOUT_DUPLICATE_KEY` | 422 |
| 颜色格式非法 | `LAYOUT_INVALID_COLOR` | 422 |
| 删除内置布局 | `LAYOUT_READONLY` | 403 |
| 导入文件不是合法布局 JSON | `LAYOUT_IMPORT_INVALID` | 422 |

## 8. 测试规范

- `tests/test_keyboard_mapping.py`
  - 默认布局：C4..B4 七键，`pitch→key` 全部命中。
  - 折叠八度：`octave_span=2` 时 C5 映射到与 C4 相同的键。
  - 超出范围：`pitch=127` 返回 `None` 且 `apply()` 后 `pitch` 不变。
  - 布局切换：同一文档换布局后 `mapped_key` 变化、`pitch` 序列不变。
  - 校验：重复 key_id、key_count 不符、非法颜色全部报错。
  - 导入/导出往返一致。

## 9. 验收标准

- [ ] 可创建、编辑、复制、删除、导入、导出布局。
- [ ] 改变布局后音符键位重算，原始音高不受影响。
- [ ] 格子谱上的键位名称与布局完全一致（与 `pocket-grid-notation` 联测）。
- [ ] 提供可视化编辑器（前端 `/keyboard`），支持增删键、改音高、改颜色、预览。
- [ ] 单元测试覆盖上述全部条目。

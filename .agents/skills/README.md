# PocketScore AI · 六大 Skill 索引与交叉依赖

本目录是 PocketScore AI 的开发契约。**修改任何核心模块前必须先读对应 Skill，
修改后必须运行对应测试。**

## 1. Skill 一览

| Skill | 负责 | 唯一实现位置 | 主要测试 |
| --- | --- | --- | --- |
| [`pocket-music-core`](pocket-music-core/SKILL.md) | 统一数据契约 `MusicDocument` | `backend/app/schemas/music_document.py`、`backend/app/services/music_document/` | `tests/test_music_document.py` |
| [`pocket-keyboard-mapping`](pocket-keyboard-mapping/SKILL.md) | 布局与音高↔键位映射 | `backend/app/services/keyboard/` | `tests/test_keyboard_mapping.py` |
| [`pocket-grid-notation`](pocket-grid-notation/SKILL.md) | 格子谱视图模型 | `backend/app/services/notation/grid.py` | `tests/test_grid_notation.py` |
| [`pocket-jianpu-notation`](pocket-jianpu-notation/SKILL.md) | 数字谱视图模型 + 双格式同步 | `backend/app/services/notation/jianpu.py`、`sync.py` | `tests/test_jianpu_notation.py`、`tests/test_notation_sync.py` |
| [`pocket-audio-transcription`](pocket-audio-transcription/SKILL.md) | MIDI 解析、音频预处理、扒谱作业 | `backend/app/services/midi/`、`backend/app/services/audio/` | `tests/test_midi_import.py`、`tests/test_audio_pipeline.py` |
| [`pocket-music-source`](pocket-music-source/SKILL.md) | 多音源接入、统一曲库、播放、扒谱资格 | `backend/app/services/sources/`、`library.py`、`eligibility.py` | `tests/test_eligibility.py`、`tests/test_sources_*.py` |

## 2. 依赖方向（有向无环）

```
                ┌──────────────────────┐
                │   pocket-music-core  │   ← 被所有 Skill 依赖，不依赖任何 Skill
                └──────────┬───────────┘
        ┌──────────────────┼───────────────────┬────────────────────┐
        ▼                  ▼                   ▼                    ▼
 keyboard-mapping    grid-notation      jianpu-notation    audio-transcription
        │                  │                   │                    │
        └────────┬─────────┴─────────┬─────────┘                    │
                 ▼                   ▼                              ▼
          （两谱共用 sync）    music-source  ← 资格判定拦截音频来源
```

**规则**

1. `music-core` 不得 import 其他 Skill 的模块。
2. `grid` / `jianpu` 可以调用 `keyboard-mapping` 与 `music-core`，
   但两者之间**不得互相 import**（同步逻辑只能在 `sync.py`）。
3. `audio-transcription` 可以产出 `MusicDocument`，不得直接调用格子谱/数字谱引擎。
4. `music-source` 只提供曲目与流/权限信息，不解析音频、不生成谱面。
5. 资格判定（`eligibility`）是音频进入 AI 链路的**唯一闸门**。

## 3. 禁止重复实现的转换

| 转换 | 唯一实现 | 其他模块的正确做法 |
| --- | --- | --- |
| 音高 → 键位 | `keyboard/mapping.py` | 读 `mapped_key` |
| 音高 → 简谱数字/八度 | `notation/jianpu.py` | 读 `degree/octave` |
| 拍 → 秒（含速度） | `music_document/timing.py` | 调用该函数 |
| 拍 → 小节/拍位 | `music_document/timing.py` | 调用 `reindex()` |
| MIDI tick → 拍 | `midi/importer.py` | 不在别处解析 MIDI |
| 音符 → 格子坐标 | `notation/grid.py` | 读 `GridViewModel` |
| 权限 → 资格 | `eligibility.py` | 读判定结果 |
| 标题 → 曲目合并 | `library.py::resolve_group` | 不按标题合并 |

## 4. 开发流程（每个子阶段强制）

1. **读**：对应 Skill + 上游依赖 Skill。
2. **查**：`docs/architecture/system-overview.md` 与现有测试。
3. **计划**：列出要改/新增/删除的文件。
4. **小步实施**：一次只改一个模块。
5. **测**：`pytest` 对应文件 → 再跑全量；前端 `npm run test`。
6. **写报告**：`docs/reports/PocketScore-Ax-...-Report.md`（含真实输出）。

## 5. 允许修改 / 禁止破坏

| 允许 | 禁止 |
| --- | --- |
| 追加新的事件字段（升 `schema_version` + 迁移） | 删除或重命名已有必填字段 |
| 新增 `NotationSettings` 选项 | 改变 `start_time/duration` 的单位语义 |
| 新增 provider 适配器 | 让某个 provider 绕过 `eligibility` |
| 优化解析与编译性能 | 在前端复制后端算法 |
| 追加 API 端点 | 改变错误信封结构 |

## 6. 测试矩阵

| 改动 | 必跑 |
| --- | --- |
| `schemas/music_document.py` | `test_music_document` + 全量后端 |
| `services/keyboard/**` | `test_keyboard_mapping` + `test_notation_sync` |
| `services/notation/grid.py` | `test_grid_notation` + `test_notation_sync` |
| `services/notation/jianpu.py` | `test_jianpu_notation` + `test_notation_sync` |
| `services/midi/**`、`services/audio/**` | `test_midi_import`、`test_audio_pipeline` |
| `services/sources/**`、`eligibility.py` | `test_eligibility`、`test_sources_*`、`test_library_merge` |
| 前端 store / 引擎渲染 | `npm run typecheck && npm run test` |
| 端到端流程 | `npx playwright test` |

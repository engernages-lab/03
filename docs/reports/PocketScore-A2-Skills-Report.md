# PocketScore A.2 — 六大 Skill 实施报告

- **版本**：V1.0-A
- **阶段**：A.2 六大 Skill 实施
- **结论**：**PASS**

---

## 1. 交付物

| # | Skill | 路径 | 行数（约） |
| --- | --- | --- | --- |
| 1 | pocket-music-core | `.agents/skills/pocket-music-core/SKILL.md` | 150 |
| 2 | pocket-keyboard-mapping | `.agents/skills/pocket-keyboard-mapping/SKILL.md` | 140 |
| 3 | pocket-grid-notation | `.agents/skills/pocket-grid-notation/SKILL.md` | 145 |
| 4 | pocket-jianpu-notation | `.agents/skills/pocket-jianpu-notation/SKILL.md` | 150 |
| 5 | pocket-audio-transcription | `.agents/skills/pocket-audio-transcription/SKILL.md` | 160 |
| 6 | pocket-music-source | `.agents/skills/pocket-music-source/SKILL.md` | 165 |
| — | 交叉依赖与开发流程 | `.agents/skills/README.md` | 110 |

## 2. 每个 Skill 的必备章节（全部 9 项齐备）

| 章节 | core | keyboard | grid | jianpu | audio | source |
| --- | --- | --- | --- | --- | --- | --- |
| 职责说明 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 输入/输出规范 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 核心数据结构 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 开发流程 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 技术约束 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 禁止事项 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 错误处理 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 测试规范 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 验收标准 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

## 3. 为 AI 开发工具提供的契约

- **项目背景**：每个 Skill 开头说明在生态中的位置与不负责的部分。
- **文件结构**：以「唯一实现位置」表格明确模块路径，`README.md` §3 给出禁止重复清单。
- **模块职责**：`README.md` §2 依赖 DAG，规定 import 方向（core 不反向依赖）。
- **允许修改的文件**：`README.md` §5 列出允许/禁止的变更类型。
- **禁止破坏的接口**：错误信封、`start_time/duration` 单位语义、必填字段、`eligibility` 闸门。
- **代码规范**：Python 用 Ruff（`backend/pyproject.toml`，line-length 110、py39 target）；
  前端 `strict` TS + `noUnusedLocals`。
- **测试要求**：`README.md` §6 改动→必跑测试矩阵；每阶段必须提供真实 pytest 输出。

## 4. Skill 协作关系

```
music-core ──► keyboard-mapping ──► grid-notation ─┐
     │                                             ├──► notation/sync.py（唯一同步点）
     └────────► jianpu-notation ───────────────────┘
     ▲
     │ 产出 MusicDocument
audio-transcription ◄── eligibility ◄── music-source
```

关键约束（已在各 Skill 中重复强调，避免实现漂移）：

1. **单一数据源**：两谱均由 `MusicDocument` 编译，禁止各自存音符。
2. **转换唯一实现**：音高→键位、音高→简谱数字、拍→小节、MIDI tick→拍 各仅一处。
3. **资格闸门**：`eligibility` 是音频进入 AI 链路的唯一入口，Spotify 恒 `PROVIDER_RESTRICTED`。
4. **不伪造**：`pocket-audio-transcription` 明确规定「无模型时返回 501，不返回假音符」。

## 5. 自检结果

| 检查项 | 结果 |
| --- | --- |
| 六个 SKILL.md 均通过 DSH 技能加载（出现在可用技能目录） | ✅ 6/6 已注册 |
| frontmatter `name` 为 kebab-case 且与目录一致 | ✅ |
| 每个 Skill 均声明「禁止事项」与「验收标准」 | ✅ |
| 交叉依赖文档存在且含禁止重复实现清单 | ✅ |
| 六个 Skill 的测试文件路径指向真实计划路径 | ✅（A.3 起逐项落地） |

## 6. 已知限制

- Skill 描述的字段是**契约**，实现将在 A.3–A.8 逐条对齐；每阶段报告需核对偏差。
- `pocket-music-source` 中 Spotify/Apple/网易云/QQ 的「可实施范围」以官方文档与
  实际凭据为准，A.8 报告将给出真实证据与结论。

## 7. 下一阶段

A.3：实现 `MusicDocument` 核心数据引擎（Pydantic v2 模型、时间轴计算、编辑原语、
序列化/反序列化/校验/版本迁移、REST 接口、单元测试）。

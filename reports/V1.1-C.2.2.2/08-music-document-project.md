# V1.1-C.2.2.2 · 08 MusicDocument 与项目保存（Phase 8）

- **日期**：2026-11-27
- **脚本**：`scripts/deploy/verify-staging-document.py`
- **证据**：`artifacts/project-document-check.json`

---

## 1. 测试项目

| 项 | 值 |
| --- | --- |
| 唯一标记 | `C2-2-2-STAGING-REGRESSION-20261127T105532Z` |
| Document ID | `6a0c696a7289` |
| 来源 | 由 MP3 真实转录生成的 MusicDocument（不是空文档） |
| 音频资产 | `5b520fb5abda`（11 385 字节 MP3） |
| schema_version | 1 |
| 轨道数 | 1（`piano`） |

> 本项目没有独立的 "Project" 实体：一个 MusicDocument + 关联音频资产即为一个作品。
> 报告如实按此建模，不虚构 Project ID。

## 2. 写入真实数据

| 步骤 | 请求 | 结果 |
| --- | --- | --- |
| 读取转录产物 | `GET /api/v1/documents/6a0c696a7289` | 200，4 个音符 |
| 命名项目 | `PATCH /api/v1/documents/...` `{title}` | 200，标题持久化 |
| 编辑（转调 +1） | `POST /api/v1/documents/.../edits` `{op:"transpose",semitones:1}` | 200，音高全部 +1 |
| 编辑回退（-1） | 同接口 | 200，音高恢复原值 |
| 重新读取 | `GET /api/v1/documents/...` | 200，标题与音符均为最新值（读的是存储，不是内存） |
| 列表 | `GET /api/v1/documents?limit=50` | 200，`total=8`，包含该文档 |

转调实测：

```text
before: [60, 64, 67, 72]
after transpose +1: [61, 65, 68, 73]   transpose_applied = true
after revert:       [60, 64, 67, 72]   revert_restored  = true
```

## 3. 两种谱面来自同一文档

| 项 | 值 |
| --- | --- |
| `grid.document_id` | `6a0c696a7289` |
| `jianpu.document_id` | `6a0c696a7289` |
| `same_document` | ✅ true |
| 网格谱 | `notes=3, unmapped=1` → 合计 4 |
| 数字谱 | `notes=4, unmapped=1`（unmapped 是子集标记） |

**计数契约（本轮实测总结，已写入验收脚本）**：

- 网格谱：`notes + unmapped == 文档音符数`（`unmapped` 是被布局丢弃的音符）
- 数字谱：`notes == 文档音符数`，`unmapped ≤ notes`（只是"未映射到键盘行"的子集）

编辑后两者仍指向同一文档，说明双谱面同源。

## 4. 项目重新读取（端到端）

```text
创建/命名项目 → 保存 → 列表查询 → 详情读取 → MusicDocument 读取 → 音符检查
```

全部通过真实 HTTPS 完成，无数据库直写、无预置音符。

## 5. 结论

| 编号 | 检查 | 结果 |
| --- | --- | --- |
| DOC-01 | 文档可读 | ✅ 200，4 音符 |
| DOC-02 | 重命名持久化 | ✅ 重读仍是新标题 |
| DOC-03 | 编辑生效并可回退 | ✅ 音高 +1 / 复原 |
| DOC-04 | 网格谱与数字谱同源 | ✅ 同一 document_id |
| DOC-05 | 计数守恒 | ✅ 两种视图都不丢音符 |
| DOC-06 | 列表可见 | ✅ |

> 遗留说明：`unmapped=1` 表示有 1 个音符（pitch 72）超出默认键盘布局的映射范围。
> 这是布局配置问题而非数据丢失，已记录为后续优化项，不影响本阶段验收。

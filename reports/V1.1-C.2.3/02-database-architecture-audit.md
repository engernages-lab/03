# PocketScore AI V1.1-C.2.3.2 · 数据库结构与数据依赖审计

> 只读审计。所有结论来自**合成临时库**（使用真实 SQLAlchemy 元数据建表）与源码阅读，
> 未连接、未读取、未修改任何 Railway 数据库或 Volume。

## 1. 审计方法与边界

| 项 | 说明 |
| --- | --- |
| 环境 | Windows 本地，`backend/.venv`（Python 3.9.13），SQLite 库版本 3.33.0 |
| 库来源 | `POCKETSCORE_DATABASE_URL=sqlite:///<临时目录>/audit.db`，用 `init_db()` 按真实元数据建表 |
| 未触碰 | `/data/pocketscore.db`、Railway Staging/Production、任何用户音频 |
| 临时库 | 审计结束即删除（Windows 句柄原因个别残留，均位于系统临时目录，非项目目录） |

## 2. 数据库基本情况

| 项 | 实测值 |
| --- | --- |
| 引擎 | SQLite（`POCKETSCORE_DATABASE_URL` 以 `sqlite` 开头） |
| 生产路径 | `sqlite:////data/pocketscore.db`（C.2.3.1 变量审计，绝对路径） |
| 本地/测试路径 | `backend/data/pocketscore.db`（`storage_dir` 默认 `./data/storage`） |
| journal_mode | **WAL**（每个连接由 `app/core/db.py` 事件钩子设置） |
| foreign_keys | **ON**（`PRAGMA foreign_keys=ON`，连接级设置） |
| page_size | 4096 |
| 表数量 | **16** |
| 迁移 | Alembic 2 个版本：`0001_initial`、`0002_event_confidence` |

> 注意：`PRAGMA foreign_keys` 是**连接级**开关，不会写进文件。用裸 `sqlite3` 打开备份文件时读到 `0`
> 是正常现象；`PRAGMA foreign_key_check` 与开关无关，永远基于文件内的外键定义执行。

## 3. 表结构（16 张）

| 表 | 列数 | 外键 |
| --- | --- | --- |
| `audio_assets` | 19 | — |
| `music_documents` | 15 | — |
| `music_events` | 15 | `document_id` → `music_documents.id` |
| `music_tracks` | 9 | `document_id` → `music_documents.id` |
| `transcription_jobs` | 15 | `asset_id` → `audio_assets.id` |
| `music_sources` | 10 | — |
| `external_accounts` | 10 | `source_id` → `music_sources.id` |
| `music_source_permissions` | 10 | `source_id` → `music_sources.id` |
| `unified_artists` | 9 | `source_id` → `music_sources.id` |
| `unified_albums` | 11 | `source_id` → `music_sources.id` |
| `unified_tracks` | 18 | `source_id` → `music_sources.id` |
| `unified_playlists` | 11 | `source_id` → `music_sources.id` |
| `playlist_tracks` | 4 | `playlist_id` → `unified_playlists.id`；`track_id` → `unified_tracks.id` |
| `playback_history` | 5 | `track_id` → `unified_tracks.id` |
| `user_favorites` | 3 | `track_id` → `unified_tracks.id` |
| `keyboard_layouts` | 10 | — |

（另加 Alembic 自带的 `alembic_version`。）

**核心业务表**（备份可用性判定用）：`audio_assets`、`music_documents`、`music_events`、
`music_tracks`、`transcription_jobs`。

**没有用户表**：不存在 `users`/`accounts`，也没有任何 `user_id` 外键（与 C.2.3.1 结论一致）。

## 4. 数据与文件系统的依赖

| 关联 | 字段 | 指向 | 影响 |
| --- | --- | --- | --- |
| 音频 → 磁盘 | `audio_assets.stored_path` | `/data/storage/audio/<sha2>/<sha256><ext>` | 数据库只存路径；文件不在库内 |
| 封面 → 磁盘 | `audio_assets.artwork_path` | 同上存储根 | 同上 |
| 去重键 | `audio_assets.checksum_sha256` | 内容寻址 | 同一内容只存一份 |
| 文档 → 音频 | `music_documents.source_metadata_json` 内嵌 asset id | 逻辑引用 | 仅恢复库会出现"记录有、文件无" |
| 任务 → 音频 | `transcription_jobs.asset_id` | `audio_assets.id` | 外键，级联策略 `SET NULL` |

路径生成见 `app/services/audio/assets.py:171-173`（`settings.audio_path / checksum[:2] / f"{checksum}{ext}"`）。

### 4.1 结论

```text
数据库备份 ≠ 完整业务数据备份
```

- 只恢复数据库 → 记录完整、**音频文件缺失**，播放与再转录会失败。
- 只恢复 `/data/storage` → 文件齐全、**索引丢失**，表现为孤儿文件（不致命但是垃圾）。
- 正确做法：文件快照与数据库备份保持**同一时间点**，恢复时两者一起回滚。

## 5. 当前风险（与备份相关）

| # | 风险 | 等级 | 说明 |
| --- | --- | --- | --- |
| 1 | 无备份机制 | P0 | C.2.3.1 已确认：无 backup 脚本、无调度、无演练 |
| 2 | 数据库在 Volume，但 Volume 不是备份 | P0 | 误删/损坏/迁移都会连带消失 |
| 3 | SQLite 单文件 + WAL | P1 | 直接 `cp` 主文件会丢 WAL 中已提交的页 |
| 4 | 文件存储未随库备份 | P1 | 见 §4 |
| 5 | 无恢复演练记录 | P1 | "有备份"≠"能恢复" |
| 6 | 单实例无副本 | P1 | 主机级故障即中断 |

## 6. 推荐备份架构

```
/data/backups/                        ← 与数据库同卷，独立目录
  pocketscore-<UTC>.sqlite3           ← sqlite3 backup API 产出的单文件一致快照
  pocketscore-<UTC>.manifest.json     ← 元数据 + sha256 + pragma 结果
  pocketscore-<UTC>.sha256            ← 独立哈希文件
```

- **一致性**：`Connection.backup()`（在线 API），禁止 `shutil.copy`。
- **原子性**：临时文件 → 校验 → `os.replace`。
- **可验证**：manifest 独立可校验（哈希 + 完整性 + 外键 + schema version + 核心表）。
- **保留**：GFS（7 日 / 4 周 / 3 月），默认 dry-run。
- **文件存储**：另用增量工具（restic/rclone）同步 `/data/storage`，与库备份对齐时间点。
- **隔离**：Production 与 Staging 各自独立目录，禁止互相恢复。

实现见 `backend/app/ops/database_backup.py` 与运维手册 `docs/operations/database-backup-recovery.md`。

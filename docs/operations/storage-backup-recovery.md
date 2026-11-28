# 文件存储与联合备份恢复运维手册

> 适用版本：PocketScore AI V1.1（SQLite + 内容寻址文件存储）
> 工具：`backend/app/ops/storage_audit.py`、`backend/app/ops/project_backup.py`、`backend/app/ops/database_backup.py`
> 本文区分 **已实测** 与 **设计目标**；未实测的会显式标注。

---

## A. 文件存储架构

### A.1 目录结构（实测，`POCKETSCORE_STORAGE_DIR` 之下）

```
<storage>/
├── audio/<sha2>/<sha256><ext>     # 原始音频，内容寻址（业务数据，必须备份）
├── artwork/<sha256>.jpg|png       # 封面，内容寻址（业务数据，必须备份）
├── uploads/                       # 上传临时文件（可丢弃）
└── midi/                          # MIDI 导入中间产物（可重建）
```

- 内容寻址：文件名主干就是文件内容的 SHA-256，因此**重复上传自动去重**，
  文件名里同时携带完整性校验值。
- 临时目录 `uploads/` 与 `midi/` 不参与业务备份；`storage_audit` 会把它们计入
  `transient_files` 而不是 `orphans`。

### A.2 数据库引用关系（实测）

| 表.字段 | 值形态 | 解析规则 | 类别 |
| --- | --- | --- | --- |
| `audio_assets.stored_path` | **相对路径**，如 `audio/f4/f482…wav` | `<storage>/<stored_path>` | 音频 |
| `audio_assets.artwork_path` | **URL 形态**，如 `/static/artwork/<sha>.jpg` | 去掉前缀 → `<storage>/artwork/<sha>.jpg` | 封面 |

> `artwork_path` 存的不是文件系统路径，而是 URL。任何"把两个字段都当路径拼"的实现都会错，
> 本工具用 `artwork_relative_path()` 显式转换。

### A.3 文件生命周期（源码事实）

| 阶段 | 行为 | 顺序 |
| --- | --- | --- |
| 上传 | 流式写临时文件 → 校验大小/扩展名 → 计算 SHA-256 → 去重查询 | — |
| 落盘 | `os.replace(临时文件, <storage>/audio/<sha2>/<sha>.<ext>)`（同卷原子） | **先文件** |
| 登记 | 探测音频 → 写 `audio_assets` 行 → 事务提交 | **后数据库** |
| 失败 | 时长超限/探测失败时删除刚落盘文件 | 补偿 |
| 删除 | `delete_asset()`：先删数据库行并提交，再删文件 | 先库后文件 |

**由此得到两个性质**：

1. 正常情况下**不存在"数据库有记录、文件不存在"**——因为文件先落盘。
2. 数据库提交失败会留下**孤儿文件**（无害，内容寻址可复用），由审计工具报告。

**已知缺陷（P2）**：`delete_asset()` 删除文件前不检查该文件是否被其它记录（例如
`music_documents.source_metadata_json` 里内嵌的 asset 引用）使用；当前 API 未暴露
`DELETE /audio/assets/{id}` 之外的项目删除路径，风险有限但必须记录。

---

## B. 文件备份

### B.1 命令

```bash
cd backend

# 联合快照（数据库 + 被引用的文件），最常用
python -m app.ops.project_backup snapshot \
  --database /data/pocketscore.db \
  --storage /data/storage \
  --backup-root /data/backups

# 只审计文件存储，不备份
python -m app.ops.storage_audit scan   --storage /data/storage
python -m app.ops.storage_audit verify --storage /data/storage   # 逐个校验 sha256
python -m app.ops.storage_audit orphans --storage /data/storage
python -m app.ops.storage_audit missing --storage /data/storage
```

### B.2 文件清单（`storage/manifest.json`）

```json
{
  "manifest_version": 1,
  "backup_id": "pocketscore-snapshot-20261128-082108Z-f7cace",
  "created_at_utc": "2026-11-28T08:21:08+00:00",
  "storage_root_identifier": "storage",
  "file_count": 1,
  "total_size_bytes": 79424,
  "files": [
    {
      "relative_path": "audio/f4/f4824273….wav",
      "file_size_bytes": 79424,
      "sha256": "f4824273…",
      "media_category": "audio",
      "record_id": "39914e448448",
      "column": "stored_path",
      "backup_status": "SUCCESS"
    }
  ],
  "backup_status": "SUCCESS"
}
```

不含文件内容、不含原始上传文件名（只保留内容寻址名与相对路径）。

### B.3 SHA-256 校验

复制时边写边算（1 MiB 分块，不整文件读入内存），复制完成后再独立重算一次，
并要求 `源哈希 == 目标哈希 == 文件名主干`。任一不等 → 快照失败。

### B.4 并发锁

`<backup_root>/.snapshot.lock`，用 `O_CREAT|O_EXCL`（POSIX/Windows 都原子）创建，
内容记录 pid 与时间。超过 `LOCK_TIMEOUT_SECONDS`（默认 900s）视为进程已崩溃并接管。
锁被占用时命令以退出码 `3` 结束，不会排队乱写。

### B.5 失败处理

任一步失败：删除 `.inprogress-*` 暂存目录 → 抛错 → 退出码 `1`。
**不会**发布半成品目录。

---

## C. 联合快照

### C.1 结构

```
/data/backups/<snapshot_id>/
├── joint-manifest.json      # 权威清单（状态、哈希、计数、一致性）
├── snapshot.sha256          # joint-manifest.json 的哈希
├── database/
│   ├── <id>.sqlite3         # sqlite3 backup API 产物
│   ├── <id>.manifest.json
│   └── <id>.sha256
└── storage/
    ├── manifest.json
    └── <相对路径…>
```

### C.2 一致性保证（关键设计）

文件清单**从快照数据库里读**，不从活库读：

```
1. 先做 SQLite 在线备份（获得一致快照）      ← 时间点 T
2. 从该备份文件中读出 audio_assets 的引用     ← 引用集合 S
3. 逐个复制 S 中的文件，校验哈希              ← 文件必须等于备份时的内容
4. 数据库里引用的文件缺失 → 整个快照 FAILED
```

这样即使备份过程中有新的上传落盘，也不会污染快照；而快照引用的文件若在这期间被删除，
会明确失败而不是"看起来成功"。

**不声称**数据库与文件处于同一原子事务——SQLite 备份 API 与文件系统无法组成原子事务。
本方案通过"引用集合来自快照本身"消除时间窗口的影响，这是可证明的弱一致性而非强事务。

### C.3 失败回滚

`backup_status` 只有 `SUCCESS` 才发布；失败时暂存目录整体删除，`list` 看不到它。

### C.4 完整性验证

```bash
python -m app.ops.project_backup verify --snapshot /data/backups/<id>
```

检查：manifest 哈希、数据库哈希 + `integrity_check` + `foreign_key_check`、
每个文件存在/大小/哈希、文件计数、以及"数据库引用 ⊆ 快照文件清单"。

---

## D. 联合恢复

### D.1 恢复前检查

1. 目标必须是**隔离目录**：工具拒绝 `/data` 下任何路径，以及
   `POCKETSCORE_ENVIRONMENT` 为 `staging`/`production` 时的任何恢复（`--force` 不解除）。
2. `verify` 必须 `ok: true`。
3. 目标目录非空时必须显式 `--force`，且会先留 `<target>.pre-restore-<UTC>` 安全副本。

### D.2 命令

```bash
# 预览（默认）
python -m app.ops.project_backup restore \
  --snapshot /data/backups/<id> --target /tmp/restore-check

# 隔离目录实际执行
python -m app.ops.project_backup restore \
  --snapshot /data/backups/<id> --target /tmp/restore-check --force
```

### D.3 恢复结果布局

```
/tmp/restore-check/
├── database/pocketscore.db
└── storage/<相对路径…>
```

恢复后可直接把 `POCKETSCORE_DATABASE_URL`/`POCKETSCORE_STORAGE_DIR` 指向它来验证业务读取。

### D.4 恢复后校验

- 数据库：`integrity_check`、`foreign_key_check`、alembic revision。
- 文件：逐个 sha256、大小、数量。
- 关联：恢复后的数据库里每一条引用都必须在恢复后的存储树中命中。
- 业务：用 API 打开原 `document_id` / `asset_id` / `job_id`，读取乐谱与波形。

### D.5 失败回滚

发布前失败 → 暂存目录删除，目标不变。
发布时失败 → 若已把旧目标移到安全副本，会自动移回。

### D.6 生产恢复的现实限制

联合恢复是**目录级**的：需要停写窗口（停服务 → 恢复 → 启动）。
本阶段没有实现"在线热恢复"，也不提供绕过 `/data` 保护的开关。

---

## E. 文件生命周期与一致性运维

| 场景 | 现象 | 处理 |
| --- | --- | --- |
| 上传失败（数据库回滚） | 留下孤儿文件 | `storage_audit orphans`，确认后人工删除（工具不自动删） |
| 文件被误删 | `missing` 非空，播放/波形报错 | 从最近联合快照恢复文件 |
| 文件被替换 | `hash_mismatches` 非空 | 视为损坏，从快照恢复 |
| 重复引用 | `duplicates` 非空 | 检查是否人为改库；不影响完整性 |
| 上传与备份并发 | 备份只包含快照时刻的引用集合 | 无需处理，新文件进下一次快照 |

定期任务建议（**未实施**）：每日 `storage_audit verify` + 每周 `project_backup snapshot`，
失败即告警。

---

## F. 数据持久性

| 概念 | 说明 |
| --- | --- |
| Railway Volume 的职责 | 让 `/data` 在重新部署后仍然存在；**它不是备份** |
| 备份与 Volume 的区别 | Volume 与容器同生命周期区域；误删、损坏、区域故障都会连带丢失 |
| 异地备份 | 建议把 `<backup_root>` 定期同步到对象存储（跨区） |
| 备份加密 | 当前**未实现**；备份按敏感数据对待。若加密，密钥不得与备份同目录 |
| 恢复演练 | 每季度一次，必须走真实 API 复读项目（见下） |
| RPO / RTO | 见下表，**均为设计目标，未在 Railway 实测** |

| 指标 | 目标值 | 性质 |
| --- | --- | --- |
| RPO（数据库+文件） | ≤ 24h | 设计目标 |
| RTO（隔离恢复） | 分钟级（数据量相关） | 设计目标，本地实测单项目 ~1s |
| RTO（含停写窗口） | 10–30 分钟 | 设计目标 |

---

## G. Railway 后续部署方案（本阶段未执行）

1. **备份目录**：`/data/backups`。当前 Staging 已用约 40 MB / 500 MB，
   每次快照≈数据库体积 + 引用文件体积；上线前需按真实增长复核容量。
2. **定时执行**：建议独立 Cron Service（同镜像，挂同一 Volume），命令：
   ```bash
   sh -c 'cd /app && python -m app.ops.project_backup snapshot \
            --database /data/pocketscore.db --storage /data/storage \
            --backup-root /data/backups && \
          python -m app.ops.project_backup prune --apply'
   ```
   **创建 Cron Job 属于云端变更，必须单独授权。**
3. **恢复窗口**：停服务 → 把备份 `database/` 与 `storage/` 放回 `/data` → 启动 → 用 API 验证。
   现有工具会拒绝直接写 `/data`，届时需要专门的运维脚本或一次性放宽开关（**未实现**）。
4. **告警**：`storage_audit` 退出码非 0 即异常（`1` 有发现、`2` 错误），
   适合直接接监控。

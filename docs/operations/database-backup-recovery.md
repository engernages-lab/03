# 数据库备份与恢复运维手册

> 适用版本：PocketScore AI V1.1（SQLite 单实例部署）
> 工具入口：`backend/app/ops/database_backup.py`（`python -m app.ops.database_backup`）
> 本手册描述**设计与已验证行为**；未实测的能力会显式标注。

---

## 0. 为什么不能直接 `cp pocketscore.db`

数据库运行在 **WAL 模式**（`app/core/db.py` 里每个连接都执行 `PRAGMA journal_mode=WAL`）。
已提交但尚未 checkpoint 的页仍在 `pocketscore.db-wal` 里，`cp` 只复制主文件会**丢数据**。
因此备份统一走 SQLite 在线备份 API（`Connection.backup()`），它在事务边界上读取一致的快照。

---

## A. 备份

### A.1 原理

```
sqlite3.connect("file:<db>?mode=ro", uri=True)   ← 只读打开源库
    .backup(<新的空库>)                            ← 在线备份 API（含 WAL 中已提交页）
        → 临时文件 → integrity_check → foreign_key_check
        → sha256 → os.replace() 原子改名 → 写 manifest + .sha256
```

任一步失败：临时文件删除、不产出备份、命令返回非 0；**不会**留下"看起来成功"的半成品。

### A.2 运行环境

- Python 3.9+（镜像内为 3.11），仅标准库：`sqlite3`/`hashlib`/`json`/`shutil`。
- 不需要网络、不需要新的 pip 依赖。
- 读权限：数据库文件；写权限：备份目录。

### A.3 命令

```bash
cd backend

# 备份到默认目录（数据库同级 backups/，可用环境变量覆盖）
POCKETSCORE_BACKUP_DIR=/data/backups \
  python -m app.ops.database_backup backup

# 指定数据库与目录
python -m app.ops.database_backup backup \
  --database /data/pocketscore.db --backup-dir /data/backups

# 验证某个备份
python -m app.ops.database_backup verify --backup /data/backups/pocketscore-20261128-093000Z.sqlite3

# 列出（--verify 会逐个校验）
python -m app.ops.database_backup list --verify
```

### A.4 目录与命名

```
<backup_dir>/
  pocketscore-20261128-093000Z.sqlite3          # 备份本体（UTC 时间戳）
  pocketscore-20261128-093000Z.manifest.json    # 元数据
  pocketscore-20261128-093000Z.sha256           # <hash>  <filename>
```

- 时间戳为 **UTC**，同一秒重复备份会被拒绝（不覆盖历史）。
- `POCKETSCORE_BACKUP_DIR` 缺省为**数据库文件同级的 `backups/`**，即生产环境中就是
  `/data/backups`，**不会**落到源码目录。
- 备份目录是**敏感目录**：不要放进任何静态资源目录，也不要提交到 Git（`.gitignore` 已包含 `backups/`）。

### A.5 Manifest 字段

`backup_id`、`created_at_utc`、`database_name`、`database_engine`、`database_schema_version`、
`alembic_revision`、`sqlite_version`、`backup_method`（固定 `sqlite3.backup_api`）、
`backup_file`、`backup_size_bytes`、`sha256`、`integrity_check`、`foreign_key_check`、
`core_tables_present`、`backup_status`、`application_version`、`source_path`。

**不含**任何行内容、用户数据、Token、密钥。

### A.6 校验方式

```bash
# 1. manifest 中记录的哈希 vs 实际文件
python -m app.ops.database_backup verify --backup <file>

# 2. 手工核对
sha256sum <file>          # 与 .sha256 文件、manifest.sha256 三者一致
sqlite3 <file> "PRAGMA integrity_check; PRAGMA foreign_key_check;"
```

`verify` 会检查：文件存在、非空、manifest 可解析、SHA-256 匹配、
`integrity_check == ok`、`foreign_key_check` 无记录、核心表齐全、**manifest 记录的 schema version 与文件一致**。

### A.7 失败排查

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| `database file not found` | 路径错/容器未挂 Volume | 检查 `POCKETSCORE_DATABASE_URL` 与 `/data` 挂载 |
| `sqlite backup failed: database is locked` | 长事务占用 | 重试；确认没有其它进程持有写锁 |
| `integrity_check returned ...` | 源库损坏 | **立即停止**，用最近的可用备份评估恢复 |
| `foreign_key_check reported N violation(s)` | 数据不一致 | 不产出备份；先排查写入路径 |
| `backup already exists` | 同秒重复执行 | 等 1 秒或换 label |
| `could not write manifest` | 磁盘满/只读 | 清理空间或换目录 |

---

## B. 恢复

### B.1 恢复前检查

1. **确认不是在真实环境操作**：工具会拒绝 `/data` 下的目标，以及
   `POCKETSCORE_ENVIRONMENT` 为 `staging`/`production` 的任何恢复。`--force` 不会解除该保护。
2. 选备份：`list --verify`，挑 `verified: true` 且时间点合适的那份。
3. 校验：`verify --backup <file>` 必须 `ok: true`。

### B.2 命令

```bash
cd backend

# 只看计划（默认就是 dry-run）
python -m app.ops.database_backup restore \
  --backup /path/to/pocketscore-20261128-093000Z.sqlite3 \
  --target /tmp/restore-check/pocketscore.db

# 隔离目录里真正执行（目标已存在时必须 --force）
python -m app.ops.database_backup restore \
  --backup /path/to/backup.sqlite3 \
  --target /tmp/restore-check/pocketscore.db --force

# 只验证备份，不碰目标
python -m app.ops.database_backup restore --backup <file> --target /tmp/x.db --verify-only
```

### B.3 恢复流程（工具内部）

1. 目标路径过保护检查（`/data`、staging、production → 拒绝，退出码 3）。
2. 校验备份（manifest/哈希/完整性/外键/核心表/schema version）。
3. 目标不存在 → 直接写；已存在 → 打印大小与 mtime，未 `--force` 则拒绝。
4. 对现有目标做安全副本 `<target>.pre-restore-<UTC>`。
5. 复制到临时文件 → 再次验证（完整性/外键/哈希）→ `os.replace` 原子替换。
6. 替换后再次验证；失败则保留安全副本并在输出里说明。

### B.4 恢复后检查

```bash
python -m app.ops.database_backup verify --backup <restored.db>   # 无 manifest 时加 --allow-manifest-missing
sqlite3 <restored.db> "PRAGMA integrity_check; PRAGMA foreign_key_check; SELECT COUNT(*) FROM music_documents;"
```

### B.5 失败处理与回滚

- 任何一步失败：目标文件**未被修改**（原子替换前失败）或已被安全副本保留。
- 回滚：把 `<target>.pre-restore-<UTC>` 复制回原路径即可。
- 真实环境恢复（Staging/Production）**必须在专门授权的运维窗口进行**，且需停机写入：
  本工具不提供在线恢复，也不会自动重启服务。

---

## C. 运维建议

### C.1 频率

| 环境 | 建议 | 说明 |
| --- | --- | --- |
| Staging | 每日 1 次 | 仅用于演练 |
| Production | 每日 1 次 + 重大操作前手动 | 迁移、批量导入、升级前各一次 |

### C.2 保留策略

`prune` 实现祖父-父-子（GFS）：默认保留最近 **7 份每日 + 4 份每周 + 3 份每月**，
且**永远保留最新一份**。默认 dry-run：

```bash
python -m app.ops.database_backup prune                 # 只打印计划
python -m app.ops.database_backup prune --apply         # 真正删除
```

安全规则：不删数据库原文件、不删 `/data/storage`、不删没有 manifest 的文件（非本系统产物）、
不删校验失败的备份、没有有效备份时拒绝删除。

### C.3 加密

**当前未实现加密**。备份文件按**敏感数据**对待：放在 Volume 内、权限收敛、不出公网。
如需加密，建议 `age`/`gpg` 对称加密，密钥存于 Railway 变量或外部 KMS，
**绝不与备份同目录**，且必须补一条"解密 → 恢复 → 校验"的测试后才能宣称支持加密。

### C.4 异地存储

Volume 与容器在同一区域，Regional 故障会同时影响两者。建议定期把备份拉到对象存储
（S3 兼容），并保留至少一份跨区域副本。

### C.5 文件存储（重要）

**数据库备份 ≠ 业务数据备份。** `audio_assets.stored_path` 指向 `/data/storage/...`，
数据库只存路径与 `checksum_sha256`。只恢复数据库会得到"记录存在但音频缺失"的半残状态。
因此必须**同时**备份 `/data/storage`（建议 `restic`/`rclone`，按内容寻址的特性可增量同步），
并让两者使用**同一时间点**（先备份文件快照，再备份数据库，或反过来保持一致窗口）。

### C.6 演练

每季度至少一次：把最近备份恢复到隔离目录 → `verify` → 抽查记录数与关键行 →
与生产只读统计对比。**没有演练过的恢复等于没有恢复。**

### C.7 RPO / RTO

| 指标 | 数值 | 性质 |
| --- | --- | --- |
| RPO | ≤ 24 小时 | **设计目标**（每日备份）；未在 Railway 实测 |
| RTO（单库恢复） | 数分钟量级 | **设计目标**；取决于备份大小与 IO，未实测 |
| RTO（含文件存储） | 小时级 | **设计目标**；未实测 |

以上均为目标值，**不是实测结果**，不得作为 SLA 对外承诺。

---

## D. Railway 后续部署方案（本阶段未执行）

> 以下为方案，**未在任何环境实施**。

### D.1 备份目录

- 备份写入 `/data/backups`（与数据库同卷），需确认 Volume 容量：
  当前 Staging 已用约 40 MB / 500 MB，每日备份约 0.1–1 MB（取决于数据量），
  保留 14 份仍在容量内；**上线前需按真实增长速度复核**。

### D.2 定时执行

不要改动服务启动命令来自动备份（会与 API 启动耦合）。可选：

1. Railway Cron Service（独立服务，同镜像，命令：
   `sh -c 'cd /app && python -m app.ops.database_backup backup && python -m app.ops.database_backup prune --apply'`），
   需要挂同一 Volume `/data`。
2. 外部调度（GitHub Actions schedule + 通过受保护的运维端点触发）——需要额外的鉴权设计。

两种方式都涉及**新建云端资源**，必须单独授权；本阶段未创建。

### D.3 恢复窗口

Production 恢复 = 停写 → 校验 → 替换 → 启动 → 校验。
真实环境恢复工具保护会拒绝执行，届时需在生产环境显式放宽（例如新增
`POCKETSCORE_RESTORE_ALLOWED=1` 的运维开关）并在同一提交内补测试，**本阶段未实现**。

---

## E. 命令速查

```bash
cd backend
python -m app.ops.database_backup backup
python -m app.ops.database_backup verify --backup <file>
python -m app.ops.database_backup list --verify
python -m app.ops.database_backup restore --backup <file> --target <path>            # dry-run
python -m app.ops.database_backup restore --backup <file> --target <path> --force    # 隔离环境
python -m app.ops.database_backup prune            # dry-run
python -m app.ops.database_backup prune --apply
```

退出码：`0` 成功 · `1` 失败 · `2` 参数错误 · `3` 安全拒绝（真实环境/受保护路径）。

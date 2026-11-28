# PocketScore AI V1.1-C.2.3.2 · 数据库备份与恢复

> **结论：CONDITIONAL PASS**
> DBR-01 ~ DBR-09、DBR-12 ~ DBR-15 全部通过（本地实测）。
> **DBR-10（Docker 内运行）与 DBR-11（CI 远程执行）未验证**：本机无 Docker 守护进程，
> 且本阶段未获 Push 授权，所以新增的 CI 步骤只做了本地静态检查，尚未在 Actions 上跑过。
> 未触碰 Railway 任何真实数据。

---

## 1. 项目信息

| 项 | 值 |
| --- | --- |
| 项目 / 版本 | PocketScore AI / V1.1-C.2 |
| 阶段 | C.2.3.2 · Database Backup & Recovery |
| 日期 | 2026-11-28 |
| 分支 | `pocketscore-v1.1-b` |
| HEAD（开始时） | `ef6a18df717a9c1f29a130536c8c06442b81a3e1` |
| HEAD（结束时） | `ef6a18df717a9c1f29a130536c8c06442b81a3e1`（未提交） |
| `origin/pocketscore-v1.1-b` | `a94dfb9`（未变） |
| `origin/main` | `9e7cd41`（未变） |
| 工作区（开始） | 干净 |
| 工作区（结束） | 2 改 + 4 新增，**未提交** |

## 2. 审计结果

详见 [02-database-architecture-audit.md](02-database-architecture-audit.md)。

| 项 | 结论 |
| --- | --- |
| 引擎 / 表数 | SQLite / **16 张**（+`alembic_version`） |
| WAL | ✅ 启用（连接级 `PRAGMA journal_mode=WAL`） |
| 外键 | ✅ 启用（连接级 `PRAGMA foreign_keys=ON`） |
| 核心表 | `audio_assets`、`music_documents`、`music_events`、`music_tracks`、`transcription_jobs` |
| 迁移 | `0001_initial`、`0002_event_confidence` |
| 文件依赖 | `audio_assets.stored_path` / `artwork_path` → `/data/storage/audio/<sha2>/<sha256><ext>` |
| 用户表 | ❌ 不存在（无 `user_id`，与 C.2.3.1 一致） |
| 当前备份风险 | 无机制、无演练、WAL 下直接 `cp` 会丢数据、文件存储未纳入 |

## 3. 实施内容

### 3.1 新增文件

| 文件 | 作用 |
| --- | --- |
| `backend/app/ops/__init__.py` | 运维工具包（不被 API 请求路径导入） |
| `backend/app/ops/database_backup.py` | 备份 / 校验 / 恢复 / 列表 / 保留策略（CLI，仅标准库） |
| `backend/tests/test_database_backup.py` | 39 个测试（全部合成库） |
| `docs/operations/database-backup-recovery.md` | 运维手册（备份/恢复/建议/Railway 方案） |
| `reports/V1.1-C.2.3/02-database-architecture-audit.md` | 结构审计 |
| `reports/V1.1-C.2.3/03-database-backup-recovery.md` | 本报告 |

### 3.2 修改文件

| 文件 | 变更 | 说明 |
| --- | --- | --- |
| `.github/workflows/docker-verify.yml` | +14 行，1 个新步骤 | 在镜像内跑备份测试（第 14 步） |
| `.gitignore` | +4 行 | `backups/`、`*.manifest.json` |

未修改：Dockerfile、业务代码、模型、迁移、`railway.json`、任何环境变量。

### 3.3 备份架构

```text
sqlite3.connect("file:<db>?mode=ro", uri=True)
   └─ .backup(临时文件)            ← 在线 API，含 WAL 中已提交页
        ├─ size > 0
        ├─ PRAGMA integrity_check == ok
        ├─ PRAGMA foreign_key_check 为空
        ├─ sha256
        └─ os.replace → 正式文件名   ← 原子，失败不留半成品
              └─ 写 manifest + .sha256 → 再校验一次哈希
```

关键实现点：

| 点 | 做法 |
| --- | --- |
| 一致性 | `Connection.backup()`，**不用** `shutil.copy` |
| 句柄管理 | `contextlib.closing` 显式关闭（Windows 上不关闭会锁文件） |
| 原子性 | 临时名 `.partial` → `os.replace` |
| 失败清理 | 任一步异常 → 删临时文件 → 抛 `BackupError` |
| 不覆盖历史 | 同秒重复备份直接拒绝 |
| 默认目录 | `POCKETSCORE_BACKUP_DIR` 或**数据库同级 `backups/`**（不进源码目录） |

### 3.4 恢复架构

1. **目标保护**（先于一切）：`/data` 下任意路径 → 拒绝；`POCKETSCORE_ENVIRONMENT` 为 `staging`/`production` → 拒绝。
   `--force` **不解除**这两条。退出码 `3`。
2. **源校验**：manifest + SHA-256 + `integrity_check` + `foreign_key_check` + 核心表 + schema version。
3. **目标检查**：存在则打印大小/mtime，未 `--force` 拒绝（退出码 `1`）。
4. **安全副本**：`<target>.pre-restore-<UTC>`。
5. **临时复制 → 验证 → `os.replace`**（原子）。
6. **恢复后复验**：完整性/外键/哈希 + 核心表。

### 3.5 Manifest 结构

```json
{
  "manifest_version": 1,
  "backup_id": "pocketscore-20261128-075446Z",
  "created_at_utc": "2026-11-28T07:54:46+00:00",
  "database_name": "pocketscore.db",
  "database_engine": "sqlite",
  "database_schema_version": 0,
  "alembic_revision": "0002_event_confidence",
  "sqlite_version": "3.33.0",
  "backup_method": "sqlite3.backup_api",
  "backup_file": "pocketscore-20261128-075446Z.sqlite3",
  "backup_size_bytes": 53248,
  "sha256": "fa188d14…",
  "integrity_check": "ok",
  "foreign_key_check": "ok",
  "core_tables_present": true,
  "backup_status": "SUCCESS",
  "application_version": null,
  "source_path": "<db path>"
}
```

无行内容、无 Token、无密钥、无用户数据（有专门测试断言）。

### 3.6 保留策略

GFS：默认 `--daily 7 --weekly 4 --monthly 3`，**永远保留最新一份**，默认 dry-run，`--apply` 才删。

安全规则（均有测试）：不删库原文件、不删 `/data/storage`、不删无 manifest 的文件、
不删校验失败的备份、无有效备份时拒绝执行、不删到一份不剩。

## 4. 测试报告

| 项 | 值 |
| --- | --- |
| 测试文件 | `backend/tests/test_database_backup.py` |
| 本套测试数 | **39** |
| 通过 | **39** |
| 失败 | 0 |
| 跳过 | 0 |
| 命令 | `cd backend && python -m pytest tests/test_database_backup.py -q` |
| 全量回归 | `python -m pytest` → **393 passed in 42.54s**（原 354 + 新增 39） |
| Lint | `ruff check app tests` → All checks passed |

覆盖矩阵（对应任务书 §9）：

| 分类 | 覆盖的用例 |
| --- | --- |
| 备份 | 空库、正常库、WAL 已提交页、未提交事务、活跃连接、目录不存在、目录不可写、磁盘满（注入）、中断清理、manifest 写入失败、哈希不一致、损坏库拒绝成功、同时间戳拒绝覆盖 |
| 恢复 | 正常、空库、错误路径、哈希不一致、文件损坏、manifest 缺失、schema version 不匹配、外键失败、目标已存在、dry-run 不改目标、未授权覆盖拒绝、production 保护、staging 保护、`/data` 保护、恢复后一致性 |
| 保留 | dry-run 不删、越界候选生成、最新永远保留、只删计划内文件、非本系统文件不动、失败备份跳过 |
| CLI | backup+verify、verify 失败退出码、restore 拒绝退出码 3、prune 默认 dry-run |
| 端到端 | 建数据 → 备份 → 篡改 → 恢复 → 计数/行/哈希一致 |

### 4.1 隔离环境实跑（CLI，非 pytest）

合成库（1 资产 / 1 文档 / 4 音符 / 1 轨 / 1 任务）：

| 步骤 | 结果 |
| --- | --- |
| `backup` | rc=0，`pocketscore-20261128-075446Z.sqlite3`，53 248 B |
| `verify` | rc=0，`ok: true`，`problems: []` |
| `list --verify` | rc=0，count=1 |
| `prune` | rc=0，`dry_run: true`，`remove: []` |
| `restore --dry-run` | rc=0（未写目标） |
| `restore --force` | rc=0，`ok: true` |
| 恢复后计数 | 与备份前**完全一致**（4 音符、音高 `[60, 64, 67, 72]`） |

## 5. 数据完整性证明

| 指标 | 备份时 | 恢复后 |
| --- | --- | --- |
| `audio_assets` | 1 | 1 |
| `music_documents` | 1 | 1 |
| `music_events` | 4 | 4 |
| `music_tracks` | 1 | 1 |
| `transcription_jobs` | 1 | 1 |
| 音高序列 | `[60, 64, 67, 72]` | `[60, 64, 67, 72]` |
| `integrity_check` | `ok` | `ok` |
| `foreign_key_check` | 0 条 | 0 条 |
| `user_version` | 0 | 0 |
| `alembic_revision` | `0002_event_confidence` | `0002_event_confidence` |

**哈希对照（必须区分两个对象）**：

| 对象 | SHA-256（前 16 位） |
| --- | --- |
| 备份文件 | `fa188d14c0d2fbe9` |
| 恢复出的文件 | `fa188d14c0d2fbe9` ← **与备份逐字节相同** |
| 活库主文件（WAL 模式） | `b88fc646d4a3123c` ← **必然不同** |

说明：WAL 模式下活库主文件与"备份快照"不是同一份字节——已提交页可能仍在 `-wal`，
且备份 API 会写成紧凑的单文件。所以正确的等价判断是 **备份哈希 == 恢复哈希**（成立），
以及**行级内容一致**（成立）。把"活库哈希 == 备份哈希"当作正确性判据是错误的，本报告不采用。

损坏场景对照（备份后删除文档与音符）：活库 `music_documents=0`、`music_events=0`、外键违规 1 条；
恢复后回到 `1 / 4 / 0 违规`，证明恢复确实覆盖了损坏状态。

## 6. 安全报告

| 检查 | 结果 |
| --- | --- |
| 路径保护 | ✅ `/data` 前缀比较做了规范化（大小写/盘符），有 3 个测试 |
| 防覆盖 | ✅ 无 `--force` 一律拒绝，退出码 1，目标文件字节不变 |
| 删除保护 | ✅ 只删 `list_backups` 识别出的（有 manifest 且命名匹配）文件；`--apply` 才真删 |
| 日志脱敏 | ✅ 只输出路径、大小、哈希、pragma 结果，无行内容 |
| Manifest | ✅ 无行数据/音频名/密钥（测试断言 `melody.wav` 等不出现） |
| 环境隔离 | ✅ staging/production 直接拒绝，`--force` 不解除 |
| 备份目录可否被 Web 访问 | ✅ 默认在 Volume 内 `/data/backups`，不在 `frontend/dist`，无静态挂载 |
| 可否通过 API 下载备份 | ✅ 无任何路由暴露 `backups/`（67 条路由中无） |
| 路径穿越 | ✅ 备份文件名由时间戳生成，不接受用户输入；恢复目标由调用者显式给绝对路径 |
| 备份误入 Git | ✅ `.gitignore` 加 `backups/`、`*.manifest.json` |
| 并发备份 | ⚠️ 未加锁：两个进程同时备份会因同名拒绝其一（时间戳秒级），但**没有**全局锁；并发 prune 与 backup 也未互斥 |
| 真实数据保护 | ✅ 全程只碰 `tmp_path` 合成库；未连接 Railway |

## 7. Docker 与 CI

### 7.1 Docker

| 项 | 结论 |
| --- | --- |
| 工具是否进镜像 | ✅ `/app/app/ops/database_backup.py`（`COPY backend/` 覆盖） |
| 新依赖 | ❌ 无（纯标准库） |
| API 启动命令 | 未改 |
| 默认备份目录 | `/data/backups`（Volume 内），不进镜像、不自动打包 |
| 容器启动自动恢复 | ❌ 无（不存在任何启动钩子） |
| **镜像内实际运行** | ⛔ **NOT VERIFIED**（本机无 Docker 守护进程） |

### 7.2 CI 变更（未 Push、未触发）

`.github/workflows/docker-verify.yml` 新增第 14 步（在镜像安全扫描之后）：

```yaml
- name: Database backup/restore tests inside the image
  run: |
    set -euo pipefail
    docker run --rm \
      -v "$PWD/backend/tests:/tests:ro" \
      -w /app \
      -e POCKETSCORE_ENVIRONMENT=test \
      --entrypoint python \
      "$IMAGE" -m pytest /tests/test_database_backup.py -q
```

动机：`tests/` 被 `.dockerignore` 排除，但用**镜像自身的解释器**跑测试才能覆盖
镜像里的 SQLite 版本与模块布局。

本地检查：YAML 解析通过（步骤数 31 → 32），`bash -n` 通过，未访问 Railway、不需要 Secrets。
**未执行**：无 Push 授权，Actions 未触发。

## 8. Git 状态

| 项 | 值 |
| --- | --- |
| 修改 | `.github/workflows/docker-verify.yml`（+14）、`.gitignore`（+4） |
| 新增 | `backend/app/ops/`、`backend/tests/test_database_backup.py`、`docs/operations/`、`reports/V1.1-C.2.3/` |
| 分支 | `pocketscore-v1.1-b` |
| HEAD | `ef6a18d`（未变） |
| Commit | ❌ 未提交（未授权） |
| Push | ❌ 未推送 |
| Merge | ❌ 未合并 |
| main | 未触碰（`9e7cd41`） |

## 9. 未解决问题

| # | 问题 | 等级 | 影响 | 建议 |
| --- | --- | --- | --- | --- |
| 1 | 镜像内未实跑该工具 | P1 | 无法证明容器内可用（仅能证明纯标准库 + 进镜像） | 授权 Push 后由 CI 步骤 14 验证 |
| 2 | 无并发锁 | P2 | 两个备份进程可能互相干扰（不会损坏数据，同名会拒绝） | 需要时加 `fcntl`/锁文件 |
| 3 | 备份未加密 | P2 | 备份文件按敏感数据对待，泄露即全量泄露 | 见手册 C.3；实现后需补解密恢复测试 |
| 4 | 无异地副本 | P2 | 区域级故障同时损失源与备份 | 对象存储 + 跨区 |
| 5 | 文件存储未纳入自动备份 | **P1** | 只恢复库会导致音频缺失 | 必须先定文件备份方案再宣称"可恢复" |
| 6 | 无调度 | P2 | 目前只能手动跑 | Railway Cron 需单独授权 |
| 7 | 真实环境恢复被硬保护 | — | 设计使然；生产恢复需专门开关 | 未来加 `POCKETSCORE_RESTORE_ALLOWED` 并补测试 |
| 8 | RPO/RTO 未实测 | P3 | 手册中标为设计目标 | 演练后回填实测值 |

## 10. 验收判定

| 编号 | 项目 | 结果 | 说明 |
| --- | --- | --- | --- |
| DBR-01 | 数据库审计 | ✅ PASS | 16 表/16 依赖关系已确认，含文件依赖 |
| DBR-02 | 在线备份 | ✅ PASS | `sqlite3.backup` API，非文件复制 |
| DBR-03 | WAL 支持 | ✅ PASS | 有专门测试证明 WAL 中已提交页被包含 |
| DBR-04 | Manifest | ✅ PASS | 字段齐全，无敏感信息（测试断言） |
| DBR-05 | 哈希校验 | ✅ PASS | 备份哈希 == 恢复哈希，篡改被检出 |
| DBR-06 | 完整性 | ✅ PASS | `integrity_check` / `foreign_key_check` 均实测 |
| DBR-07 | 恢复工具 | ✅ PASS | dry-run + 隔离恢复均实跑 |
| DBR-08 | 防覆盖 | ✅ PASS | 无 `--force` 拒绝，字节不变 |
| DBR-09 | 保留策略 | ✅ PASS | dry-run 默认，删除保护有测试 |
| DBR-10 | Docker | ⚠️ **NOT VERIFIED** | 无本地 Docker；命令已在镜像内就绪 |
| DBR-11 | CI | ⚠️ **NOT VERIFIED** | 步骤已加，未 Push 未执行 |
| DBR-12 | 安全审计 | ✅ PASS | 见 §6（并发锁为 P2 已记录） |
| DBR-13 | 运维文档 | ✅ PASS | 手册含 A–D 全部要求 |
| DBR-14 | 真实环境保护 | ✅ PASS | 未连接 Railway，未读写真实数据 |
| DBR-15 | Git 边界 | ✅ PASS | 未提交、未推送、未合并、未部署 |

### 最终结论

```text
CONDITIONAL PASS
```

- **已达成**：备份/恢复/校验/保留四项能力在隔离环境实测通过（39 测试 + 一次完整 CLI 端到端），
  数据一致性有哈希与行级双重证明，真实数据零接触。
- **未达成**：DBR-10（镜像内运行）与 DBR-11（CI 执行）需要 Docker 守护进程或 Push 授权，
  本阶段两者都没有。**不得**据此宣称容器内与 CI 已验证。
- **进入 C.2.3.3 的条件**：不满足"全部 PASS"。建议先完成以下之一：
  1. 授权 Push 触发 CI（步骤 14 会给出镜像内实测结果），或
  2. 本地安装 Docker 后手动验证同一条命令。
  此外建议先确定 `/data/storage` 的文件备份方案（问题 #5），否则"可恢复"只覆盖数据库。

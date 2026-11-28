# PocketScore AI V1.1-C.2.3.3 · 文件存储与数据持久性

> **结论：CONDITIONAL PASS**
> 核心目标已用真实业务链路证明：**创建项目 → 上传合成音频 → 真实 Basic Pitch 扒谱 →
> 联合快照 → 删除音频 → 联合恢复 → 通过 API 重新打开原项目并读出原乐谱**。
> 未达成项只有两个，且都因环境限制：**ST-11（镜像内运行）** 与 **ST-12（CI 远程执行）**，
> 本机无 Docker 守护进程且未获 Push 授权。Railway 真实数据零接触。

---

## 1. 项目信息

| 项 | 值 |
| --- | --- |
| 项目 / 版本 | PocketScore AI / V1.1-C.2 |
| 阶段 | C.2.3.3 · Storage & Data Durability |
| 日期 | 2026-11-28 |
| 分支 | `pocketscore-v1.1-b` |
| HEAD（开始 = 结束） | `ef6a18df717a9c1f29a130536c8c06442b81a3e1`（未提交） |
| 工作区（开始） | 干净 |
| 工作区（结束） | 2 改 + 6 新增，未提交 |
| `origin/main` | `9e7cd41`（未变） |
| `origin/pocketscore-v1.1-b` | `a94dfb9`（未变） |

## 2. 存储架构审计

详见 [04-storage-architecture-audit.md](04-storage-architecture-audit.md)。

| 项 | 结论 |
| --- | --- |
| 目录 | `<storage>/audio/<sha2>/<sha><ext>`、`artwork/<sha>.<ext>`、`uploads/`（临时）、`midi/`（中间） |
| 内容寻址 | ✅ 文件名主干 = 内容 SHA-256，天然去重 + 自校验 |
| `audio_assets.stored_path` | 相对路径，`<storage>/<stored_path>` |
| `audio_assets.artwork_path` | **URL** `/static/artwork/<sha>.jpg`，需前缀转换 |
| 写入顺序 | 文件先落盘（`os.replace`）→ 再写数据库 |
| 由此性质 | 正常路径不会出现"有记录无文件"；DB 提交失败留孤儿（无害） |
| 已发现缺陷 | `delete_asset` 不检查共享引用（P2）；`absolute_path` 无包含性校验（P1） |

## 3. 实施内容

### 3.1 新增文件

| 文件 | 行数 | 作用 |
| --- | --- | --- |
| `backend/app/ops/storage_audit.py` | 353 | 存储完整性审计（scan/verify/orphans/missing/report） |
| `backend/app/ops/project_backup.py` | 724 | 联合快照 / 校验 / 恢复 / 列表 / 保留 |
| `backend/tests/test_storage_audit.py` | 157 | 12 个审计测试 |
| `backend/tests/test_project_backup.py` | 269 | 20 个快照/恢复/锁/保留测试 |
| `backend/tests/test_project_restore_e2e.py` | 189 | 1 个真实业务端到端测试 |
| `docs/operations/storage-backup-recovery.md` | — | 运维手册（A–G） |
| `reports/V1.1-C.2.3/04-storage-architecture-audit.md` | — | 结构审计 |
| `reports/V1.1-C.2.3/04-storage-data-durability.md` | — | 本报告 |

### 3.2 修改文件

| 文件 | 变更 |
| --- | --- |
| `.github/workflows/docker-verify.yml` | 步骤 14 扩展为跑 4 个运维测试文件（+7 行，挂载 fixtures） |
| `.gitignore` | C.2.3.2 已加 `backups/`、`*.manifest.json`（本阶段沿用） |

未修改：Dockerfile、API 路由、ORM 模型、迁移、`railway.json`、前端。

### 3.3 存储审计工具

| 能力 | 实现 |
| --- | --- |
| 引用扫描 | 读 `audio_assets.stored_path` / `artwork_path`，解析成相对路径 |
| 缺失检测 | 引用存在但文件不在 |
| 孤儿检测 | 磁盘上有、无任何引用（`uploads/`/`midi/` 排除） |
| 哈希校验 | 文件名主干 vs 实际 SHA-256 |
| 越界检测 | `resolve()` 后必须仍位于存储根（含符号链接解析） |
| 重复引用 | 同一路径被多条记录引用（**不**误判为孤儿） |
| Artwork | URL → 文件映射后单独统计缺失 |
| 输出 | 结构化 JSON + 计数汇总，无文件内容 |

### 3.4 联合快照（一致性核心）

```
1. 取文件锁 <backup_root>/.snapshot.lock   （O_CREAT|O_EXCL，900s 后视为陈旧可接管）
2. 先做 SQLite 在线备份 → 得到时间点 T 的一致数据库
3. 从"备份文件"里读 audio_assets 引用       ← 关键：不是从活库读
4. 逐个复制引用文件，边写边算 SHA-256，复制后再复算
5. 校验：源哈希 == 目标哈希 == 文件名主干
6. 数据库引用缺失 / 哈希不符 → 整个快照 FAILED，删除暂存目录
7. 写 storage/manifest.json + joint-manifest.json + snapshot.sha256
8. os.replace(暂存目录 → 正式目录) 原子发布
```

> 不声称"数据库与文件在同一原子事务"。本设计用**引用集合来自快照本身**消除时间窗口：
> 快照之后新增的文件与本次备份无关，快照引用的文件若已消失则备份必然失败。

### 3.5 联合恢复

```
1. 目标保护（/data、staging、production → 拒绝，--force 不解除）
2. 校验快照：manifest 哈希、数据库哈希+完整性+外键、每个文件哈希与大小、引用⊆清单
3. 目标非空 → 需 --force，且先留 <target>.pre-restore-<UTC> 安全副本
4. 恢复到 <target>/database/pocketscore.db 与 <target>/storage/...
5. 恢复后复验：完整性、外键、每条引用在恢复树中命中
6. 原子目录切换发布；失败则回滚并删除暂存
```

### 3.6 并发控制

| 机制 | 说明 |
| --- | --- |
| 锁文件 | `O_CREAT\|O_EXCL` 原子创建，POSIX/Windows 通用 |
| 陈旧接管 | 锁年龄 > 900s 视为崩溃残留，自动接管（有测试） |
| 冲突行为 | 锁被占用 → 退出码 `3`，不排队、不覆盖 |
| 备份期间源文件变化 | 复制前后各算一次哈希，不一致 → 失败 |

### 3.7 文件一致性机制

- 内容寻址文件名即期望哈希 → 任何内容替换都会被检出。
- 快照清单记录 `record_id` 与 `column`，可回溯到具体数据库字段。
- 恢复后强制"数据库引用 ⊆ 恢复文件"校验。

## 4. 联合备份结果（真实运行）

| 项 | 值 |
| --- | --- |
| Snapshot ID | `pocketscore-snapshot-20261128-082108Z-f7cace` |
| 状态 | **SUCCESS** |
| 数据库文件大小 | 249 856 B |
| 数据库 SHA-256 | `7525ee8095b74f3157eeeff1fa316569764bfe631e5ecce3e04ed08109941206` |
| 文件总数 | 1 |
| 文件总大小 | 79 424 B |
| 音频 SHA-256 | `f4824273ba04a1afbc3946327507097e4af507d0cb675a1c3dcc45fa55ec51f6` |
| joint-manifest SHA-256 | `d87f3fd027e478de03409b215f41690d4232149f127660805e121ea8222166b8` |
| consistency | `database_references_verified: true`，`missing_files: 0`，`unreferenced_files: 0`，`hash_mismatches: 0` |
| storage verification | `ok` |
| integrity_check / foreign_key_check | `ok` / `ok` |

文件条目：

```json
{
  "relative_path": "audio/f4/f4824273…wav",
  "file_size_bytes": 79424,
  "sha256": "f4824273…",
  "media_category": "audio",
  "record_id": "39914e448448",
  "column": "stored_path",
  "backup_status": "SUCCESS"
}
```

## 5. 联合恢复结果

| 项 | 值 |
| --- | --- |
| 恢复前审计 | `ok: true`，1 文件，0 缺失，0 孤儿，0 哈希不符 |
| 模拟丢失 | 删除 `audio/f4/f482…wav`，删除后 `waveform` 接口返回 **422**（证明引用真的失效） |
| dry-run | `ok: true`，**目标目录未创建** |
| 实际恢复 | `ok: true`，7 步全部通过 |
| 恢复文件 | `audio/f4/f482…wav`，79 424 B，SHA-256 与备份**完全一致** |
| 数据库完整性 | `ok` |
| 文件完整性 | 1/1 哈希一致 |
| 业务一致性 | 项目/资产/任务 ID 全部不变，音符 4 个，音高 `[60,64,67,72]` 不变 |
| 重复创建 | ❌ 无：恢复库中 `music_documents` 计数 = **1** |
| 恢复后审计 | `ok: true`，0 缺失，0 孤儿，0 哈希不符 |

## 6. E2E 验证报告（真实业务链路）

| # | 步骤 | 结果 | 证据 |
| --- | --- | --- | --- |
| 1 | 创建扒谱项目 | ✅ PASS | upload 202 → `job_cd9231e5ee97` |
| 2 | 上传合成音频 | ✅ PASS | asset `39914e448448`，79 424 B |
| 3 | 音频存储 | ✅ PASS | `audio/f4/f4824273…wav`，SHA-256 `f4824273…` |
| 4 | **真实 Basic Pitch 扒谱** | ✅ PASS | status `completed`，`method: basic_pitch`，confidence 0.6569，4 个音符 |
| 5 | 联合备份 | ✅ PASS | snapshot `…082108Z-f7cace` SUCCESS |
| 6 | 数据库备份 | ✅ PASS | 249 856 B，`7525ee80…`，integrity `ok` |
| 7 | 文件备份 | ✅ PASS | 1 文件 79 424 B，哈希一致 |
| 8 | 模拟文件丢失 | ✅ PASS | 文件删除，`waveform` → 422 |
| 9 | 联合恢复 | ✅ PASS | dry-run 无副作用 + 实际恢复成功 |
| 10 | **重新打开项目** | ✅ PASS | `GET /documents/{id}` 200，ID 相同 |
| 11 | 音频验证 | ✅ PASS | `GET /assets/{id}` 200、`/waveform` 200、哈希与大小一致 |
| 12 | 乐谱验证 | ✅ PASS | `GET /transcription/jobs/{id}/result` 200，4 音符 `[60,64,67,72]`；`GET /notation/{id}/both` 200 |
| 13 | 最终一致性 | ✅ PASS | 存储审计 clean、快照复验 `ok: true`、文档数 = 1 |

**关键 ID（同一次运行）**：`job_cd9231e5ee97` · asset `39914e448448` · document `aea66215c911`。

## 7. 测试报告

| 项 | 值 |
| --- | --- |
| 新增测试 | **33**（12 审计 + 20 快照/恢复 + 1 端到端） |
| 新增测试通过 | **33** |
| 新增测试失败 | 0 |
| 新增测试跳过 | 0 |
| 后端全量 | **426 passed, 1 skipped** in 78.79 s |
| 跳过原因 | 符号链接测试（Windows 无权限创建 symlink） |
| Lint | `ruff check app tests` → All checks passed |
| 前端 | 未改动，未运行（无影响） |
| Docker | ⛔ **未验证**（本机无 Docker 守护进程） |
| 远程 CI | ⛔ **未验证**（未获 Push 授权） |

命令：

```bash
cd backend
python -m pytest tests/test_storage_audit.py tests/test_project_backup.py tests/test_project_restore_e2e.py -q
python -m pytest -q
```

CLI 冒烟（真实子进程）：

| 命令 | 退出码 | 结果 |
| --- | --- | --- |
| `project_backup snapshot` | 0 | `SUCCESS` |
| `project_backup verify` | 0 | `ok: true` |
| `project_backup list` | 0 | count = 1 |
| `project_backup restore --dry-run` | 0 | 目标未创建 |
| `project_backup restore --force` | 0 | 数据库 + 文件均恢复 |
| `project_backup restore --target /data/x` | **3** | `REFUSED` |

## 8. 安全报告

| 编号 | 检查 | 结果 | 证据 |
| --- | --- | --- | --- |
| ST-SEC-01 | 路径穿越 | ✅ | `is_within()` 用 `resolve()` + `normcase` 前缀比较；有测试 |
| ST-SEC-02 | 符号链接 | ✅ | 解析后判定；测试（本机跳过创建，逻辑已覆盖） |
| ST-SEC-03 | 文件覆盖 | ✅ | 快照目录不可重名；恢复需 `--force` 且先留安全副本 |
| ST-SEC-04 | 哈希不匹配 | ✅ | 快照/校验/恢复三处都查；有 3 个测试 |
| ST-SEC-05 | 并发修改 | ✅ | 锁 + 复制前后哈希对比；锁与陈旧接管有测试 |
| ST-SEC-06 | 部分备份 | ✅ | 失败即删暂存，不发布 |
| ST-SEC-07 | 部分恢复 | ✅ | 暂存目录 → 全量校验 → 原子切换 |
| ST-SEC-08 | 孤儿文件 | ✅ | 只报告，不删除 |
| ST-SEC-09 | 缺失文件 | ✅ | 快照直接 FAILED；审计单独列出 |
| ST-SEC-10 | API/静态暴露 | ✅ | 备份默认在 `/data/backups`，不在 `frontend/dist`，无路由 |
| ST-SEC-11 | 日志泄露 | ✅ | 只输出路径、大小、哈希、计数 |
| ST-SEC-12 | 清理误删 | ✅ | 以整个 snapshot 目录为单位；只删有 joint-manifest 的目录 |
| ST-SEC-13 | 环境误操作 | ✅ | `/data` + staging/production 拒绝，`--force` 不解除（3 个测试） |
| ST-SEC-14 | 备份敏感 | ✅ | 文档标注敏感；`.gitignore` 已排除 |
| ST-SEC-15 | 引用失效 | ✅ | 恢复后逐条引用校验 |

## 9. 未解决问题

| # | 问题 | 等级 | 影响 | 阻塞发布 | 建议 |
| --- | --- | --- | --- | --- | --- |
| 1 | 镜像内未实跑 | P1 | 无法证明容器内可用（代码纯标准库，已进镜像） | 否（需 CI 验证） | 授权 Push 后由步骤 14 验证 |
| 2 | CI 未远程执行 | P1 | 同上 | 否 | 同上 |
| 3 | 备份未加密 | P2 | 备份泄露 = 全量数据泄露 | 否 | 见手册 F |
| 4 | 无异地副本 | P2 | 区域故障同时损失源与备份 | 否 | 对象存储 + 跨区 |
| 5 | 无定时任务 | P2 | 只能手动备份 | 否 | Railway Cron 需单独授权 |
| 6 | 无在线热恢复 | P2 | 生产恢复需停写窗口 | 否 | 设计使然，文档已声明 |
| 7 | `delete_asset` 不查共享引用 | P2 | JSON 内嵌引用可能悬空 | 否 | 后续加引用计数 |
| 8 | `absolute_path` 无包含性校验 | P1 | DB 被篡改时可能读越界 | 否 | 建议后续加校验 |
| 9 | RPO/RTO 未实测 | P3 | 手册中标为设计目标 | 否 | 演练后回填 |
| 10 | 单卷单副本 | P1 | Volume 故障即全失 | 否 | 依赖 #4 异地备份 |

## 10. Git 与部署状态

| 项 | 值 |
| --- | --- |
| 分支 | `pocketscore-v1.1-b` |
| HEAD | `ef6a18d`（未变） |
| 修改 | `.github/workflows/docker-verify.yml`（+21）、`.gitignore`（+4，C.2.3.2） |
| 新增 | `backend/app/ops/`、`backend/tests/test_{database,storage,project}_*.py`、`docs/operations/`、`reports/V1.1-C.2.3/` |
| Commit | ❌ 未提交 |
| Push | ❌ 未推送 |
| Merge | ❌ 未合并（`main` = `9e7cd41` 未动） |
| Railway | ❌ 未部署、未改变量、未碰 Volume、未连数据库 |

## 11. 验收判定

| 编号 | 项目 | 结果 | 说明 |
| --- | --- | --- | --- |
| ST-01 | 文件架构审计 | ✅ PASS | 目录、类型、引用、生命周期全部落到源码行 |
| ST-02 | 完整性扫描 | ✅ PASS | 缺失/孤儿/哈希/越界/Artwork 全部可检出（12 测试） |
| ST-03 | 文件备份 | ✅ PASS | 流式复制 + 双重哈希 |
| ST-04 | 文件恢复 | ✅ PASS | 独立可用，哈希一致 |
| ST-05 | 联合 Manifest | ✅ PASS | 统一 snapshot ID |
| ST-06 | 联合一致性 | ✅ PASS | 引用取自快照 DB，缺失即失败 |
| ST-07 | 并发安全 | ✅ PASS | 锁 + 陈旧接管 + 变更检测（有测试） |
| ST-08 | 恢复保护 | ✅ PASS | `/data`、staging、production 三处拒绝 |
| ST-09 | 联合恢复 | ✅ PASS | 7 步全过，原子发布 |
| ST-10 | 文件生命周期 | ✅ PASS | 顺序已确认；共享引用缺陷记为 P2 |
| ST-11 | Docker | ⚠️ **NOT VERIFIED** | 无本地 Docker |
| ST-12 | CI | ⚠️ **NOT VERIFIED** | 未授权 Push |
| ST-13 | 安全审计 | ✅ PASS | 15 项逐条有证据 |
| ST-14 | 运维文档 | ✅ PASS | A–G 全覆盖 |
| ST-15 | 真实数据保护 | ✅ PASS | 全程临时目录 |
| ST-16 | Git 边界 | ✅ PASS | 未提交/推送/合并/部署 |
| **ST-17** | **业务端到端恢复** | ✅ **PASS** | 真实上传 + 真实推理 + 真实恢复 + API 重开项目 |

### 最终结论

```text
CONDITIONAL PASS
```

- **核心目标达成**：一次性真实跑通「创建项目 → 上传 → 真实扒谱（4 音符）→ 联合快照 →
  删除音频 → 联合恢复 → API 重开项目 → 音高与哈希全部一致，且未重复创建」。
  ST-17 是 PASS，不是模拟。
- **未达成**：ST-11（镜像内运行）与 ST-12（CI 远程执行）。两者都需要外部条件，
  与 C.2.3.2 的 DBR-10/DBR-11 同类。
- **能否进入 C.2.3.4**：核心数据持久性目标已验证，但按本阶段"全部关键项通过才 PASS"的标准，
  不能算 PASS。建议先授权 Push 让 CI 跑一次（步骤 14 会同时覆盖备份与存储两套测试），
  即可把 ST-11/ST-12 转成实测。

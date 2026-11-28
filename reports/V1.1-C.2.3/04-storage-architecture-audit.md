# PocketScore AI V1.1-C.2.3.3 · 文件存储架构审计

> 只读审计。结论来自源码阅读 + 一次真实上传（隔离临时目录）产生的目录/数据库事实，
> 未连接任何 Railway 环境。

## 1. 存储目录结构（实测）

以隔离环境真实上传 `melody.wav`（79 424 B）后观察：

```
<storage>/
└── audio/
    └── f4/
        └── f4824273ba04a1afbc3946327507097e4af507d0cb675a1c3dcc45fa55ec51f6.wav
```

配置派生路径（`app/core/config.py`）：

| 属性 | 路径 |
| --- | --- |
| `storage_path` | `<POCKETSCORE_STORAGE_DIR>`（测试默认 `./data/storage`，生产 `/data/storage`） |
| `audio_path` | `<storage>/audio` |
| `artwork_path` | `<storage>/artwork` |
| `upload_path` | `<storage>/uploads`（临时） |
| `midi_path` | `<storage>/midi`（中间产物） |

## 2. 文件类型清单

| 类型 | 是否持久化 | 依据 |
| --- | --- | --- |
| 原始音频 `audio/<sha2>/<sha><ext>` | ✅ 业务数据 | 内容寻址写入，`audio_assets.stored_path` 引用 |
| 封面 `artwork/<sha>.jpg|png` | ✅ 业务数据 | `_store_artwork()`，`audio_assets.artwork_path` 引用 |
| `uploads/` 临时文件 | ❌ 可丢弃 | 流式上传中转，成功后 `os.replace` 移走 |
| `midi/` | ❌ 可重建 | MIDI 导入中间产物 |
| 导出文件（SVG/TXT/MIDI） | ❌ 按需生成 | 由 `notation`/`midi` 路由实时生成，不落盘持久化 |

## 3. 数据库文件引用关系（逐字段）

| 表.字段 | 形态 | 解析 | 唯一标识 | 删除联动 | 恢复要求 |
| --- | --- | --- | --- | --- | --- |
| `audio_assets.stored_path` | 相对路径 `audio/xx/<sha>.wav` | `<storage>/<stored_path>` | 文件名 = SHA-256 | `delete_asset()` 先删库后删文件 | 必须与 DB 一起恢复 |
| `audio_assets.artwork_path` | URL `/static/artwork/<sha>.jpg` | 去前缀 → `<storage>/artwork/<sha>.jpg` | 文件名 = 资产 SHA-256 | 同上 | 必须与 DB 一起恢复 |

`absolute_path(record) = storage_path / record.stored_path` —— **未做包含性校验**，
若数据库被写入 `../` 路径则可能越界读取（见 §6 风险 R3）。

## 4. 文件生命周期（真实顺序）

```
上传请求
  → 流式写入 <storage>/uploads/（或系统临时目录），累计大小上限
  → 校验扩展名（7 种）
  → 计算 SHA-256 → 查重
       ├─ 命中：直接返回既有资产（同一内容只存一份）
       └─ 未命中：
            → os.replace 到 audio/<sha2>/<sha><ext>     ← 文件先落盘
            → 探测（soundfile/ffmpeg/wave）+ 可解码校验
            → 写 audio_assets 行 → 提交                    ← 数据库后提交
            → 失败则删除刚落盘文件（补偿）
```

**关键性质**：正常路径下不会出现"数据库有记录但文件不存在"。
数据库提交失败会留下孤儿文件（内容寻址，可被后续同内容上传复用）。

## 5. 当前存储风险

| # | 风险 | 等级 | 说明 |
| --- | --- | --- | --- |
| R1 | 无文件级备份 | **P0** | 数据库备份不含文件；只恢复库会"记录在、音频无" |
| R2 | 无一致性校验 | P1 | 无工具能发现缺失/孤儿/哈希不符（本阶段已补） |
| R3 | `absolute_path` 未校验包含性 | P1 | DB 被篡改时可能读越界；写入路径安全，读取路径依赖数据可信 |
| R4 | `delete_asset` 不检查共享引用 | P2 | 若其它记录（JSON 内嵌）引用同一资产，删除后引用悬空 |
| R5 | 上传失败留孤儿 | P3 | 无害但占用空间，需定期审计清理 |
| R6 | 无加密 | P2 | 备份与原始音频均为明文，依赖 Volume 权限 |
| R7 | 单卷单副本 | P1 | Volume 故障 = 业务文件全失 |

## 6. 数据库与文件一致性风险

| 场景 | 结果 | 检测手段 |
| --- | --- | --- |
| 文件被误删 | 播放/波形 422，记录仍在 | `storage_audit missing` |
| 数据库回滚 | 孤儿文件 | `storage_audit orphans` |
| 文件被覆盖 | 哈希与文件名不符 | `storage_audit verify`（hash_mismatches） |
| 路径被改写为 `../x` | 可能越界读 | `storage_audit out_of_root` |
| 两个记录引用同一文件 | 不是孤儿 | `duplicates`（只报告） |
| Artwork 缺失 | 封面 404 | `artwork_missing` |

## 7. 推荐联合备份方案（已实现）

1. **以数据库快照为引用来源**：先做 SQLite 在线备份，再从备份里读文件引用。
2. **成组发布**：数据库与文件同处一个 snapshot 目录，原子目录切换。
3. **逐文件 SHA-256**：复制时计算 + 复制后复算 + 与内容寻址文件名比对。
4. **一致性判定**：数据库引用缺失 → 快照 FAILED，不发布。
5. **锁与保留**：文件锁防并发；GFS 保留以整个 snapshot 为单位，数据库与文件永不分离。

实现：`backend/app/ops/project_backup.py`，文档 `docs/operations/storage-backup-recovery.md`。

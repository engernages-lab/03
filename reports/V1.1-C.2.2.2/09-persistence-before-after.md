# V1.1-C.2.2.2 · 09 重启前后持久化对比（Phase 9–11）

- **日期**：2026-11-27
- **脚本**：`scripts/deploy/verify-staging-persistence.py`（快照）、
  `scripts/deploy/compare-staging-persistence.py`（逐字段比较）
- **证据**：`artifacts/before-restart.json`、`artifacts/after-restart.json`、
  `artifacts/persistence-diff.json`、`artifacts/after-redeploy.json`、
  `artifacts/persistence-diff-redeploy.json`

---

## 1. 快照方法

快照包含九类数据，全部经真实 API 获取：

1. `project.document_id / title / artist / asset_id / track_count`
2. `notes.count / pitch_sequence / onset_sequence / duration_sequence / velocity_sequence`
3. `notation.grid / jianpu`（两种谱面统计）
4. `audio.sha256 / size_bytes`（**通过 `GET /audio/assets/{id}/stream` 下载真实字节后自行计算 SHA256**）
5. `health`、`ready` 的完整响应

音频哈希是关键：只查数据库记录无法证明"音频文件还在"。

## 2. 重启执行

```bash
railway restart --service pocketscore-api --yes
```

| 项 | 值 |
| --- | --- |
| 重启对象 | `pocketscore-api`（staging） |
| Volume | 未删除、未替换 |
| 恢复时间 | **31.4 s** 后 `/ready` 返回 200 |
| 新进程证据 | `/ready.checks.model.load_seconds = 1.191`（重新加载），`inference.completed = 0`（计数归零） |

## 3. 逐字段对比（重启前 → 重启后）

| 字段 | 重启前 | 重启后 | 一致 |
| --- | --- | --- | --- |
| Project ID | `6a0c696a7289` | `6a0c696a7289` | ✅ |
| Project Name | `C2-2-2-STAGING-REGRESSION-20261127T105532Z` | 同上 | ✅ |
| Audio Asset ID | `5b520fb5abda` | `5b520fb5abda` | ✅ |
| Note Count | 4 | 4 | ✅ |
| Pitch Sequence | `[60, 64, 67, 72]` | `[60, 64, 67, 72]` | ✅ |
| Onset Sequence | `[0.0, 0.75, 1.5, 2.5]` | `[0.0, 0.75, 1.5, 2.5]` | ✅ |
| Duration Sequence | `[0.75, 0.75, 0.75, 0.75]` | 同上 | ✅ |
| Velocity Sequence | `[97, 96, 101, 97]` | 同上 | ✅ |
| Audio SHA256 | `622501298bd9…8016c` | `622501298bd9…8016c` | ✅ |
| Audio File Size | 11 385 | 11 385 | ✅ |
| Grid Stats | `notes=3, unmapped=1, …` | 同 | ✅ |
| Jianpu Stats | `notes=4, unmapped=1, …` | 同 | ✅ |

比较脚本输出：`identical: true`，`health_after: true`，`ready_after: true`。

## 4. 追加验证：完整重新部署（可选）

随后执行了一次**重新部署**（不是重启）：

```bash
railway up --ci --service pocketscore-api
# Deployment 492d9fa7-50b8-4444-9ec5-90324b58069e  SUCCESS @ 2026-11-27T11:00:25Z
```

再次快照并与**重启前**基线对比（`artifacts/persistence-diff-redeploy.json`）：
12 个字段**全部一致**，音频 SHA256 不变。

即：数据在
①进程重启、②镜像重建并换容器 两种情况下都完整存活。

## 5. 这证明了什么 / 没证明什么

**证明**：

- SQLite 数据库确实写在 `/data`（Volume），换容器后仍在
- 上传的 MP3 音频字节完整（SHA256 一致），不是"数据库有记录但文件没了"
- 项目文档的音符、速度、时值、力度逐项未变
- 服务重启后能自行恢复到 ready（31.4 s）

**未证明**：

- 跨 Railway 项目/区域的迁移（未测）
- 并发写入时的持久化一致性（单客户端顺序测试）
- Volume 容量上限触顶行为（当前 36 MB / 500 MB）

## 6. 结论

| 编号 | 检查 | 结果 |
| --- | --- | --- |
| DB-01 | SQLite 写入 | ✅ `/ready` database ok |
| DB-02 | 项目保存 | ✅ |
| DB-03 | 项目读取 | ✅ |
| DB-04 | 音频文件写入 | ✅ 11 385 字节 |
| DB-05 | 服务重启 | ✅ 31.4 s 恢复 |
| DB-06 | 重启后项目读取 | ✅ 全字段一致 |
| DB-07 | 重启后音频读取 | ✅ SHA256 一致 |
| DB-08 | 数据关联完整 | ✅ 文档 ↔ 资产 ↔ 谱面 |

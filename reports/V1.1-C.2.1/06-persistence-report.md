# V1.1-C.2.1 · 06 持久化与优雅退出报告

> 两项均 **EXECUTED ✅**（GitHub Actions run `45819026067`）

---

## 1. Volume 持久化（步骤 23，59 s，success）

执行 `scripts/docker/verify-persistence.sh`：

```text
容器 #1（pocketscore-c21-<RUN_ID>-c1）→ wait-ready → 上传+扒谱
  → 记录 document_id / asset_id
  → 对 {事件数, 标题, checksum_sha256, 大小} 求 SHA-256 → state_digest_before
docker stop --time 30 → docker rm        ← 真正删除容器
容器 #2（-c2，新容器）→ 同一 volume → wait-ready
  → GET /documents/{id} → 200
  → GET /audio/assets/{id} → 200
  → GET /audio/assets?limit=5 → total ≥ 1
  → 同一摘要 → state_digest_after
断言：两个摘要完全一致，否则退出码 1
```

| 检查 | 结果 |
| --- | --- |
| 容器是否真的被删除 | ✅ `docker rm` 后由新 `docker run` 创建 |
| 是否复用同一卷 | ✅ `-v ${VOLUME}:/data` |
| 文档重建后可读 | ✅ 断言 HTTP 200 |
| 资产重建后可读 | ✅ 断言 HTTP 200 |
| 资产总数 | ✅ `total ≥ 1` |
| 一致性 | ✅ SHA-256 摘要相等（`identical: true`） |
| 数据库是否被自动重置 | ❌ 未重置（文档与资产仍在） |

产物：`persistence-result.json`、`before/after-restart-document.json`、
`before/after-restart-asset.json`。

## 2. Linux 优雅退出（步骤 24，21 s，success）

执行 `scripts/docker/verify-graceful-shutdown.sh`：

```text
启动独立容器 → wait-ready → docker stop --time 30
→ 读取 .State.ExitCode / .State.OOMKilled
→ 日志必须命中 shutting down | finished server process | application shutdown complete
→ 日志出现 Traceback 判失败
→ 退出码必须 ∈ {0, 143}
```

| 检查 | 结果 |
| --- | --- |
| `docker stop` 完成 | ✅ 21 s 内（远小于 25 s 预算） |
| 退出码 | ✅ ∈ {0, 143}（断言通过，具体值见 `graceful-shutdown.txt`） |
| SIGTERM 被 uvicorn 接收 | ✅ 日志命中关闭标记（否则脚本失败） |
| Traceback | ✅ 无 |
| OOMKilled | ✅ false |
| 孤立进程 | ⚠️ 未单独检测（容器随 `docker rm` 移除；Docker 的 PID 命名空间保证容器内进程不会存活） |

## 3. 明确未验证的部分

**"推理任务进行中收到 SIGTERM 的完整恢复行为"没有验证。**

- 本次 `docker stop` 发生在容器就绪、无正在执行的推理任务时；
- 当前实现的推理线程不可中断（见 C.2 报告），中途停机会让作业停在中间状态，
  下次启动时任务状态保持原样（可解释，但未实测）；
- 该限制已写入 C.2 的 `inference_limiter.py` 注释与本报告，不声称已解决。

## 4. 清理（步骤 28，success）

`cleanup-test-resources.sh` 只删除 `pocketscore-c21-<RUN_ID>*` 的容器与本次创建的卷，
未执行任何 `docker system prune`，不影响 runner 上其他作业的资源。

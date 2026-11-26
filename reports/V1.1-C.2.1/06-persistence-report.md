# V1.1-C.2.1 · 06 持久化与优雅退出报告

> **Docker Volume 持久化：NOT EXECUTED**（无 Docker 运行时）
> **Linux SIGTERM 优雅退出：NOT EXECUTED**（同上）

---

## 1. 脚本设计（CI 将执行）

### 1.1 `verify-persistence.sh`

```text
容器 #1（名字含 RUN_ID）→ 等待 ready → 上传+扒谱（复用 verify-transcription.py）
  → 记录 document_id / asset_id / 状态摘要哈希
  → docker stop → docker rm      ← 真正删除容器，不是重启
容器 #2（同名规则，新容器）→ 同一 volume → 等待 ready
  → GET 文档（比较事件数、标题）
  → GET 资产（比较 checksum_sha256、size_bytes）
  → GET /audio/assets?limit=5（total ≥ 1）
  → 摘要哈希必须完全一致
→ 写入 persistence-result.json → 不一致则退出码 1
```

关键点：

| 要求 | 实现 |
| --- | --- |
| 必须真正删除容器 | `docker rm` 后由 `docker run` 新建（`verify-persistence.sh` 第 2、4 段） |
| 必须复用同一卷 | `-v "${VOLUME}:/data"`，卷在测试开始前 `docker volume create` |
| 数据库不能重置 | 断言重启后 `document`/`asset` 仍 200，且 `assets_total ≥ 1` |
| 一致性可判定 | 对 `{events 数, 标题, checksum, 大小}` 求 SHA-256 比较 |

### 1.2 `verify-graceful-shutdown.sh`

```text
启动独立容器 → 等待 ready → 计时 docker stop --time 30
→ 读取 .State.ExitCode / .State.OOMKilled
→ 抓取日志，要求出现 shutting down / finished server process 等标记
→ 日志中出现 Traceback 判失败
→ 退出码必须 ∈ {0, 143}
→ 记录 stop 耗时与最后 40 行日志
```

## 2. 已有的等价证据（不是容器）

C.2 阶段在宿主进程上验证过（`scripts/smoke_deployment.py`）：

| 项 | 结果 |
| --- | --- |
| 卷目录内数据库 | 4096 B，重启后可读 |
| 音频文件 | `storage/audio/f4/<sha256>.wav` 保留 |
| 文档 | 重启后 `GET /documents/{id}` 200，4 事件 |
| 资产总数 | 1 |

**局限**：这是"同一台机器上的进程重启"，不含 Docker 层（卷驱动、容器命名空间、PID 1）。

## 3. 优雅退出：为什么必须在 Linux 容器里测

C.2 报告已记录：Windows 上 `send_signal(SIGTERM)` 等价于 `TerminateProcess`，
ASGI 关闭钩子不会执行。因此"优雅退出"只能在 ubuntu runner 的容器里验证，
本报告不能给出结论。

**未验证的子项**（CI 会给出答案）：

1. `exec uvicorn` 是否使 uvicorn 成为 PID 1；
2. `docker stop` 是否在 25 s 预算内完成；
3. 退出码是否 0/143；
4. 是否存在 OOMKilled；
5. 关闭期间是否有 Traceback。

**明确不声称**：没有验证"推理任务进行中收到 SIGTERM 的完整恢复行为"。
当前实现中推理线程不可中断，任务状态会在下次启动时保持原样（可解释的中间态）。

## 4. 关闭条件

绿色 `docker-verify` 运行，产物包含：

- `persistence-result.json` 且 `identical: true`、`document_http_after: 200`
- `graceful-shutdown.txt` 且 `container_exit_code ∈ {0,143}`、日志含 shutdown 标记
- 清理步骤只删除 `pocketscore-c21-<RUN_ID>*` 资源

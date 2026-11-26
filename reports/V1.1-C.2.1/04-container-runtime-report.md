# V1.1-C.2.1 · 04 容器运行报告

> **Container Runtime: NOT EXECUTED**（无 Docker 运行时；CI 未触发）

---

## 1. 状态

| 项 | 值 |
| --- | --- |
| 容器启动 | ⛔ 未执行 |
| PORT 注入（8000 / 8123） | ⛔ 未执行（脚本已就绪） |
| `/health` | ⛔ 未执行 |
| `/ready` | ⛔ 未执行 |
| 容器日志 | ⛔ 无 |

## 2. CI 会执行的容器测试（可复核）

工作流与脚本已经把每一步写成可独立运行的命令：

| 步骤 | 脚本 | 断言 |
| --- | --- | --- |
| 非默认端口 | 工作流内联 | 容器 `-e PORT=8123 -p 8123:8123`，`/health` 200；并断言容器内 **8000 端口未监听**（否则说明 PORT 被忽略） |
| 默认端口 + 卷 | 工作流内联 | `-e PORT=8000 -v volume:/data` |
| 就绪 | `scripts/docker/wait-ready.sh` | 轮询 `/health` 与 `/ready`，最多 300 s；`ready==true` 且 `model.status=ready`、`storage.ok=true`、`inference.capacity>=1`；超时打印容器日志并失败 |
| 运行时快照 | 工作流内联 | `runtime-info.json`（镜像、启动时间、重启次数）+ `docker stats` 一行 |

`wait-ready.sh` 的判定是**硬失败**：模型未预热不会被当成 ready。

## 3. C.2 的本地等价结果（不是容器，仅供参考）

C.2 用同一启动命令在宿主进程上验证过：

```text
startup 9.04 s → /ready 200 (model ready, load 2.663 s, warmup 2.044 s)
→ upload 201 → job completed 4 notes → restart → document still readable
```

这证明应用层逻辑正确，但**不能**替代容器证据（端口映射、卷挂载、PID 1 信号、镜像内依赖都不同）。

## 4. 关闭条件

绿色 `docker-verify` 运行，产物包含：

- `health-check.json`（200）
- `ready-check.json`（`ready: true`，`model.status == "ready"`）
- `runtime-info.json`
- 日志中无 `Traceback`

当前不具备该证据。

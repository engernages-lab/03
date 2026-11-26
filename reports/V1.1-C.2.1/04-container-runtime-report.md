# V1.1-C.2.1 · 04 容器运行报告

> **Container Runtime: EXECUTED ✅**（GitHub Actions run `45819026067`）

---

## 1. 端口注入

| 测试 | 做法 | 结果 | 耗时 |
| --- | --- | --- | --- |
| 非默认端口 | `-e PORT=8123 -p 8123:8123` | ✅ `/health` 200；并**断言容器内 8000 未监听** | 21 s |
| 默认端口 + 卷 | `-e PORT=8000 -p 8000:8000 -v <volume>:/data` | ✅ 启动成功 | <1 s |

关键点：如果 Dockerfile 仍然硬编码 8000，`PORT=8123` 的容器不会在 8123 应答，
测试会直接失败。本次通过，说明 `exec ... --port "${PORT:-8000}"` 生效。

## 2. 健康与就绪

| 检查 | 脚本 | 结果 | 耗时 |
| --- | --- | --- | --- |
| `/health` | 工作流内联 + `wait-ready.sh` | ✅ 200 | 含在 21 s |
| `/ready` | `wait-ready.sh` | ✅ `ready: true`；`model.status=ready`、`storage.ok=true`、`inference.capacity ≥ 1` | 21 s（含模型加载 + 预热） |

`wait-ready.sh` 是硬判定：模型未完成预热时 `/ready` 不会返回 `true`，
脚本最多等 300 s，超时会打印容器日志并退出码 1（不会无限等待）。

## 3. 运行时快照

步骤 19（2 s）写出 `docker-verification/runtime-info.json`（镜像名、启动时间、重启次数）
与 `container-stats.txt`（`docker stats` 一行 CPU/内存）。

具体数值位于 CI 产物中；本机无 GitHub 凭据无法读取（见 §5），未编造。

## 4. 日志

- 容器日志在失败时才导出（`Container logs on failure` 步骤，本次 skipped = 没有失败）。
- `graceful-shutdown.txt` 中保留了最后 40 行关闭日志（见 06 报告）。
- 全程日志中无 `Traceback`（`verify-graceful-shutdown.sh` 断言）。

## 5. 无法读取的数值（如实说明）

GitHub 的 artifact/日志下载接口需要仓库权限：

```text
GET /repos/engernages-lab/03/actions/artifacts/15117441072/zip → 401 Requires authentication
GET /repos/engernages-lab/03/actions/jobs/<id>/logs           → 403 Must have admin rights
```

因此本报告只能给出**步骤级**证据（全部 success + 耗时），
镜像大小、`ready` 返回的 `load_seconds`/`warmup_seconds`、`docker stats` 数值
保留在产物 `docker-verification-45819026067`（15 KB，保留 14 天）中。
用户可在 run 页面直接下载查看，无需向我提供任何凭据。

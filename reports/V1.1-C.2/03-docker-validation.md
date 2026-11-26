# V1.1-C.2 · 03 Docker 验证报告（Docker Validation）

> **状态：NOT EXECUTED — 本机不具备 Docker 运行时。**

---

## 1. 为什么不执行

```text
$ docker --version
docker : 无法将“docker”项识别为 cmdlet、函数、脚本文件或可运行程序的名称

$ docker info
（同上，命令不存在）

$ wsl --status
未安装适用于 Linux 的 Windows 子系统

$ podman --version / nerdctl --version
（命令不存在）

$ [System.IO.DriveInfo]::GetDrives()
C:\  113.3 GB free / 400 GB
D:\  199.2 GB free / 551.6 GB     # 空间充足，不是空间问题
```

| 依赖 | 状态 |
| --- | --- |
| Docker Engine | ❌ 未安装 |
| Docker CLI | ❌ 未安装 |
| WSL2 | ❌ 未安装 |
| 磁盘 | ✅ 199 GB 可用 |

安装 Docker Desktop 需要管理员权限与重启，超出本阶段授权范围（且属于"修改开发环境"，
不属于项目代码）。因此**镜像构建、容器启动、容器内健康检查均未执行**。

按验收标准 §10.3，"Docker 无法构建/容器无法启动"属于 BLOCKED 条件；
本报告**不把静态检查当作 Docker 验证通过**。

---

## 2. 替代验证：容器等价语义（真实进程）

为尽可能接近容器行为，执行 `scripts/smoke_deployment.py`，它复刻了镜像里的
**同一条启动命令**与**同一组环境变量**，并使用一个独立目录充当 `/data` 卷：

```text
python -m uvicorn app.main:app --host 127.0.0.1 --port $PORT \
       --timeout-graceful-shutdown 10
```

环境：`POCKETSCORE_ENVIRONMENT=staging`、`MODEL_PRELOAD=true`、
`DATABASE_URL=sqlite:///<volume>/pocketscore.db`、`STORAGE_DIR=<volume>/storage`、
`CORS_ORIGINS=https://engernages-lab.github.io`、`ALLOW_PRIVATE_NETWORK_SOURCES=false`、
`MAX_UPLOAD_MB=25`。

### 2.1 实测结果（staging 模式，端口 8134）

```json
{
  "startup_seconds": 9.04,
  "ready_status": 200,
  "ready": {
    "ready": true,
    "model": {
      "ok": true, "status": "ready", "version": "0.4.0",
      "load_seconds": 2.663, "warmup_seconds": 2.044, "optional": false
    },
    "storage": { "ok": true },
    "inference": {
      "ok": true, "capacity": 1, "active": 0, "queued": 0,
      "max_queued": 0, "completed": 0, "busied": 0, "timed_out": 0
    }
  },
  "upload_status": 201,
  "job_http": 200,
  "job_state": "completed",
  "events": 4,
  "inference_seconds": 2.61,
  "model_load_seconds": 2.663,
  "queue_wait_seconds": 0.0,
  "db_bytes": 4096,
  "stored_files": [
    "storage\\audio\\f4\\f4824273ba04a1afbc3946327507097e4af507d0cb675a1c3dcc45fa55ec51f6.wav"
  ],
  "restart_seconds": 9.75,
  "after_restart_document_status": 200,
  "after_restart_events": 4,
  "data_survived": true,
  "after_restart_assets": 1,
  "restart_ready": true
}
```

### 2.2 逐项对照验收表

| 验收项 | 标准 | 本机结果 | 判定 |
| --- | --- | --- | --- |
| 镜像构建 | 成功 | **未执行**（无 Docker） | ⛔ NOT VERIFIED |
| 容器启动 | 成功 | **未执行**；等价进程启动成功 | ⚠️ 部分 |
| PORT 注入 | 生效 | ✅ `PORT=8134` → 服务监听 8134，`/health` 200 | ✅ |
| 健康检查 | 200 | ✅ `/health` 200（2.9 s 内） | ✅ |
| Ready 检查 | 模型就绪后 200 | ✅ `ready: true`，model `ready` | ✅ |
| 数据库 | 可连接 | ✅ `db_bytes: 4096`，文档写入后重启仍可读 | ✅ |
| 数据目录 | 可读写 | ✅ 卷目录内创建 `pocketscore.db` | ✅ |
| 音频目录 | 可读写 | ✅ `storage/audio/f4/<sha256>.wav` | ✅ |
| AI 模型 | 可加载 | ✅ `load_seconds: 2.663`，`version 0.4.0` | ✅ |
| 音频推理 | 返回真实音符 | ✅ 上传 → 作业 `completed` → **4 个音符** | ✅ |
| 容器重启 | 数据未丢失 | ✅ 重启后文档 200、4 事件、1 资产 | ✅ |
| 优雅退出 | SIGTERM 正常 | ⚠️ **未验证**（见 §3） | ⚠️ |

---

## 3. 优雅退出的诚实说明

Windows 上 `subprocess.send_signal(SIGTERM)` 映射为 `TerminateProcess`，进程不会执行
ASGI shutdown 钩子，因此：

- `termination_exit_code = 1`（Windows 强制终止语义，不是应用崩溃）
- `graceful_shutdown_verified = false`

镜像内使用的是 `exec uvicorn ... --timeout-graceful-shutdown 25`，在 Linux 容器中
SIGTERM 会走 uvicorn 的优雅关闭路径。**该路径只能由真实容器验证**，本阶段未验证。

数据面影响：即使被强行终止，SQLite（WAL）与内容寻址音频文件在重启后完整可读 —— 这一点已实测。

---

## 4. 镜像层面的静态核对（不是验证）

| 检查 | 结论 |
| --- | --- |
| 基础镜像 | `python:3.11-slim` |
| 系统依赖 | `libsndfile1`、`ca-certificates`（FFmpeg 由 imageio-ffmpeg wheel 提供） |
| 安装顺序 | `requirements` → `app` → `alembic` → `frontend/dist`（后者不存在时构建会失败，需先 `npm run build`） |
| 端口 | `EXPOSE 8000`；实际监听 `$PORT` |
| 卷 | `VOLUME ["/data"]`，`chmod 0777 /data` |
| 健康检查 | `urllib` 探 `/health`，`start-period` 90 s（覆盖模型预热） |
| PID 1 | `sh -c exec uvicorn` → uvicorn 为 PID 1，信号可直达 |

---

## 5. 要完成本报告，需要什么

1. 安装 Docker Desktop（或提供 WSL2 + dockerd），或在 **GitHub Actions** 上执行
   （ubuntu runner 自带 Docker）。
2. 执行：`docker build -f backend/Dockerfile -t pocketscore-api .`（先 `npm run build` 生成 `frontend/dist`）。
3. 执行：`docker run --rm -p 8080:8080 -e PORT=8080 -e POCKETSCORE_ENVIRONMENT=staging ... -v psdata:/data pocketscore-api`
4. 重复 §2.1 的 10 项检查，并额外验证 `docker stop` 的优雅退出日志。

在拿到上述证据前，**本报告不判定 Docker 验证通过**。

# V1.1-C.2 · 01 环境审计（Environment Audit）

- **日期**：2026-11-26
- **阶段**：V1.1-C.2 · Railway Production Deployment & Backend Launch
- **性质**：审计先于修改；本文件记录修改前的真实状态

---

## 1. 项目根目录

`D:\AI扒谱工具`（Windows 11，PowerShell，Node v24.22.0，Python 3.9.13 venv）

## 2. Git 状态（修改前）

```text
$ git branch --show-current
pocketscore-v1.1-b
$ git log --oneline -1
8ae2b28 docs(V1.1-C.1): production deployment architecture audit (read-only)
$ git status --short | wc -l
0                       # 工作区干净
$ git branch -vv
  main               5315e3d [origin/main: ahead 1]
  pocketscore-v1.1-a a928983
* pocketscore-v1.1-b 8ae2b28
$ git remote -v
origin  git@github.com:engernages-lab/03.git
$ git rev-parse --short origin/main
9e7cd41
```

| 检查项 | 结果 |
| --- | --- |
| 分支 | `pocketscore-v1.1-b` ✅ 与任务书一致 |
| HEAD | `8ae2b28`（C.1 报告提交），**不是** 任务书写的 `afe0086` |
| 差异说明 | 任务书写的 `afe0086` 是 V1.1-B 提交；C.1 在其上新增了一个仅含文档的提交 `8ae2b28`。无业务代码差异。 |
| 工作区 | 干净，0 未跟踪（`git status --porcelain` 为空） |
| 分支关系 | `9e7cd41 → 5315e3d → a928983 → afe0086 → 8ae2b28`，线性 |
| 远程 | `origin/main = 9e7cd41`；本地领先 4 个提交（均未推送） |

**结论**：可以安全继续，无需切分支、无需 reset。

## 3. 当前 Dockerfile（修改前）

`backend/Dockerfile`：`python:3.11-slim`，`CMD ["python","-m","uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]`。

**问题（C.1 已记录，本次确认）**：

1. 端口硬编码 `8000`，不读 Railway 的 `PORT`。
2. 镜像内 Python 3.11，而本地 venv 与 `requirements.txt` 面向 3.9 → 依赖解析可能不同。
3. `COPY frontend/dist` 无容错：dist 不存在时构建失败。
4. 无 `--timeout-graceful-shutdown`；`CMD` 为数组形式但无 `exec` 语义问题（数组形式已是 exec）。

## 4. Railway 配置（修改前）

**不存在**。仓库无 `railway.json` / `railway.toml` / `nixpacks.toml` / 根 `Dockerfile`。

→ Railway 默认只在仓库根找 Dockerfile，而它在 `backend/`：**部署必然失败**。

## 5. 后端启动入口

`backend/app/main.py::create_app()`，模块级 `app`。
启动钩子：`settings.ensure_directories()` → `init_db()` → 日志。**无密钥校验、无模型预热**。

## 6. Git 与 Docker 运行环境（关键）

```text
$ docker --version
docker: 命令不存在（docker / docker.exe 均未安装）
$ docker info
同上
$ wsl --status
未安装适用于 Linux 的 Windows 子系统
$ railway --version
命令不存在
$ [System.IO.DriveInfo]::GetDrives()
C:\  113.3 GB free / 400 GB
D:\  199.2 GB free / 551.6 GB
```

| 能力 | 状态 |
| --- | --- |
| Docker Engine / CLI | ❌ **不可用** |
| WSL2 后端 | ❌ 未安装 |
| podman / nerdctl | ❌ 未安装 |
| Railway CLI | ❌ 未安装 |
| 磁盘空间 | ✅ 充足（D: 199 GB） |

**影响**：`C.2-07 本地 Docker 构建验证` 在本机**无法执行**。
按验收标准 §10.3，这构成 **BLOCKED 级未验证项**，不得用静态检查冒充。
本阶段改为执行**等价语义的宿主进程验证**（同一启动命令、`PORT` 注入、独立"卷"目录、
SIGTERM 后重启），并明确标注其与容器验证的差别。

## 7. 前端 API 配置（修改前）

- 唯一入口 `frontend/src/lib/api.ts`：`VITE_API_BASE_URL`，空值即同源。
- `vite.config.ts`：`build.sourcemap: true`（生产也发布 sourcemap）。
- 无"API 地址缺失"提示：GitHub Pages 构建在未配置变量时会静默请求 `/<repo>/api/v1/...` 并 404。

## 8. 生产环境变量读取（修改前，含实测失败）

`Settings`（pydantic-settings 2.2.1，前缀 `POCKETSCORE_`）。实测：

```text
$ POCKETSCORE_CORS_ORIGINS=https://engernages-lab.github.io uvicorn app.main:app
pydantic_settings.sources.SettingsError:
  error parsing value for field "cors_origins" from source "EnvSettingsSource"
  ← json.decoder.JSONDecodeError: Expecting value: line 1 column 1
```

**生产阻断缺陷**：pydantic-settings 2.2.1 会在校验器之前对 `List[str]` 字段做 JSON 解码，
因此**逗号分隔的 CORS 值会让进程在导入阶段直接崩溃**。而 `.env.example` 与
`docker-compose.yml` 用的正是逗号分隔写法 → 一旦按文档部署就起不来。

## 9. Basic Pitch 模型加载方式（修改前）

`transcription/inference.py::run_model()` 传 **路径** 给 `predict()`；上游 `run_inference()`：

```python
if isinstance(model_or_model_path, Model):
    model = model_or_model_path
else:
    model = Model(model_or_model_path)   # ← 每个请求重建 ONNX 会话
```

实测重建成本 0.028–0.073 s（模型 230 KB），非致命但纯浪费，且无预热。

## 10. 上传与推理资源（修改前）

| 项 | 状态 |
| --- | --- |
| 上传读取方式 | `data = await file.read()` 全量入内存，之后才比对 200 MB |
| 请求体上限 | 无 |
| 推理并发 | 无限制（anyio 线程池默认 40） |
| 推理超时 | 无 |
| 限流 | 无 |

## 11. 结论

| 结论 | 内容 |
| --- | --- |
| 可安全继续 | ✅ 分支/工作区正常，无冲突修改 |
| P0 待修 | Dockerfile 端口、Railway 配置缺失、CORS 解析崩溃 |
| P1 待修 | 模型重复初始化、无并发上限、上传全量入内存、生产弱密钥 |
| 本机阻塞项 | Docker / WSL / Railway CLI 均不可用 → 容器与云端验证无法执行 |

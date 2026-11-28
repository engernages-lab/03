# PocketScore AI V1.1-C.2.3.4.3 · 供应链审计

> 扫描日期：2026-11-28 · 分支 `pocketscore-v1.1-b` · HEAD `ef6a18d`

## 1. 工具与版本

| 工具 | 版本 | 结果 |
| --- | --- | --- |
| Python | 3.9.13（`backend/.venv`） | 项目运行时 |
| `pip check` | 内置 | ✅ `No broken requirements found.` |
| `pip-audit` | 未安装 | ❌ 安装尝试因网络阻塞中止（>10 分钟无进展），**Python CVE 扫描未执行** |
| `npm audit` | npm 随 Node 24.22.0 | ✅ 执行成功 |
| Docker | 无守护进程 | ❌ 镜像扫描 / SBOM 未执行 |

> 没有伪造扫描结果：`pip-audit` 不可用即标注 NOT VERIFIED，不使用"排除规则"制造全绿。

## 2. Python 依赖

`backend/requirements.txt`（范围锁定，非精确 pin）：

```
fastapi>=0.110,<0.116        uvicorn[standard]>=0.29,<0.31
python-multipart>=0.0.9      pydantic>=2.7,<2.10
pydantic-settings>=2.2,<2.6  SQLAlchemy>=2.0,<2.1
greenlet>=3.0,<3.3           alembic>=1.13,<1.14
```

`requirements-model.txt`：`basic-pitch` 以 `--no-deps` 安装，闭包在 `requirements.txt` 中显式列出。

| 检查 | 结果 |
| --- | --- |
| 依赖冲突 | ✅ 无（`pip check`） |
| CVE 扫描 | ⛔ **NOT VERIFIED**（工具不可用） |
| 可复现构建 | ⚠️ 范围锁定意味着不同时间构建可能得到不同补丁版本 → 建议后续引入精确 pin + hash（见整改） |
| 安装脚本风险 | ✅ 模型包 `--no-deps` + 构建期断言（无 TensorFlow）已固化 |

## 3. Node 依赖（`npm audit`，真实结果）

| 包 | 严重度 | 影响面 | 是否进入运行时镜像 | 修复 |
| --- | --- | --- | --- | --- |
| `react-router-dom` | **moderate** | **生产依赖**，GHSA-337j-9hxr-rhxg（SSR hydration `deserializeErrors` 任意构造器注入） | 是（打进 SPA bundle） | 需升到 v7（semver major） |
| `tinypool` | critical | 仅 dev（vitest 依赖） | **否**（镜像只 `COPY --from=frontend /web/dist`） | 随 vitest 升级 |
| `vitest` | critical | 仅 dev（UI server 任意文件读取） | **否** | v5 |
| `vite` | high | 仅 dev（`.map` 路径穿越、launch-editor UNC） | **否** | v8（major） |
| `vitest-node` | moderate | 仅 dev | **否** | 随 vitest |

**生产风险评估（react-router-dom）**：该 advisory 依赖 **SSR hydration** 路径；
本项目是纯客户端 SPA（Vite `build` 产出静态资源，无 SSR、无 `hydrateRoot` 服务端数据），
因此**当前不可利用**。但不能因此宣称"无风险"：升级到大版本会破坏路由写法，属于需要单独回归的改动。

**dev-only 提示**：`npm audit --omit=dev` 仍报 react-router 2 条，其余 4 条只在 dev 依赖中出现。
镜像不包含 `node_modules`，所以 critical 的 tinypool/vitest 不会进入生产镜像。

## 4. Docker 基础镜像

| stage | 原 | 现 | 说明 |
| --- | --- | --- | --- |
| frontend | `node:20-slim` | `node:20-slim@sha256:2cf067cfed83d5ea958367df9f966191a942351a2df77d6f0193e162b5febfc0` | 构建期，产物只取 `dist` |
| runtime | `python:3.11-slim` | `python:3.11-slim@sha256:7032841967d07aa3353905945dc186901c89b6b319c61425f4439f677a4a8a34` | 生产运行 |

digest 由 Docker Hub registry manifest 查询获得（`Docker-Content-Digest`），
为 **multi-arch index** 摘要，因此在 amd64/arm64 上都能解析。
**未验证**：本机无 Docker，未实际 `docker pull` 这两个 digest。

## 5. GitHub Actions

全部由浮动 major tag 改为 40 位 commit SHA，并保留版本注释：

| Action | 引用 | 版本 |
| --- | --- | --- |
| `actions/checkout` | `11d5960a326750d5838078e36cf38b85af677262` | v4.2.2 |
| `actions/setup-node` | `49933ea5288caeca8642d1e84afbd3f7d6820020` | v4.4.0 |
| `docker/setup-buildx-action` | `8d2750c68a42422c14e847fe6c8ac0403b4cbd6f` | v3.10.0 |
| `docker/build-push-action` | `10e90e3645eae34f1e60eeb005ba3a3d33f178e8` | v6.18.0 |
| `actions/upload-artifact` | `ea165f8d65b6e75b540449e92b4886f43607fa02` | v4.6.2 |

静态测试 `test_runtime_config.py` 会断言：任何 `uses:` 必须是 40 位 SHA、必须带版本注释、
不得出现浮动 tag。SHA 由 GitHub API `git/ref/tags/<tag>` 解析（annotated tag 已二次解引用）。

**未验证**：未推送，因此这些 SHA 尚未在真实 runner 上执行过。

## 6. SBOM

| 方案 | 评估 | 状态 |
| --- | --- | --- |
| `docker buildx build --sbom=true` | 需要 containerd image store / registry 导出，会改变现有 `load: true` 构建路径 | **未启用**（NOT VERIFIED） |
| Syft | 未安装，且无 Docker 无法扫描镜像 | NOT VERIFIED |
| Python 依赖清单 | `pip freeze` 可作为轻量清单，但不是标准 SBOM | 可选 |

结论：**SBOM 能力未建立**，标记 NOT VERIFIED。建议在 CI 增加独立的 `anchore/sbom-action`
或 `docker buildx --sbom` 步骤，并在报告中声明"生成 SBOM ≠ 消除漏洞"。

## 7. 未修复漏洞汇总

| # | 包 | 严重度 | 层 | 处置 |
| --- | --- | --- | --- | --- |
| 1 | `react-router-dom` | moderate | 生产 | 记录；需单独大版本升级 + 路由回归（建议 C.2.4 前） |
| 2 | `vite` | high | dev | 记录；dev 工具链升级随前端依赖整体更新 |
| 3 | `vitest` / `tinypool` | critical | dev | 记录；不进入镜像，但 CI 开发机需升级 |
| 4 | Python 依赖 | unknown | 生产 | **未扫描**，需在可联网环境执行 `pip-audit` |

## 8. 整改建议

1. 在可联网的 CI 中加 `pip-audit --strict`（首次可 `|| true` 出报告，第二次起阻断）。
2. `requirements.txt` 改为精确 pin（或 `pip-compile` 生成带 hash 的 lock）。
3. `react-router` 升级列入独立任务，配路由回归。
4. 前端 dev 依赖升级到一个无 critical 的组合。
5. 增加 SBOM 步骤。
6. 建立"基础镜像 digest 季度复核"流程（当前 pin 需要定期刷新）。

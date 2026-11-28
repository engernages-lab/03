# V1.1-C.2.3.4.3 · CI 补充验证与授权分支推送报告

- 阶段：V1.1-C.2.3.4.3（CI Supplementary Verification & Authorized Branch Push）
- 日期：2026-11-28
- 分支：`pocketscore-v1.1-b`
- 起点提交：`a94dfb9`（V1.1-C.2.2.2.3 远端验证通过点）
- 终点提交：`ed9e947`
- 最终 CI 运行：`46161802762`（workflow `docker-verify`，结论 **success**，45 步全绿）
- 说明：验证对象是代码提交 `ed9e947`；本报告本身是纯文档提交，`reports/**` 不在工作流 `push.paths` 触发范围内，因此不会触发新的运行，也不需要新的运行来证明文档正确。
- 上游约束：不推 `main`、不合并、不开 PR、不改 Railway 生产环境、不动真实 Staging 卷、不伪造 PASS

---

## 1. 执行摘要

本阶段完成三件事：

1. **把未提交的工作整理成两个语义清晰的提交并推送**到 `origin/pocketscore-v1.1-b`（main 保持 `9e7cd41` 未动）。
2. **在真实 GitHub Actions runner 上跑通补充验证**：非 root 运行时（UID/GID 10001）、全新卷读写、历史卷兼容（三种模式）、SQLite WAL/SHM、音频 SHA256、备份写入、重启持久化、SIGTERM 优雅退出，以及镜像内 11 个测试文件的真实执行。
3. **补齐供应链证据**：Trivy 镜像扫描 + CycloneDX SBOM、npm audit（全部依赖与生产依赖）、pip-audit（尽力项，见 §8）。

过程中在 CI 里**真实暴露并修复了 5 个缺陷**（其中 3 个只会在非 root 容器里出现），这些缺陷在本地环境下均不可见（§6）。

### 最终判定：**CONDITIONAL PASS**

| 维度 | 判定 | 依据 |
| --- | --- | --- |
| 非 root 运行时 + 卷兼容 | **PASS** | CI 步骤 15/16/17/18 全绿（真实 runner、真实 Docker） |
| 历史卷兼容（根属主遗留卷） | **PASS** | 模式 B 实测「可读不可写」，模式 C 迁移后哈希不变且可写 |
| 数据持久化（WAL/SHM/音频/备份/重启/SIGTERM） | **PASS** | CI 步骤 15、36、37 全绿 |
| 镜像内测试执行 | **PASS** | 步骤 19（ops 51–70 s）、步骤 20（security 9–17 s）全绿 |
| 依赖与镜像扫描 | **PASS（部分）** | npm audit + Trivy + SBOM 有产物并被校验；**pip-audit NOT VERIFIED** |
| 分支推送 | **PASS** | `a94dfb9..dfbb9b1`，无 `--force` |

> **CONDITIONAL PASS 的唯一原因**：CI 环境下 `pip-audit` 无法产出报告（两种安装路径、两种模式均失败，见 §8），因此「Python 依赖漏洞扫描」记为 `NOT VERIFIED`，不计为通过。其余项均有真实 CI 证据。

---

## 2. 授权范围与本阶段实际动作

用户明确授权：整理并提交 C.2.3.2 / C.2.3.3 / C.2.3.4.1 / C.2.3.4.2 / C.2.3.4.3 的未提交工作；推送 `origin/pocketscore-v1.1-b`；触发 Actions；读取真实 CI 日志/产物；修 CI 问题并再推送。

实际执行（全部在授权范围内）：

| 动作 | 结果 |
| --- | --- |
| 提交未跟踪/已修改文件 | 2 个提交（`1e1d4ff` ops、`bd45034` security）+ 后续 CI 修复提交 |
| 推送到特性分支 | 8 次，均为快进（fast-forward），无 `--force` |
| 触发 GitHub Actions | 12 次真实运行（含失败与修复） |
| 读取 CI 证据 | 运行/步骤级状态、check-run annotations、artifact 名称与体积 |
| 修改产品代码 | 仅 1 处运行时修复（JIT 缓存目录）+ 1 处后台任务健壮性修复（§6.3） |

**未做**（保持禁止）：未推 `main`、未合并、未开 PR、未改 Railway 环境变量/卷/部署、未对真实 Staging 卷执行 `chown`、未写入任何密钥、未 `reset --hard` / `clean -fd`、未删除任何测试。

---

## 3. 环境与基线事实

| 事实 | 值 |
| --- | --- |
| 本地 OS / 分支 | Windows · `pocketscore-v1.1-b` |
| 本地 Docker/Podman | **不可用**（`docker` 不在 PATH，无 WSL 发行版） |
| 本地后端解释器 | `backend/.venv`（Python 3.9.13） |
| 镜像基础 | `python:3.11-slim`（`@sha256:7032…`）、构建阶段 `node:20-slim@sha256:2cf0…` |
| GitHub 远端 | `engernages-lab/03`（公开仓库） |
| 推送通道 | SSH 22 被本机代理拦截（`198.18.1.63:22` → `Connection closed`），改走 `ssh.github.com:443`，同一仓库、同一分支 |
| 匿名可读性 | 运行/步骤状态可读（200）；运行日志 403、artifact 内容 401 → 无法读取日志正文（§7.3 说明应对方式） |

**回归基线（本地，本阶段结束时）**：

```
581 passed, 3 skipped, 4 warnings in 95.67s
ruff check app  -> All checks passed
```

与上一阶段基线（581/3）一致，新增测试全部计入。

---

## 4. 提交与推送

### 4.1 提交清单（`a94dfb9..dfbb9b1`）

| 提交 | 类型 | 内容 |
| --- | --- | --- |
| `1e1d4ff` | feat(ops) | 数据库备份/恢复、存储审计、联合快照（C.2.3.2 + C.2.3.3），含 72 个测试与 2 篇运维文档 |
| `bd45034` | feat(security) | 存储边界、限流、CORS、安全响应头、非 root 镜像、供应链固定（C.2.3.4.1/4.2/4.3） |
| `6ab98eb` | fix(ci) | 卷造数改用 root；CI fixture 放宽限流；容器内 pytest 关闭缓存插件 |
| `ac31779` | fix(ci) | 卷兼容拆成 A/B/C 三步；修正 WAL 断言顺序 |
| `0f1944a` | fix(ci) | 镜像内 pytest 失败改发 annotation |
| `990f738` | fix(ci) | 镜像内 pytest 拆 ops / security 两步 + 可写 HOME |
| `7f9ba66` | fix(tests) | 修复 `parents[2]` 在浅路径（`/tests/x.py`）下的 IndexError |
| `9ede764` | chore(ci) | 转写步骤失败诊断（公开信号） |
| `8ef8aa5` | chore(ci) | 诊断扩展到建任务/运行 |
| `d1508d9` | chore(ci) | 指纹化容器存活、表数量、traceback 末行 |
| `b776ad4` | chore(ci) | 记录传输异常类型与失败后健康状态 |
| `5129393` | fix(runtime) | JIT 缓存目录可写 + 后台任务异常不再重置连接 |
| `4fc9d09` | ci | SBOM 与审计产物强制校验 |
| `c06f952` | ci | pip-audit 解析失败降级 `--no-deps` |
| `46b3bd8` | ci | pip-audit 改走 `uvx`/`pipx` |
| `dfbb9b1` | ci | pip-audit 转为尽力项并显式告警 |
| `ed9e947` | ci | pip-audit 重试链超时收紧（**最终验证提交**） |

改动规模：`46 files changed, 9922 insertions(+), 24 deletions(-)`。

### 4.2 推送记录

| 时间（UTC） | 提交 | 结果 |
| --- | --- | --- |
| 12:14 | `bd45034` | `a94dfb9..bd45034` ✅ |
| 12:24 | `6ab98eb` | `bd45034..6ab98eb` ✅ |
| 12:28 | `ac31779` | `6ab98eb..ac31779` ✅ |
| 12:38 | `0f1944a` | `ac31779..0f1944a` ✅ |
| 12:48 | `990f738` | `0f1944a..990f738` ✅ |
| 13:03 | `7f9ba66` | `990f738..7f9ba66` ✅ |
| 13:19–15:36 | `9ede764`…`dfbb9b1` | 逐次快进 ✅ |

推送后复核：`origin/main = 9e7cd419…`（未变）、`origin/pocketscore-v1.1-b = ed9e947…`。

---

## 5. CI 验证矩阵（真实 runner）

工作流 `docker-verify`，45 个步骤。

### 5.1 构建与镜像

| 项 | 步骤 | 证据 |
| --- | --- | --- |
| 前端生产构建 | 8 Production build | 通过 |
| Pages base path | 9 Verify frontend artefacts | 通过 |
| Dockerfile COPY vs .dockerignore | 10 Verify build context | 通过 |
| 镜像构建 | 12 Build image | 通过（~28 s，含 gha 缓存） |
| 镜像内容（依赖/模型/ffmpeg/dist） | 13 | 通过 |
| 镜像安全扫描 | 14 Image security scan | 通过 |

### 5.2 非 root 运行时（本阶段核心）

| 检查 | 结果 | 证据形式 |
| --- | --- | --- |
| 进程 UID/GID = 10001 | ✅ | 步骤 15 内 `os.getuid() == 10001`，失败即 `exit 1` |
| `/data` 不存在时自动创建 | ✅ | 全新命名卷 |
| 全新卷可读写（storage/backups） | ✅ | 写入 + 回读，含删除 |
| SQLite WAL/SHM 生成 | ✅ | 连接打开期间 `-wal` 存在断言 |
| 音频 SHA256 落盘正确 | ✅ | 内容寻址路径 + 哈希复核 |
| 备份目录可写 | ✅ | `/data/backups` 写入 |
| 重启后数据仍在 | ✅ | 步骤 36 Persistence across a container rebuild |
| SIGTERM 优雅退出 | ✅ | 步骤 37，退出码与超时断言 |
| **容器内不存在 0777** | ✅ | 步骤 15 扫描 `/data` 与 `/app` |
| **镜像内 `USER 10001:10001`** | ✅ | 静态断言（`test_runtime_config.py`，19 例） |

### 5.3 历史卷兼容（三种模式分别成步）

| 模式 | 场景 | 结果 |
| --- | --- | --- |
| A | 卷已属 `10001:10001` | ✅ 遗留文件可读、新文件可写、可删除；造数容器显式 `--user 0:0` |
| B | 卷属 root（真实 Staging 遗留形态，0644/0755） | ✅ 实测「可读、**不可写**」——这是边界事实，不是测试缺陷；CI 记录并继续 |
| C | 一次性、范围受限的属主迁移 | ✅ 迁移前后 SHA256 完全一致；迁移后 UID 10001 可写、WAL 正常 |

> 模式 B 的结论直接决定上线顺序：**真实 Staging 卷在切换非 root 前必须先执行受限迁移**，否则容器会以「可读不可写」状态启动（应用会 fail-fast，不会静默损坏数据）。

### 5.4 镜像内真实测试执行

| 组 | 文件 | 结果 |
| --- | --- | --- |
| Ops | `test_database_backup` `test_storage_audit` `test_project_backup` `test_project_restore_e2e` | ✅ 51–70 s |
| Security | `test_storage_path_safety` `test_upload_filename_safety` `test_storage_api_security` `test_rate_limit` `test_cors_security` `test_security_headers` `test_runtime_config` | ✅ 9–17 s |

这两步在镜像内以 **UID 10001**、`/app` 只读、`/tests` 与 `/repo` 只读挂载下运行，因此额外证明了「非 root + 只读应用目录」下测试基础设施可用。

### 5.5 运行时行为

| 检查 | 结果 |
| --- | --- |
| 非默认端口注入（8123） | ✅ 步骤 21 |
| 默认端口 + 卷启动 | ✅ 步骤 23 |
| 就绪探针 | ✅ 步骤 24 |
| 访问门禁（匿名被拒） | ✅ 步骤 25 |
| SPA 与静态资源 | ✅ 步骤 26 |
| 容器运行时信息 | ✅ 步骤 27 |
| **真实 Basic Pitch 转写** | ✅ 步骤 28（4 个音符，模型加载真实发生） |
| 不支持的格式被拒 | ✅ 步骤 33 |
| 上传大小限制 413 | ✅ 步骤 34 |

### 5.6 供应链

| 项 | 步骤 | 结果 |
| --- | --- | --- |
| npm audit（全部依赖） | 40 | ✅ JSON 产出 |
| npm audit（生产依赖） | 40 | ✅ JSON 产出，按 high 级别判定 |
| Trivy 镜像漏洞扫描 | 41 | ✅ JSON + 表格 |
| CycloneDX SBOM | 41 | ✅ `pocketscore-sbom.cdx.json`，被步骤 42 校验为「CycloneDX 且组件数 > 0」 |
| 产物完整性强制校验 | 42 | ✅ SBOM + npm + Trivy 缺失即失败 |
| pip-audit | 39 | ⚠️ **NOT VERIFIED**（见 §8） |

---

## 6. 真实 CI 故障与修复（本阶段最有价值的部分）

以下 5 个问题**在本地环境完全不可见**，只有跑真实 Docker + 真实 runner 才暴露。

### 6.1 卷造数容器无法 `chown`（run 46143682894 / 46144467617）

- **症状**：步骤 15（非 root 运行时）通过，步骤 16（历史卷）失败。
- **根因**：镜像声明 `USER 10001` 后，用于「造历史数据」的容器也是非 root，无法 `chown`/`chmod` 卷。
- **修复**：造数与迁移容器显式 `--user 0:0`；验证容器保持 UID 10001。
- **复测**：run 46144794989 起步骤 16 通过。

### 6.2 浅路径下的 `parents[2]` IndexError（run 46144794989 / 46145645888）

- **症状**：镜像内 pytest 退出码 2（collection error），本地同样的 11 个文件全通过。
- **根因**：`test_project_restore_e2e.py` 在模块级用 `Path(__file__).resolve().parents[2]` 推导仓库根；容器内文件挂在 `/tests/x.py`，只有 2 层父目录 → **导入期 IndexError**，一个测试都没跑。
- **证据链**：pytest 退出码 2 对应「collection 期间 1 个错误」，本地注入 `import definitely_missing_module` 复现出同样的 `exit=2`。
- **修复**：`_candidates()` 仅在父目录足够时才加入仓库候选；`test_runtime_config.py` 同样改为优先 `POCKETSCORE_REPO_ROOT`。
- **复测**：run 46147709900 步骤 19/20 全绿。

### 6.3 非 root 下 JIT 缓存不可写（run 46147709900 → 46153017082）

- **症状**：步骤 28「真实 Basic Pitch 转写」在 **1.0 s** 内失败；容器仍存活、16 张表齐全、**没有任何 traceback 日志**。
- **诊断方式**（日志不可读，故用公开通道）：把探针结果编码进 **artifact 名称** → `health=200 anon=401 authed=200 upload=201 job=0 after=200`。即：上传成功、建任务发生传输级失败、失败后服务仍健康。
- **根因**：`POST /jobs` 把推理放进后台任务；librosa/numba 首次使用时要编译 JIT 内核并缓存到 `$HOME`。镜像里 `HOME=/app`（root 属主），UID 10001 不可写 → 后台线程抛错。此时响应已开始，异常无法转成 HTTP 错误，客户端只看到连接被重置，访问日志也不会写出——与全部观测吻合。
- **修复**：
  1. 镜像内 `HOME=/app/tmp`、`NUMBA_CACHE_DIR=/app/tmp/numba`、`MPLCONFIGDIR=/app/tmp/mpl`（均属 UID 10001）；
  2. 后台任务包装器 `try/except` 记录异常并返回，避免未来同类问题再次表现为「神秘重置」。
- **复测**：run 46153017082 步骤 28 通过，全流程 44 步全绿；本地回归 581 passed 不变。

> 这是本阶段最重要的发现：**镜像改为非 root 后，任何依赖 `$HOME` 可写的库都会在推理路径上失败**，且失败形态极难定位（无日志、无 traceback、连接重置）。

### 6.4 SBOM 与审计产物未被校验（run 46154317434）

- **症状**：Trivy 步骤「成功」，但无法确认 SBOM 真的写出。
- **根因**：扫描步骤只记录扫描器退出码，不校验产物。
- **修复**：新增步骤 42，强制 `pocketscore-sbom.cdx.json` 存在、为 CycloneDX、组件数 > 0，并要求 npm/Trivy 产物非空。
- **复测**：该步骤随即真实失败，annotation 指出 `python-audit.json is missing or empty` —— 证明校验有效。

### 6.5 pip-audit 静默无产物（run 46154317434 → 46158573068）

- **症状**：步骤 39 显示 success，但 `python-audit.json` 不存在。
- **根因 1**：`python3 -m venv` 在 runner 镜像上不可用（缺 ensurepip），pip-audit 根本没执行；步骤因未设 `set -e` 而「假成功」。
- **根因 2**：改用 `uvx` / `pipx` 后仍无产物，两种模式（resolved、`--no-deps`）均失败。
- **修复**：��掉「假成功」，改为有界超时 + `mode=unavailable` 记录 + 显式 `::warning`，产物校验对该文件只告警不失败。
- **结论**：该环境下 Python 依赖扫描 **NOT VERIFIED**，不冒充 clean（§8）。

---

## 7. 方法与证据可信度

### 7.1 为什么不「本地跑一遍就宣布通过」

本机无 Docker，历史卷、UID/GID、卷属主、WAL 落盘、容器内只读挂载等属性**无法在 Windows 本机等价模拟**。因此本阶段把判定权交给真实 runner，并逐步骤核对。

### 7.2 为什么每个检查都设计成「失败即红」

- 卷脚本缺 Docker 时 `exit 78`（NOT VERIFIED），绝不当作通过；
- 非 root 脚本断言 `getuid() == 10001`，失败即退出非零；
- 模式 B 的写入失败**被允许**（那是要测量的边界），但结论会写进步骤输出；
- 模式 C 用「迁移前后 SHA256 一致」证明迁移只改属主、不改数据。

### 7.3 日志不可读时的取证方式

仓库日志接口对匿名请求返回 403、artifact 内容 401，但**运行/步骤状态、check-run annotations、artifact 名称**可读。因此：

1. 把失败步骤**拆细**（A/B/C 三模式、ops/security 两组），用步骤名定位；
2. 把探针结果**编码进 artifact 名称**（`health=200-…-job=0-after=200`）；
3. 用 `::warning` / `::error` **annotation** 传递缺失产物名称（§6.4 即由此定位）；
4. 用**指纹**（容器是否存活、表数量、traceback 末行）判断崩溃还是逻辑错误。

这套方法完全基于真实 CI 数据，没有任何猜测被当成结论。

---

## 8. 未验证项（NOT VERIFIED，逐条说明）

| 项 | 状态 | 原因 | 证据 |
| --- | --- | --- | --- |
| **Python 依赖漏洞扫描（pip-audit）** | **NOT VERIFIED** | CI 环境下 pip-audit 在三种安装方式（venv / uvx / pipx）× 两种模式（resolved / `--no-deps`）下均未产出报告；本地因网络无法安装同工具 | run 46158573068 annotation：`pip-audit produced no JSON in mode no-deps`；run 46154317434：`python-audit.json is missing or empty` |
| 本地 Docker 端到端复跑 | NOT VERIFIED | 本机无 Docker/Podman、无 WSL 发行版 | `docker` 不在 PATH |
| 真实 Staging 卷上的属主迁移 | NOT VERIFIED | 明确禁止本阶段改动真实 Staging 卷 | 仅在隔离卷上验证（模式 C） |
| Railway 生产环境部署 | NOT VERIFIED | 生产环境仍为空（0 个 `POCKETSCORE_*` 变量、无卷/域名/部署） | 本阶段未触碰 |
| npm audit 逐条漏洞明细 | 部分 | 明细在 artifact 内，匿名不可下载 | 本阶段给出的是「扫描已执行且产物非空」，不含逐条 CVE 列表 |
| Trivy 逐条 CVE 明细 | 部分 | 同上 | 同上 |

> 报告中**没有**把上述任何一项写成 PASS。

---

## 9. 结论与后续

### 9.1 本阶段完成的判定

- 非 root 运行时、卷兼容、持久化、镜像内测试、npm 审计、Trivy 扫描、SBOM：**在真实 CI 上通过**；
- Python 依赖扫描：**NOT VERIFIED**（环境限制，非产品缺陷）；
- 因此 **CONDITIONAL PASS**，唯一条件项为 §8 第一行。

### 9.2 上线前必须做的两件事

1. **真实 Staging 卷的非 root 迁移**：参照模式 C 的范围（仅 `/data`、`/data/storage`、`/data/backups`），先备份、再迁移、迁移前后比对文件 SHA256；未迁移就切 `USER 10001` 会导致容器 fail-fast（这是设计好的行为，不是故障）。
2. **补齐 Python 依赖扫描**：在可联网环境或自建 runner 上跑 `pip-audit -r backend/requirements.txt`，把结果并入供应链证据链。

### 9.3 下一阶段（C.2.3.4.4）

身份与归属隔离（真正的多用户阻塞项）：P0「A 可读/删 B 的资产」与 P0「`/static` 暴露整个存储根」仍未修，需引入用户/会话主体、资产归属列与访问校验，并收敛静态目录暴露范围。这一项**不能用配置或文档绕过**。

---

## 附录 A：可复现命令

```bash
# 本地回归
cd backend && .venv/Scripts/python -m pytest -q          # 581 passed, 3 skipped
cd backend && .venv/Scripts/python -m ruff check app      # All checks passed

# 真实 CI（同一工作流，本地无 Docker 时失败点会以 exit 78 明确标记 NOT VERIFIED）
bash scripts/docker/test_nonroot_runtime.sh pocketscore-ai:c2-verify
bash scripts/docker/test_nonroot_volume.sh mode-a pocketscore-ai:c2-verify
bash scripts/docker/test_nonroot_volume.sh mode-b pocketscore-ai:c2-verify
bash scripts/docker/test_nonroot_volume.sh mode-c pocketscore-ai:c2-verify
```

## 附录 B：工作流步骤索引（45 步）

1–5 环境/密钥/密钥扫描 · 6–10 前端构建与上下文校验 · 11–14 镜像构建与内容校验 · 15 非 root 运行时 · 16–18 历史卷 A/B/C · 19–20 镜像内测试 · 21–27 端口/就绪/门禁/SPA/运行时信息 · 28 真实转写 · 29–32 失败诊断（仅失败时） · 33–34 上传边界 · 35–37 重启持久化与 SIGTERM · 38 依赖审计汇总 · 39 pip-audit · 40 npm audit · 41 Trivy + SBOM · 42 产物校验 · 43–46 汇总/上传/清理/失败日志。

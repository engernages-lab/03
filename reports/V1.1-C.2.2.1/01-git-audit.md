# V1.1-C.2.2.1 · 01 Git 与环境审计

- **日期**：2026-11-26
- **阶段**：V1.1-C.2.2.1 · Railway Staging Cloud Acceptance
- **性质**：执行前审计（阶段 0）

---

## 1. Git 实况

```text
$ git status --short --branch
## pocketscore-v1.1-b...origin/pocketscore-v1.1-b

$ git branch --show-current
pocketscore-v1.1-b

$ git rev-parse HEAD
9856378b4084436ed395a9856e8d85516c59db1c

$ git rev-parse origin/main
9e7cd419ea6576b89053ef1596d0dd155d422410

$ git log -8 --oneline
9856378 test(e2e): staging smoke authenticates against the access gate
1dcaecc fix(ci): pass the real gate token into the persistence/shutdown containers
a2007dd fix(ci): pass the access-gate token to the verification scripts
8e47b41 feat(deploy): staging access gate enforced at boot, runtime and deploy time
c0da9f1 docs(V1.1-C.2.1): record the green docker-verify run (PASS)
9dca1ad fix(ci): verify-image must actually run its assertions
d0dbc19 fix(docker): do not ignore frontend/dist; verify COPY sources before building
5a41b87 fix(ci): scope the placeholder-secret check to its documented homes
```

| 检查项 | 结果 |
| --- | --- |
| 当前分支 | `pocketscore-v1.1-b` |
| 当前 HEAD | `9856378` |
| 与远程同步 | ✅ 与 `origin/pocketscore-v1.1-b` 一致（无 ahead/behind） |
| 工作区 | ✅ 干净（0 修改、0 未跟踪） |
| 未提交修改 | 无（无需保护/备份） |
| C.2.2 代码是否在 HEAD | ✅ `8e47b41`（门禁）、`1dcaecc`（令牌修复）均在祖先链上 |
| C.2.2 报告提交 | `9856378`（C.2.2 报告 + staging spec 鉴权） |
| `origin/main` | `9e7cd41`（V1.0 基线，**未合并** C.1/C.2/C.2.1/C.2.2） |
| 未完成报告文件 | 无 |

> 任务书提到"C.2.2 最终报告提交必须通过 Git 检查确认"，实测该提交就是 `9856378`。

## 2. CI 状态与 HEAD 的关系（重要）

| 事实 | 值 |
| --- | --- |
| 最近一次绿色 Docker CI | run `45828419659` → 提交 `1dcaecc`，29 步全绿 |
| 当前 HEAD | `9856378`（比 `1dcaecc` 多 1 个提交） |
| 该提交改了什么 | `tests/e2e/staging-smoke.spec.ts`（+15/-2）与 3 份 Markdown 报告 |
| 是否影响镜像 | ❌ 否 —— 没有触碰 `backend/**`、`frontend/src/**`、Dockerfile、`scripts/docker/**` |
| 因此可部署产物 | ✅ 与 CI 验证过的 `1dcaecc` 镜像内容等价 |

如实说明：`9856378` 本身**没有触发** Docker CI（workflow 的 paths 过滤不含 `tests/e2e/**`、`reports/**`），
所以严格意义上"当前 HEAD 的 CI"= 通过祖先提交的证据推导，而非直接运行。
若要求"HEAD 自身有绿色记录"，需要对 `9856378` 手动 `workflow_dispatch`（需仓库权限）。

## 3. 运行环境

| 能力 | 状态 |
| --- | --- |
| Python venv 3.9.13 | ✅ |
| Node / npm | ✅ |
| Docker / WSL | ❌ 未安装（容器证据来自 GitHub Actions） |
| Railway CLI | ❌ 未安装 |
| Railway 登录凭据 | ❌ 无（`~/.railway/config.json` 不存在，无 `RAILWAY_*` 环境变量） |
| `npx @railway/cli` | ❌ 失败（`npm error The operation was rejected by your operating system`，沙箱拒绝写入/执行 npm 包） |

## 4. 强制边界遵守情况

| 禁止项 | 本阶段是否触碰 |
| --- | --- |
| `git reset --hard` | ❌ 未执行 |
| 删除用户未提交修改 | ❌ 未执行（工作区本就干净） |
| 切换/覆盖用户分支 | ❌ 未执行 |
| 合并至 main | ❌ 未执行 |
| Push | ❌ 未执行（本轮**零推送**） |
| 修改生产环境 | ❌ 未执行 |
| 删除 Railway 资源 | ❌ 未执行（无权限，未尝试） |
| 修改现有 Volume 数据 | ❌ 未执行（无权限，未尝试） |

## 5. 结论

Git 状态健康，可部署产物与 CI 绿色提交等价。
**Railway 侧没有任何凭据**，因此阶段 5–11 的云端验收在本次执行中无法进行（详见 04 报告 §24）。

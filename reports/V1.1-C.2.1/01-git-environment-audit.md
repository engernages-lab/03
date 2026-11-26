# V1.1-C.2.1 · 01 Git 与环境审计

- **日期**：2026-11-26
- **阶段**：V1.1-C.2.1 · Docker CI Verification & Deployment Gate
- **性质**：修改前审计

---

## 1. Git 实测

```text
$ git branch --show-current
pocketscore-v1.1-b
$ git rev-parse --short HEAD
372ca7b
$ git status --short
（空）
$ git log --oneline -4
372ca7b feat(V1.1-C.2): container-ready backend - PORT, model singleton, concurrency cap
8ae2b28 docs(V1.1-C.1): production deployment architecture audit (read-only)
afe0086 feat(V1.1-B): professional score export - A4/DPI, PDF, preview, naming
a928983 feat(V1.1-A): accuracy upgrade - harmonic splitting, harmonic suppression
$ git rev-parse --short origin/main
9e7cd41
$ git cat-file -t 5315e3d
commit
```

| 检查项 | 结果 |
| --- | --- |
| 当前分支 | `pocketscore-v1.1-b` ✅ |
| 当前 HEAD | `372ca7b`（C.2 提交），与任务书的 `8ae2b28` 不同 —— 因为 C.2 已在本地提交，属预期推进 |
| 工作区 | 干净（0 修改、0 未跟踪） |
| C.2 提交 | 已在本地（`372ca7b`） |
| `origin/main` | `9e7cd41`，**不包含** C.1/C.2 任何提交 |
| V1.1-B 冻结基线 | `5315e3d` 存在且未改动 |
| 本地未推送提交 | 5 个（`a928983` … `372ca7b`） |
| 远程跟踪 | 仅 `main` 有 upstream；`pocketscore-v1.1-*` 无 upstream（从未推送） |

**差异说明**：任务书写"当前 HEAD 可能已变化"，实测确为 `372ca7b`。
无用户未提交修改，无需 reset / 切分支。

## 2. 运行环境

| 能力 | 状态 | 影响 |
| --- | --- | --- |
| Docker Engine / CLI | ❌ 未安装 | 本阶段无法在本机构建/运行容器 |
| WSL2 | ❌ 未安装 | 无法用 Linux 内核替代 |
| Railway CLI | ❌ 未安装 | 云端部署不属本阶段 |
| Node / npm | ✅ v24.22.0 | 前端构建可本地验证 |
| Python venv | ✅ 3.9.13 | 后端测试可本地验证 |
| bash（Git for Windows） | ⚠️ 存在但无法启动（`couldn't create signal pipe, Win32 error 5`） | 本机无法执行 `bash -n` |
| PyYAML | ✅ 6.0.3 | 可本地校验工作流 YAML |

## 3. 结论

- Git 状态健康，可安全继续。
- **本机不具备 Docker**，因此 `Docker Build` 与 `GitHub Actions Execution` 在本阶段
  只能到"工作流与脚本就绪 + 本地静态校验 + Push 前审核"为止。
- 真实容器证据必须来自 GitHub Actions（ubuntu runner 自带 Docker），这需要一次 push 授权。

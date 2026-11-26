# V1.1-C.2.1 · 07 Git Push 审核与执行记录

> 用户已授权选项 A：推送 `pocketscore-v1.1-b`。本文件记录推送前的审核**与**实际推送结果。

---

## 1. 授权与范围

| 项 | 值 |
| --- | --- |
| 用户授权 | ✅ 选项 A（`git push origin pocketscore-v1.1-b`） |
| 目标远程分支 | `origin/pocketscore-v1.1-b`（推送前**不存在**，本次新建） |
| 是否触碰 `origin/main` | ❌ 否（`origin/main` 仍为 `9e7cd41`） |
| 是否部署 | ❌ 否 |
| 是否创建 Release / PR | ❌ 否 |
| 推送方式 | `git push -u origin pocketscore-v1.1-b`（设置 upstream） |

## 2. 推送记录（共 4 次）

| # | 提交 | 起因 | CI 结果 |
| --- | --- | --- | --- |
| 1 | `0283936` | 首次推送 C.2.1 全部内容（6 个提交） | ❌ run `45817337637` — Secret scan 误报 |
| 2 | `5a41b87` | 修正扫描白名单 | ❌ run `45817671769` — Build image 失败（`.dockerignore` 排除 dist） |
| 3 | `d0dbc19` | 恢复 dist + 新增 `verify-context.py` | ❌ run `45818307503` — Verify image 失败（缺 `-i` + `pip check`） |
| 4 | `9dca1ad` | 修 `verify-image.sh` | ✅ run `45819026067` — **全部 29 步通过** |

推送后 `origin/pocketscore-v1.1-b = 9dca1ad`。

## 3. 推送内容（审核结论）

| 检查 | 结果 |
| --- | --- |
| 是否含 `.env` | ❌ 无 |
| 是否含私钥 / 真实密钥 | ❌ 无（CI 密钥运行时用 `openssl rand` 生成 + `::add-mask::`） |
| 是否含数据库 | ❌ 无 |
| 是否含音频隐私文件 | ❌ 无（仅既有 `tests/fixtures/melody.wav`） |
| 是否含构建产物 | ❌ 无（`frontend/dist` 由 CI 现场构建，仍被 `.gitignore` 忽略） |
| 是否含 `node_modules` | ❌ 无 |

CI 的密钥扫描（步骤 5 + 步骤 14）在最终运行中通过，与上表一致。

## 4. 推送触发的 CI

| 工作流 | 是否触发 | 说明 |
| --- | --- | --- |
| `Docker verify (V1.1-C.2.1)` | ✅ 4 次（每次 push 一次） | paths 过滤命中 `scripts/docker/**`、workflow 自身、`.dockerignore` |
| `CI`（既有） | ❌ 未触发 | 该工作流只监听 `main` / PR；本次未推送 main |
| `Deploy frontend to GitHub Pages` | ❌ 未触发 | 只监听 `main`，线上站点未变化 |

**后果说明**：单元测试（后端 327 / 前端 103 / E2E 15）在本次推送中**没有**在 CI 上跑，
因为 `ci.yml` 不监听该分支。这些数字来自本地运行（C.2 阶段），
容器门禁覆盖的是构建、依赖、运行时、真实推理、持久化与退出。

## 5. 远程现状

```text
origin/main                = 9e7cd41   （未变）
origin/pocketscore-v1.1-b  = 9dca1ad   （新建）
本地 pocketscore-v1.1-b     = 9dca1ad   （与远程一致）
```

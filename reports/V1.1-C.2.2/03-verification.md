# V1.1-C.2.2 · 03 验证报告（访问门禁 + 容器）

- **日期**：2026-11-26
- **CI run**：`45828419659`（`1dcaecc`）— **全部步骤 success**
- **本机**：Windows，无 Docker；访问门禁在真实进程上端到端验证

---

## 1. CI 中的访问门禁（强制步骤）

| 步骤 | 耗时 | 结果 |
| --- | --- | --- |
| 19 · Access gate enforced (anonymous must be blocked) | 0 s | ✅ success |
| 21 · Real Basic Pitch transcription（带令牌） | 14 s | ✅ success |
| 22 · Reject an unsupported upload（先鉴权再验 415） | 0 s | ✅ success |
| 24 · Persistence across a container rebuild（容器内带令牌） | 58 s | ✅ success |
| 25 · Graceful shutdown on SIGTERM | 21 s | ✅ success |

该步骤的断言（`scripts/deploy/verify-access-gate.sh`）：

1. `/health` 无凭据 → **200**
2. `GET /api/v1/documents` 无凭据 → **401** 且 `code=ACCESS_GATE_REQUIRED`
3. `POST /api/v1/audio/upload` 无凭据 → **401**
4. 带正确 bearer → **200**
5. 带错误 bearer → **401**

**任一条不满足，工作流失败**，因此流水线无法产出一个"裸奔"的 staging 镜像。

## 2. 启动门禁（最强的一层）

| 场景 | 预期 | 实测 |
| --- | --- | --- |
| staging + 无任何门禁凭据 | 进程拒绝启动 | ✅ `validate_hardened_secrets` 返回问题，`RuntimeError` |
| staging + `ACCESS_GATE_MODE=off` | 拒绝启动 | ✅ 单元测试覆盖 |
| staging + token | 正常启动，门禁 `token` 模式 | ✅ |
| staging + user/password | 正常启动，门禁 `basic` 模式 | ✅ |
| development | 不启用门禁 | ✅ |

这条是"部署前"的保证：忘记配置 → 容器起不来 → 平台健康检查失败 → 部署失败。
不存在"先上线再补"的路径。

## 3. 本机端到端验证（真实进程 + 真实模型）

```
/health                     无凭据 → 200
/api/v1/documents           无凭据 → 401
/api/v1/documents           带 bearer → 200
transcription (--token)     → TRANSCRIPTION VERIFY OK: 4 notes, pitches [60,64,67,72] in 2.477 s
```

容器等价冒烟（`scripts/smoke_deployment.py`，已带门禁令牌）：

```
startup 9.79 s → /ready 200 (ready:true, model ready 3.3s/warmup 1.9s)
upload 201 → job completed → 4 events → document 200 → 重启后数据仍在
```

## 4. 本轮修复的两个真实问题

| # | 现象 | 根因 | 修复 |
| --- | --- | --- | --- |
| 1 | 第一次带门禁的 CI 失败 | 校验脚本在 runner 上调 API 却没带令牌（门禁**按预期**拦住了） | `verify-transcription.py` 增加 `--token`；持久化脚本所有 curl 带 `Authorization`；415 用例先鉴权 |
| 2 | 第二次失败在"Persistence" | 一次 shell 补丁把 `${TEST_ACCESS_TOKEN}` 变成了空串 → 容器因缺凭据拒绝启动 | 修正两处为 `"${TEST_ACCESS_TOKEN}"`，并加脚本级检查（不得出现不含变量的 `ACCESS_GATE_TOKEN` 行） |

第 1 条恰好证明门禁有效：脚本没带凭据就被拦了。

## 5. 回归

| 层级 | 结果 |
| --- | --- |
| 后端 pytest | **346 passed**（+19 门禁/配置测试） |
| 前端 vitest | 103 passed |
| Ruff | All checks passed |
| CI（容器门禁） | 29 步全绿（run `45828419659`） |

## 6. 未覆盖

- 公网 Railway 部署未执行（缺凭据，见 04 报告）。
- 门禁的 429 防爆破只在单测覆盖，未在容器内压测。
- 门禁为**共享凭据**，不做用户隔离（C.5）。

# V1.1-C.2.2 · 02 实施报告

- **日期**：2026-11-26
- **范围**：访问门禁（启动 + 运行时 + 部署门禁）、部署脚本、CI 触发范围

---

## 1. 修改文件清单

| # | 文件 | 类型 | 内容 | 原因 | 影响现有功能 |
| --- | --- | --- | --- | --- | --- |
| 1 | `backend/app/core/access_gate.py` | 新增 | `AccessGate` + `AccessGateMiddleware` + `build_gate` / `gate_problems`：token/basic 两种模式、`/health`&`/ready`&OPTIONS 放行、401 信封、429 防爆破、`describe()` 不含凭据 | staging 无认证不得公开 | 否 |
| 2 | `backend/app/core/config.py` | 修改 | 新增 `access_gate_mode/token/user/password`；`validate_hardened_secrets()` 增加门禁校验（缺凭据或显式 off → 拒绝启动） | 启动期强制 | 否（development 不受影响） |
| 3 | `backend/app/main.py` | 修改 | 挂载 `AccessGateMiddleware`（CORS 在其外层），启动日志打印门禁描述 | 运行时强制 | 否 |
| 4 | `backend/app/api/v1/health.py` | 修改 | `/ready` 增加 `checks.access_gate`（只报 mode/enabled/配置有无） | 让部署探针区分"已保护"与"意外开放" | 否 |
| 5 | `scripts/deploy/verify-access-gate.sh` | 新增 | 断言匿名 401、健康 200、令牌 200、错令牌 401、上传 401 | 部署门禁 | 否 |
| 6 | `.github/workflows/docker-verify.yml` | 修改 | 生成 `TEST_ACCESS_TOKEN` 并注入所有容器；新增 **Access gate enforced** 步骤（就绪之后、AI 之前）；`bash -n` 覆盖 `scripts/deploy/*.sh`；paths 增加 `scripts/deploy/**` | 门禁进流水线 | 否 |
| 7 | `scripts/docker/verify-transcription.py` | 修改 | `--token` 参数，默认读 `POCKETSCORE_ACCESS_GATE_TOKEN` / `TEST_ACCESS_TOKEN` | 带凭据做真实扒谱 | 否 |
| 8 | `scripts/docker/verify-persistence.sh` | 修改 | 容器注入真实令牌；5 处 curl 带 `Authorization`；验证器传 `--token` | 持久化验证在门禁后仍成立 | 否 |
| 9 | `scripts/docker/verify-graceful-shutdown.sh` | 修改 | 容器注入真实令牌 | 容器能启动 | 否 |
| 10 | `scripts/smoke_deployment.py` | 修改 | 注入令牌 + 请求带 `Authorization` | 本地等价冒烟 | 否 |
| 11 | `tests/e2e/staging-smoke.spec.ts` | 修改 | 5 处 API 调用带 `Authorization: Bearer ${POCKETSCORE_ACCESS_GATE_TOKEN}` | 云端验收能在门禁下运行 | 否（无 URL 时仍 skip） |
| 12 | `backend/tests/test_access_gate.py` | 新增 | 19 项：配置拒绝、放行路径、401/200、错令牌、Basic、预检、429、描述不泄漏 | 契约测试 | — |
| 13 | `backend/tests/test_production_config.py` | 修改 | staging 基准配置补入门禁凭据 | 配置规则变更 | — |
| 14 | `backend/.env.example` / `docker-compose.yml` | 修改 | 门禁变量与说明 | 部署文档化 | 否 |
| 15 | `reports/V1.1-C.2.2/01..05*.md` | 新增 | 本阶段报告 | 交付 | — |

无删除；未改动 V1.1-B 冻结实现。

## 2. 三层强制如何落地

```text
启动   validate_hardened_secrets()
       ├─ staging/production 且无 token/user+password → RuntimeError，进程不启动
       └─ 显式 ACCESS_GATE_MODE=off → 同样拒绝
运行   AccessGateMiddleware
       ├─ /health /ready OPTIONS 放行
       ├─ 其余：无凭据/错凭据 → 401 ACCESS_GATE_REQUIRED
       └─ 单 IP 60s 内 20 次失败 → 429 TOO_MANY_ATTEMPTS
部署   CI 步骤 "Access gate enforced"
       ├─ 匿名 /documents、/audio/upload 必须 401
       ├─ 正确令牌必须 200，错误令牌必须 401
       └─ 任一不满足 → 工作流红
```

## 3. 与 Docker 验证的关系（按你的要求）

- **没有重做** Docker 验证系统：C.2.1 的工作流、脚本、镜像断言全部沿用。
- 只做了两处扩展：
  1. 容器启动参数补了一枚门禁令牌（否则 staging 容器会拒绝启动）；
  2. 新增一个门禁断言步骤。
- 触发范围补了 `scripts/deploy/**`，其余规则不变；
  本次 `tests/e2e/**`、`reports/**` 的改动**不会**触发 Docker 构建，避免浪费分钟数。

## 4. CI 结果

| run | 提交 | 结果 | 说明 |
| --- | --- | --- | --- |
| `45823317201` | `8e47b41` | ❌ | 脚本调 API 没带令牌（门禁**按预期**拦住） |
| `45827062415` | `a2007dd` | ❌ | 持久化脚本里 `${TEST_ACCESS_TOKEN}` 被 shell 补丁写成空串 → 容器拒绝启动 |
| **`45828419659`** | **`1dcaecc`** | ✅ **29 步全绿** | 门禁、真实扒谱、持久化、优雅退出全部通过 |

关键步骤耗时：Build image 25 s / Verify image 6 s / PORT 8123 21 s / **Access gate 0 s** /
真实扒谱 14 s / 持久化 58 s / 优雅退出 21 s。

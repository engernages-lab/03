# V1.1-C.2.2 · 01 访问保护设计（Deployment Gate）

- **日期**：2026-11-26
- **目标**：把"staging 必须有访问保护"变成**部署门禁**，而不是部署后的待办
- **前提事实**：本后端**没有用户认证**（C.5 才做），一旦公开即等于把 AI 算力与全部项目数据开放

---

## 1. 三层强制（缺一层都不算达标）

| 层 | 机制 | 效果 |
| --- | --- | --- |
| L1 启动 | `Settings.validate_hardened_secrets()` 检查访问凭据 | staging/production **缺凭据就拒绝启动**，进程根本起不来 |
| L2 运行 | `AccessGateMiddleware` | 除 `/health` `/ready` 外的**所有**请求都要凭据，否则 401 |
| L3 部署 | `scripts/deploy/verify-access-gate.sh` + CI 步骤 | 部署前/后必须证明"匿名被拦、凭据可用"，否则流水线失败 |

L1 让"忘记配置"变成启动失败；L2 让"配置了但没生效"变成 401 断言；L3 让"以为配了"变成红灯。

## 2. 配置

| 变量 | 说明 |
| --- | --- |
| `POCKETSCORE_ACCESS_GATE_MODE` | `auto`（默认）/ `token` / `basic` / `off` |
| `POCKETSCORE_ACCESS_GATE_TOKEN` | bearer 令牌（脚本、CI、curl） |
| `POCKETSCORE_ACCESS_GATE_USER` / `_PASSWORD` | HTTP Basic（人用浏览器/curl） |

**`auto` 的解析规则**：

- development / test → `off`（本地开发不受影响）
- staging / production → 有 user+password 用 `basic`，否则有 token 用 `token`，都没有则 `off` → **启动失败**

显式 `mode=off` 在 staging/production 被直接拒绝（不是警告）。

## 3. 哪些路径放行

| 路径 | 原因 |
| --- | --- |
| `/health`、`/ready` | 平台健康检查无法携带凭据；被拦会误判部署失败 |
| `OPTIONS *` | CORS 预检不带凭据；拦了浏览器就完全不可用（且 CORS 中间件在外层） |

其余全部保护，包括 `/api/v1/*`、`/static/*`、SPA 页面、`/docs`。

## 4. 这是不是"认证"？

**不是。** 它是**单一共享凭据**的访问墙：

- 无法区分为不同用户，也不做数据隔离（所有项目对持有凭据者可见）；
- 没有会话、没有审计归属；
- 只能用于"少量受控测试者"或"内部验证"。

报告与代码注释都这样写，避免把它当成 C.5 的替代品。C.5 完成后应移除此门或退化为额外一层。

## 5. 防爆破

同一 IP 在 60 s 内失败达到 20 次 → 返回 **429 `TOO_MANY_ATTEMPTS`**。
计数在内存中（进程级），重启清空；多副本不共享（当前单副本部署，可接受）。

## 6. 信息泄漏控制

- 401 响应只返回 `{error:{code,message,details:{mode,realm}}}`，**不含**任何凭据；
- `/ready` 的 `checks.access_gate` 只报 `mode/enabled/token_configured/basic_configured`；
- 日志记录 `method path client attempt`，**不记录** Authorization 头。

## 7. 对前端的影响（必须说清）

GitHub Pages 的静态前端**没有**这枚凭据，因此它调用 staging API 会得到 401。
这是**设计如此**：C.2.2 的 staging 是"API 级验收环境"，不是公开产品。

要让页面可用，只有两条路：

1. C.5 实现真正的用户认证（推荐）；
2. 在页面上让测试者**手动输入**令牌（存 sessionStorage，不进构建产物）——本阶段未实现，避免让人误以为产品已可公开。

## 8. 与之配套的部署门禁

```bash
# 部署前/后都必须通过（CI 已在容器上执行）
scripts/deploy/verify-access-gate.sh https://<host> "$POCKETSCORE_ACCESS_GATE_TOKEN"
```

断言：

1. `/health` 无凭据 200；
2. `GET /api/v1/documents` 无凭据 **401** 且错误码 `ACCESS_GATE_REQUIRED`；
3. `POST /api/v1/audio/upload` 无凭据 **401**；
4. 带正确令牌 → 200；
5. 带错误令牌 → 401。

# V1.1-C.2.2.2 · 05 就绪与访问门禁真实性（Phase 5）

- **日期**：2026-11-27
- **证据**：`artifacts/ready-response.json`、`artifacts/health-response.json`

---

## 1. `/health`

```json
{"status":"ok","version":"1.0.0a1","stage":"V1.0-A"}
```

HTTP 200，`content-type: application/json`，耗时 0.87–0.99 s，匿名可访问（探针豁免）。

## 2. `/ready`（完整响应，实测）

```json
{
  "ready": true,
  "status": "ready",
  "checks": {
    "database":   {"ok": true},
    "storage":    {"ok": true},
    "ffmpeg":     {"ok": true, "optional": false},
    "librosa":    {"ok": true, "optional": true},
    "midi":       {"ok": true, "optional": false},
    "model":      {"ok": true, "status": "ready", "version": "0.4.0",
                   "load_seconds": 1.104, "warmup_seconds": 1.03, "optional": false},
    "inference":  {"ok": true, "capacity": 1, "active": 0, "queued": 0, "completed": 0},
    "access_gate":{"ok": true, "mode": "token", "enabled": true,
                   "token_configured": true, "basic_configured": false,
                   "exempt_paths": ["/health", "/ready"]}
  },
  "timestamp": "2026-11-27T09:18:15.343683+00:00"
}
```

| 要求字段 | 存在 | 说明 |
| --- | --- | --- |
| database | ✅ | `ok: true` |
| storage | ✅ | 真实写入探测（非仅路径判断） |
| ffmpeg | ✅ | 捆绑 ffmpeg 可用 |
| librosa | ✅ | 音频库可用 |
| midi | ✅ | mido/pretty_midi 可用 |
| model | ✅ | `status: ready`（模型已加载并预热） |
| inference | ✅ | 并发池 capacity=1 |
| access_gate | ✅ | 仅报布尔/模式，不含凭据 |

### 2.1 database 是否真的执行了 SQL？

代码路径（本轮修复）：

```python
# backend/app/main.py
@app.get("/ready", include_in_schema=False)
def ready_root() -> JSONResponse:
    from app.core.db import session_scope
    with session_scope() as session:
        payload = _readiness_payload(session)

# backend/app/api/v1/health.py
if db is not None:
    db.execute(text("SELECT 1"))
    checks["database"] = {"ok": True}
```

云端返回 `database: {ok: true}` 且 `ready: true`，说明会话能打开且 `SELECT 1` 成功。
（修复前该字段根本不存在 —— 见 `01-preflight-audit.md` §2 F5。）

### 2.2 access_gate 是否泄露凭据？

`describe()` 只输出 `mode / enabled / token_configured / basic_configured / exempt_paths`，
没有任何令牌、密码、长度或哈希。已用 regex 检查响应体不含令牌原文。

## 3. 数据库故障时的 503：**CLOUD_FAULT_INJECTION: NOT TESTED**

按要求没有对真实 Staging 做故障注入（不删库、不改 Volume、不停服务）。

可替代的**本地证据**（隔离环境，不触碰云端）：

```text
backend/tests/test_health.py::test_ready_checks_the_database          ✅
backend/tests/test_health.py::test_ready_reports_the_access_gate_state ✅
backend/tests/test_production_config.py（启动期拒绝不安全配置）        ✅
```

诚实声明：**"数据库不可用时 /ready 返回 503" 在云端未验证。**
代码上 `/ready` 在 `session_scope()` 抛异常时返回
`{"ready": false, "status": "degraded", "checks": {"database": {"ok": false}}}` 且 HTTP 503，
但这是代码阅读 + 本地测试结论，不是云端实测。

## 4. Access Gate 在云端的完整行为

| 请求 | 状态 | 证据来源 |
| --- | --- | --- |
| `/health` 匿名 | 200 | curl |
| `/ready` 匿名 | 200 | curl |
| `/` 匿名 | 401 | curl + 浏览器（Chrome 直接 `ERR_INVALID_AUTH_CREDENTIALS`） |
| `/docs` 匿名 | 401 | curl |
| `/openapi.json` 匿名 | 401 | curl |
| `/api/v1/documents` 匿名 | 401 | curl + Playwright request |
| `/assets/*.js`、`*.css` 匿名 | 401 | curl |
| 错误令牌 | 401 | curl |
| 正确令牌 | 200 | curl |
| 21 次连续错误 | 429 | curl（见 11 号报告） |
| OPTIONS 预检 | 200 + 允许头 / 外来源 400 | curl |

## 5. 结论

| 项 | 结果 |
| --- | --- |
| `/health` 真实 | ✅ |
| `/ready` 完整（8 个检查项） | ✅ |
| database 真实 SELECT 1 | ✅（云端 ok，代码可追溯） |
| access_gate 状态真实且不泄露 | ✅ |
| 数据库故障 503 | ⛔ 云端未注入（NOT TESTED，仅本地测试覆盖） |

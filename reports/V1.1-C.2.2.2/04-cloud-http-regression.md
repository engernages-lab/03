# V1.1-C.2.2.2 · 04 云端 HTTP 回归（Phase 4）

- **日期**：2026-11-27
- **目标域名**：`https://pocketscore-api-staging.up.railway.app`
- **脚本**：`scripts/deploy/verify-staging-regression.sh`（本次新增）
- **结果**：**24 项断言全部通过（passed=24 failed=0）**

---

## 1. 首页（`GET /`）

门禁保护一切非探针路径，所以 SPA 根路径对匿名访问是 **401**，这是设计而非缺陷。两种状态都记录：

| 请求 | 状态 | 说明 |
| --- | --- | --- |
| 匿名 `GET /` | **401** | `content-type: application/json`，`www-authenticate: Basic realm="PocketScore Staging"` |
| 带令牌 `GET /` | **200** | `text/html; charset=utf-8`，665 字节，0.93 s |

证据：`artifacts/homepage-response-headers.txt`、`artifacts/homepage.html`、
`artifacts/homepage-meta.json`、`artifacts/homepage-anonymous.json`

响应头（节选）：

```text
HTTP/1.1 200 OK
Accept-Ranges: bytes
Content-Type: text/html; charset=utf-8
etag: "9b4f8e3c3d31eec0b70ca3647e509050"
last-modified: Fri, 27 Nov 2026 08:37:14 GMT
Server: railway-hikari
```

返回的是**真正的 SPA HTML**（`<!doctype html><html lang="zh-CN" class="dark">`），
不是 API 描述 JSON、不是 FastAPI 默认页、不是 404。

## 2. 静态资源（从真实 HTML 中提取，未硬编码版本号）

证据：`artifacts/frontend-assets-check.json`

```json
{
  "js":  {"path":"/assets/index-BGu74WxJ.js","anonymous":401,"authenticated":200,
          "content_type":"application/javascript","bytes":399033},
  "css": {"path":"/assets/index-BcW44oh8.css","anonymous":401,"authenticated":200,
          "content_type":"text/css; charset=utf-8","bytes":37581}
}
```

| 检查 | 结果 |
| --- | --- |
| JS 200 + `application/javascript` | ✅ 399,033 字节 |
| CSS 200 + `text/css` | ✅ 37,581 字节 |
| 匿名访问被拒 | ✅ 401（门禁同样保护静态资源） |
| 是否存在 `/03/assets/` | ✅ 不存在（F2 修复生效） |

## 3. SPA 客户端路由（直接访问 = 刷新行为）

证据：`artifacts/spa-routes.txt`

```text
/dashboard      status=200 html=yes
/scores         status=200 html=yes
/transcription  status=200 html=yes
/settings       status=200 html=yes
```

四个真实路由（取自 `frontend/src/App.tsx`）直接 GET 均返回 SPA HTML，
说明 catch-all 正常，刷新二级路由不会 404 或返回 API JSON。

## 4. Access Gate（真实 HTTP）

证据：`artifacts/access-gate-check.json`、`artifacts/gate-anon.json`

| 测试 | 期望 | 实测 |
| --- | --- | --- |
| `GET /api/v1/documents` 匿名 | 401 | ✅ 401 |
| 同上 + 错误令牌 | 401 | ✅ 401 |
| 同上 + 正确令牌 | 200 | ✅ 200 |
| `GET /docs` 匿名 | 401 | ✅ 401 |
| `GET /openapi.json` 匿名 | 401 | ✅ 401 |
| `POST /api/v1/audio/upload` 匿名 | 401 | ✅ 401 |
| 错误信封 | `ACCESS_GATE_REQUIRED` | ✅ |
| 响应中是否回显令牌 | 否 | ✅ 否 |

`gate-anon.json` 实际内容（脱敏，无令牌）：

```json
{"error":{"code":"ACCESS_GATE_REQUIRED","message":"需要访问凭据（该环境启用了 staging 访问保护）",
          "details":{"mode":"token","realm":"PocketScore Staging"}}}
```

## 5. CORS

证据：`artifacts/cors-preflight-headers.txt`

| 测试 | 结果 |
| --- | --- |
| 允许来源 `https://engernages-lab.github.io` 预检 | ✅ 200，`access-control-allow-origin: https://engernages-lab.github.io` |
| 允许 headers | ✅ `authorization` |
| 允许 methods | `DELETE, GET, HEAD, OPTIONS, PATCH, POST, PUT` |
| `max-age` | 600 |
| 外来源 `https://evil.example` 预检 | ✅ **400**（拒绝） |

## 6. `/health` 与 `/ready`

| 请求 | 状态 | 耗时 | 证据 |
| --- | --- | --- | --- |
| `GET /health` | 200 | 0.87–0.99 s | `artifacts/health-response.json` |
| `GET /ready` | 200 | 0.90–1.02 s | `artifacts/ready-response.json` |

`/ready` 完整内容见 `05-readiness-and-access-gate.md`。

## 7. 浏览器侧的真实证据（补充）

Playwright 用系统 Chrome 打开真实域名（见 `10-browser-regression.md`）：

```text
asset_count=12  全部 200
console_errors=[]   failed_requests=[]
title="PocketScore AI · 音乐工作站"
final_url=/scores   （SPA 路由跳转成功）
```

## 8. 结论

| 编号 | 项目 | 结果 |
| --- | --- | --- |
| F2 | 基路径 `/` | ✅ 资源路径无 `/03/` |
| F4 | SPA 托管 | ✅ 根路径 HTML + 4 条客户端路由 + 真实浏览器渲染 |
| — | Access Gate | ✅ 401/200 全部符合设计 |
| — | CORS | ✅ 精确来源放行，外来源 400 |

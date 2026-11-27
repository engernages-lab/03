# V1.1-C.2.2.2 · 10 浏览器真实回归（Phase 12）

- **日期**：2026-11-27
- **工具**：Playwright + **系统 Chrome**（本机 Playwright 内置浏览器不可用，见 §5）
- **目标**：`https://pocketscore-api-staging.up.railway.app`（真实云端，非 localhost）
- **结果**：**2 passed / 1 skipped（1 项标为 NOT TESTED，理由见 §4）**

---

## 1. 认证浏览器：SPA 真的能用

`tests/e2e/staging-regression.spec.ts`，通过 `test.use({ extraHTTPHeaders })` 注入令牌。

实测输出：

```text
BROWSER_SUMMARY {
  "staging":"https://pocketscore-api-staging.up.railway.app",
  "final_url":"https://pocketscore-api-staging.up.railway.app/scores",
  "title":"PocketScore AI · 音乐工作站",
  "asset_count":12,
  "console_errors":[],
  "failed_requests":[]
}
```

| 检查 | 结果 |
| --- | --- |
| 首页打开 | ✅ 200，`text/html` |
| React 真正挂载 | ✅ `#root` 有内容，标题为「PocketScore AI · 音乐工作站」 |
| 静态资源 | ✅ 12 次请求全部 200（JS 399 KB / CSS 37.6 KB 重复加载属正常路由切换） |
| 客户端路由 | ✅ `/dashboard`、`/scores`、`/settings` 均渲染，URL 正确 |
| 深链接刷新 | ✅ `/scores` 直接访问 + `reload()` 后仍正常 |
| Console 错误 | ✅ 无（已过滤 favicon/ResizeObserver 噪音，实际为 0） |
| 失败请求 | ✅ 0 |
| 白屏 | ❌ 未出现 |
| Network 404 | ❌ 无 |

## 2. 匿名访问：HTTP 层已证明被拒（浏览器渲染断言 NOT TESTED）

`tests/e2e/staging-anonymous.spec.ts`：

| 断言 | 结果 |
| --- | --- |
| 匿名 `request.get('/api/v1/documents')` | ✅ 401 + `ACCESS_GATE_REQUIRED` |
| 匿名浏览器导航到 `/` | ⚠️ 见下 |

浏览器导航的真实观察：

- 用**独立脚本**（非测试运行器）启动 Chrome 访问 `/`：
  两次均抛 `net::ERR_INVALID_AUTH_CREDENTIALS` —— Chrome 收到
  `401 + WWW-Authenticate: Basic` 后拒绝在没有凭据的情况下渲染；
- 但在 Playwright Test 里，同样的匿名导航会**挂起**（runner 与单独 worker 均复现，
  120 s 超时），无法稳定拿到"未渲染"的断言结果。

因此该条标为 **NOT TESTED**（`test.fixme` + 原因写在文件头），
并保留一条**今天能跑**的断言（匿名 API 401）。

**重要的实现坑**：Playwright Test 会把文件里的 `test.use({ extraHTTPHeaders })`
应用到该 worker 启动的**所有**浏览器，包括手动 `chromium.launch()` 出来的实例——
所以"匿名"用例最初拿到的是 200。这也是为什么匿名用例必须单独一个文件。

## 3. 安全边界：前端不持有共享令牌

| 检查 | 结果 |
| --- | --- |
| 页面源码/构建产物含令牌 | ✅ 无（bundle 扫描见 11 号报告） |
| `VITE_*` 含令牌 | ✅ 无 |
| `localStorage` 存令牌 | ✅ 无（测试通过注入 HTTP 头，不落存储） |
| 为了让浏览器跑通而关闭门禁 | ❌ 没有 |

## 4. 架构限制（必须记录）

共享令牌**无法**安全地交给公开静态前端：

- GitHub Pages 的 JS 是公开的，任何内置令牌都等于泄露；
- 因此 staging 前端**只能**在注入凭据的受控浏览器里使用（本次测试的做法），
  普通访客打开 Pages 站点会得到 401；
- 这不是本阶段可以绕过的问题，需要 C.5 的真实用户认证。

## 5. 环境限制（如实记录）

- 本机 Playwright 内置 Chromium 未安装且下载不稳定（两次中断），
  改用系统 Chrome（`channel: "chrome"`，版本由系统决定）。
- 本地 E2E 也因同样原因需用 `channel` 覆盖配置
  （`.run/playwright.chrome.config.ts`，仅本地使用，未提交）。

## 6. 结论

| 项目 | 结果 |
| --- | --- |
| 真实浏览器打开 staging 前端 | ✅ |
| 资源/CORS/路由/刷新 | ✅ |
| Console 与 Network 干净 | ✅ |
| 匿名浏览器渲染断言 | ⛔ NOT TESTED（环境不稳定） |
| 匿名 API 401 | ✅ |
| 前端无令牌 | ✅ |

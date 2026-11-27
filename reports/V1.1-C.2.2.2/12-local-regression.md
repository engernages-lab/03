# V1.1-C.2.2.2 · 12 本地自动化回归（Phase 14）

- **日期**：2026-11-27
- **说明**：本节全部为**本地**结果，不代表云端行为；云端证据见 04–10 号报告。

---

## 1. 后端

| 命令 | 结果 |
| --- | --- |
| `python -m ruff check app tests` | ✅ All checks passed |
| `python -m pytest` | ✅ **354 passed**（46.8 s） |

覆盖：Access Gate（19）、生产配置校验、health/ready 契约、上传限制、
模型管理器、推理限流器、音频资产、MusicDocument、谱面、导出等。

## 2. 前端

| 命令 | 结果 |
| --- | --- |
| `npx tsc --noEmit` | ✅ exit 0 |
| `npx vitest run` | ✅ **103 passed**（12 文件） |
| `npm run build` | ✅ `built in 11.25s`，0 sourcemap |

## 3. E2E（本地，Chromium 由系统 Chrome 提供）

| 命令 | 结果 |
| --- | --- |
| `npx playwright test --config .run/playwright.chrome.config.ts --grep-invert staging` | ✅ **15 passed / 1 skipped**（46 s） |

> 本机 Playwright 自带浏览器未安装（下载两次中断），因此本地用
> `.run/playwright.chrome.config.ts` 覆盖 `channel: chrome`；该文件在 `.run/`（gitignore），
> 不影响仓库与 CI 配置。

## 4. 本阶段新增的测试与脚本

| 文件 | 类型 | 用途 |
| --- | --- | --- |
| `scripts/deploy/verify-staging-regression.sh` | 新增 | 云端 HTTP 回归（24 断言） |
| `scripts/deploy/verify-staging-audio.py` | 新增 | 云端 WAV/MP3 上传 + 扒谱 + 音符校验 |
| `scripts/deploy/verify-staging-document.py` | 新增 | 云端文档保存/编辑/双谱面一致性 |
| `scripts/deploy/verify-staging-persistence.py` | 新增 | 重启前后快照（含音频 SHA256） |
| `scripts/deploy/compare-staging-persistence.py` | 新增 | 12 字段逐项比较 |
| `tests/e2e/staging-regression.spec.ts` | 新增 | 真实浏览器：资源/路由/刷新/Console |
| `tests/e2e/staging-anonymous.spec.ts` | 新增 | 匿名拒绝（API 401 可跑；渲染断言 FIXME） |

未新增后端单元测试：本轮未修改运行时代码（除文档外），既有 354 项已覆盖相关契约。

## 5. Docker CI（远程，非本地）

| 项 | 值 |
| --- | --- |
| 最近绿色 run | `45972926226`（`4ec2b7c`） |
| 说明 | 本阶段代码改动仅为 `tests/e2e/*` 与 `scripts/deploy/*`、`reports/*`，
不触发 `docker-verify`（paths 过滤），因此未产生新的镜像验证运行 |

## 6. 结论

本地全部检查通过。**本地通过 ≠ 云端通过**，云端证据单独列于 04–11 号报告。

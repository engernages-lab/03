# V1.1-C.2 · 05 云端冒烟测试（Cloud Smoke Test）

> **状态：NOT EXECUTED（无云端环境）** — 本文件记录已就绪的测试资产与本地实测结果。

---

## 1. 为什么没有云端结果

`04-railway-deployment-report.md` 已说明：未授权 + 无 CLI + Docker 本地验证未通过。
没有部署就不存在云端 URL，任何"云端通过"的结论都会是伪造，因此本节只报告**可在本地真实执行**的部分。

---

## 2. 已就绪的云端测试资产

`tests/e2e/staging-smoke.spec.ts`（新增）——设置 `PSC_STAGING_URL` 后自动对真实远端执行：

| 用例 | 断言 |
| --- | --- |
| 健康与就绪 | `GET /health` 200 且 `status=ok`；`GET /ready` ∈ {200,503} 且含 `checks.model` |
| 真实扒谱链路 | `POST /audio/upload` 201 → `POST /transcription/jobs` → `POST .../run` → `events_produced > 0` → `GET /notation/{id}/both` 两侧 `notes > 0` |
| 拒绝非法扩展名 | `evil.exe` → 415 且 `error.code = UNSUPPORTED_MEDIA_TYPE` |

未设置变量时 **3 个用例整体 skip**（不是 pass）。整套 E2E 当前结果：**15 passed / 4 skipped**。

运行方式：

```bash
PSC_STAGING_URL=https://<service>.up.railway.app npx playwright test tests/e2e/staging-smoke.spec.ts
```

---

## 3. 本地等价环境的实测结果（可复现）

用 `scripts/smoke_deployment.py` 以 staging 配置启动真实进程并完成整条链路（详见 03 报告 §2.1）：

| 验收项 | 实测 |
| --- | --- |
| `GET /health` | 200，启动后 2.9 s 内可用（进程总启动 9.04 s，含模型预热） |
| `GET /ready` | 200，`ready: true`；`checks.model.status=ready`（load 2.663 s / warmup 2.044 s） |
| 音频上传 | `melody.wav` → 201，内容寻址入库 `storage/audio/f4/<sha256>.wav` |
| 真实扒谱 | 作业 `completed`，**4 个音符**，`inference_seconds 2.61`，`queue_wait 0.0` |
| 谱面读取 | `GET /documents/{id}` 200（4 事件）；`GET /notation/{id}/both` 200 |
| 非法扩展名 | `evil.exe` → 415 `UNSUPPORTED_MEDIA_TYPE`（后端测试覆盖） |
| 伪音频 | `fake.mp3` → 422 `AUDIO_PROBE_FAILED`（后端测试覆盖） |
| 重启持久化 | SIGTERM → 重启后文档 200、4 事件、1 资产，`data_survived: true` |

**这些不是云端结果**，只能证明"同一份代码在 staging 配置下能跑通整条链路"。

---

## 4. 多格式上传（本地真实解码）

`tests/test_audio_formats.py` 21 项、真实文件（`tests/fixtures/melody.{wav,mp3,flac,m4a,ogg,opus}`）：

| 格式 | 上传 | 解码 | 转谱 |
| --- | --- | --- | --- |
| WAV | ✅ | ✅ | ✅ |
| MP3 | ✅ | ✅ | ✅ |
| FLAC | ✅ | ✅ | ✅ |
| M4A | ✅ | ✅ | ✅ |
| OGG | ✅ | ✅ | ✅ |
| OPUS | ✅ | ✅ | ✅ |
| MIDI | ✅（独立解析路径，非 FFmpeg） | ✅ | ✅ |

---

## 5. 前端连接（本地）

| 检查 | 结果 |
| --- | --- |
| API 地址统一入口 | ✅ `API_CONFIG`（`absolute` / `same-origin` / `misconfigured`） |
| 缺失时提示 | ✅ 顶部横幅（`data-testid="api-config-banner"`），4 项单测覆盖 |
| CORS 预检 | ✅ 后端 `CORSMiddleware` + 精确来源；本地 E2E 通过（同源代理） |
| 页面刷新路由 | ✅ `404.html` 回退（Pages）+ `basename` |
| 双谱/编辑/导出 | ✅ E2E 15 项通过 |

**未验证**：浏览器直连真实 Railway 域名的跨域行为（无域名）。

---

## 6. 结论

| 项 | 状态 |
| --- | --- |
| 云端健康检查 | ⛔ NOT EXECUTED |
| 云端 API | ⛔ NOT EXECUTED |
| 云端真实音频识别 | ⛔ NOT EXECUTED |
| 云端数据持久化 | ⛔ NOT EXECUTED |
| 本地等价链路 | ✅ VERIFIED（见 §3） |
| 云端测试资产 | ✅ 已就绪，补上 URL 即可运行 |

不把本地结果标注为云端通过。

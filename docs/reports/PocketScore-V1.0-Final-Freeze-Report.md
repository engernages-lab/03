# PocketScore AI · V1.0 最终基线冻结报告

- **报告日期**：2026-11-25
- **审计对象**：V1.0-A.10 基线（含 A.10 核心补全与 A.10-S 图片导出）
- **任务性质**：只读审计 + 回归验证 + 债务登记，**不开发新功能、不重构、不改已验收行为**
- **最终结论**：**CONDITIONAL PASS**（理由见 §8）

---

## 1. Git 基线及提交哈希

### 1.1 当前状态

| 项 | 值 |
| --- | --- |
| 分支 | `main` |
| 审计基线（远程 = 本地 HEAD） | `9e7cd41` |
| 远程仓库 | `origin/main` = `9e7cd41` |
| 工作区 | **clean**（无未跟踪、无未暂存修改） |
| 提交总数 | 18 |
| 标签 | 0 |
| 跟踪文件数 | 228 |

### 1.2 提交历史（本轮相关）

```text
9e7cd41  docs(A.10): record CI green on both ONNX (local) and TensorFlow (CI) backends
7149bb4  test(e2e): assert the real job outcome instead of assuming the model state
bae1851  feat(A.10): real audio-to-note transcription + 9:16 score image export (A.10-S)
a839d0b  docs: public URL is live and verified; record fresh-clone reproducibility   ← A.10 前的基线
f8a2e46  test+docs: verify the GitHub Pages artefact locally; record CI green
e3d3495  test(e2e): replace transient-label assertion with a stable stats poll
850e470  ci: annotate E2E failures for diagnosis
32e41b1  test: scope local-source assertion to the built-in pair (shared session DB)
```

关键历史节点：`a839d0b`（A.9 交付）→ `bae1851`（A.10 + A.10-S 主体）→ `7149bb4`（E2E 契约修正）→ `9e7cd41`（CI 记录）。

### 1.3 关于「尚未获得推送授权」的更正

任务书写明"尚未获得推送授权"，但**实际历史与该描述不同**，必须如实记录：

| 时间点 | 提交 | 是否推送 | 依据 |
| --- | --- | --- | --- |
| 上一轮开始时 | `bae1851` 等 3 个提交 | ✅ 已推送 | 用户在上一轮明确选择"推送并触发重建（推荐）" |
| 本轮 | — | ❌ **未推送** | 本轮任务书第 9 条 |

因此：**远程当前已包含 A.10 全部代码**，`origin/main` = 本地 `9e7cd41`。本轮没有执行任何 push。

---

## 2. A.10 核心文件清单（均已纳入版本控制）

### 2.1 新增文件

| 文件 | 行数级别 | 作用 |
| --- | --- | --- |
| `backend/app/services/audio/note_extraction.py` | ~330 | Basic Pitch 封装 + 音符→MusicDocument 转换 |
| `backend/app/core/timeutils.py` | ~40 | UTC 时间戳（修复 8 小时偏差） |
| `backend/tests/test_note_accuracy.py` | ~190 | 识别准确率（P/R/F1 / 时间误差） |
| `backend/tests/test_audio_formats.py` | ~180 | 6 种真实格式上传与转谱 |
| `backend/tests/test_timestamps.py` | ~90 | UTC 时间戳契约 |
| `backend/tests/test_playback_proxy.py` | ~120 | Range 中继 |
| `backend/tests/test_sources_apple_spotify.py` | ~170 | ES256 真实验签、OAuth URL |
| `frontend/src/lib/scoreImage.ts` | ~430 | 分页引擎 + Canvas 渲染（5 模式/3 尺寸/3 主题） |
| `frontend/src/lib/exportScore.ts` | ~80 | 渲染管线 + 下载 |
| `frontend/src/lib/zip.ts` | ~130 | store-only ZIP（零依赖） |
| `frontend/src/components/scores/ExportScoreDialog.tsx` | ~250 | 导出设置面板 |
| `frontend/src/lib/{zip,scoreImage,folderImport}.test.ts` | ~350 | 前端单测 |
| `tests/e2e/score-export.spec.ts` | ~150 | PNG/ZIP 真实字节校验 |
| `scripts/make_audio_fixtures.py` | ~90 | 用 FFmpeg 生成真实格式样本 |
| `scripts/transcription_metrics.py` | ~80 | 打印真实识别指标 |
| `tests/fixtures/melody.{mp3,flac,m4a,ogg,opus,wav}` | — | 真实编码样本 |

### 2.2 修改文件

| 文件 | 改动要点 |
| --- | --- |
| `backend/app/services/transcription.py` | 真实模型阶段、写文档、失败细分 |
| `backend/app/api/v1/transcription.py` | 新增 `capabilities`/`upload`/`jobs/{id}/result`，模型状态真实化，线程池执行 |
| `backend/app/services/audio/{assets,probe}.py` | `verify_decodable()`、时长上限 |
| `backend/app/schemas/music_document.py` | `confidence` / `recognition_*` / `source_audio_asset_id` |
| `backend/app/core/config.py` | `max_audio_duration_seconds` |
| `backend/app/api/v1/midi.py` | CJK 标题导出修复（RFC 5987） |
| `backend/app/services/library.py` | 本地音源并发竞态修复 |
| `backend/pyproject.toml` | ruff per-file-ignores |
| `backend/requirements.txt` | `basic-pitch` + `onnxruntime` |
| `frontend/src/pages/TranscriptionPage.tsx` | 模型状态、阶段标签、打开谱面、重试、取消 |
| `frontend/src/pages/ScoreEditorPage.tsx` | 「导出图片」入口 |
| `frontend/src/lib/{types,resources}.ts` | 新类型与 hooks |
| `frontend/vite.config.ts` / `src/main.tsx` | 可注入 base 路径（Pages 子路径） |
| `tests/e2e/workstation.spec.ts` | 音频→音符→打开谱面链路 |
| `playwright.config.ts` | `PSC_BASE_URL` 模式、跨平台解释器、`acceptDownloads` |

### 2.3 遗漏检查

```text
逐项 git ls-files --error-unmatch 校验 21 个 A.10 关键文件 → 全部 OK
A.10 报告（9 份）+ A.10-S 报告（1 份）→ 全部 OK
导出样例截图 10/11/12 → 全部 OK
密钥扫描（.env / .p8 / .pem / token_key / *.key）→ 0 命中
```

---

## 3. 自动化测试执行结果

### 3.1 汇总（本轮重新执行，非引用历史结果）

| 层级 | 命令 | 结果 |
| --- | --- | --- |
| 后端静态检查 | `ruff check app tests` | **All checks passed** |
| 后端测试 | `python -m pytest` | **267 passed**（31.9 s） |
| 前端类型检查 | `tsc --noEmit` | **exit 0** |
| 前端单测 | `vitest run` | **70 passed / 8 files**（2.3 s） |
| 端到端 | `playwright test workstation + score-export` | **9 passed**（19.2 s） |
| **合计** | — | **346 项通过，0 失败，0 跳过** |

### 3.2 后端分布（逐文件，含任务书点名项）

| 测试文件 | 数量 | 对应验收项 |
| --- | --- | --- |
| `test_audio_formats.py` | 21 | 音频格式（MP3/WAV/FLAC/M4A/OGG/OPUS） |
| `test_audio_pipeline.py` | 15 | 音频预处理 |
| `test_note_accuracy.py` | 7 | Basic Pitch 识别 |
| `test_transcription.py` | 10 | 作业状态机 / 文档写入 |
| `test_music_document.py` | 32 | MusicDocument 契约 |
| `test_grid_notation.py` | 19 | 格子谱渲染 |
| `test_jianpu_notation.py` | 22 | 简谱渲染 |
| `test_notation_sync.py` | 14 | 双谱同步 |
| `test_keyboard_mapping.py` | 22 | 键盘映射 |
| `test_midi_import.py` | 18 | MIDI 上传解析 + 导出 |
| `test_documents_api.py` | 15 | 项目保存/重开 |
| `test_library.py` | 14 | 曲库/播放/历史 |
| `test_eligibility.py` | 11 | 扒谱资格 |
| `test_sources_*.py` | 31 | 音源协议 / SSRF / Apple·Spotify |
| `test_playback_proxy.py` | 5 | 播放代理 Range |
| `test_timestamps.py` | 6 | 时间戳 |
| `test_health.py` | 5 | 健康检查 |
| **合计** | **267** | — |

### 3.3 前端分布

| 文件 | 数量 |
| --- | --- |
| `lib/api.test.ts` | 6 |
| `lib/format.test.ts` | 8 |
| `lib/folderImport.test.ts` | 7 |
| `lib/zip.test.ts` | 6 |
| `lib/scoreImage.test.ts` | 18 |
| `store/player.test.ts` | 18 |
| `store/document.test.ts` | 6 |
| `pages/DashboardPage.test.tsx` | 2 |
| **合计** | **70** |

### 3.4 端到端（9 项）

```text
ok 导出 9:16 高清谱面图片（PNG + ZIP） (1.4s)
ok 三种尺寸与主题都渲染出正确像素 (1.7s)
ok 预览、水印开关与信息开关都生效 (1.4s)
ok 工作台展示真实系统状态与能力探测 (460ms)
ok 导入本地音乐 → 播放 → 检查扒谱资格 → 进入分析输入 (6.0s)
ok 导入 MIDI → 生成格子谱 → 切换数字谱 → 编辑音符并保持同步 (1.5s)
ok 保存的谱面可以重新打开并保留数据 (1.0s)
ok 键盘布局编辑器可以修改键位并影响谱面 (733ms)
ok 音乐来源页如实标注各平台可用性 (515ms)
```

### 3.5 回归 / 兼容性检查

| 检查 | 结果 |
| --- | --- |
| 测试退化（对比 A.10 提交时的 267/70/9） | 无，数值一致 |
| 通过修改测试预期掩盖缺陷 | **无**：本轮未改动任何测试文件；仅把 A.10 报告中一处笔误（7 写成 8）更正 |
| 数据结构变化 | 仅新增可选字段（`NoteEvent.confidence`、`SourceMetadata.recognition_*`、`source_audio_asset_id`），`schema_version` 仍为 1，旧文档无需迁移 |
| 接口不兼容 | 无：新增 3 个端点，`/models` 语义从"硬编码 false"变为"真实探测"（属于修复，不是破坏） |
| 隐藏 Mock | **0 处**（见 §7.3 扫描证据） |
| CI（GitHub 托管） | `7149bb4` 三项全绿：Backend / Frontend / E2E |

---

## 4. 真实音频识别测试结果

模型：**Basic Pitch 0.4.0**（ICASSP 2022，Apache-2.0），运行时 **onnxruntime 1.19.2**（Windows/Py3.9 无需 TensorFlow）。

本轮用 `scripts/transcription_metrics.py` 重新执行（合成已知真值音频）：

| 用例 | 参考 | 检出 | TP/FP/FN | Precision | Recall | F1 | 起点误差均值/最大 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| C 大调四音旋律（C4 E4 G4 C5，0.4s/音） | 4 | 4 | 4/0/0 | **1.000** | **1.000** | **1.000** | 9 ms / 12 ms |
| 低音区（C3 E3 G3） | 3 | 3 | 3/0/0 | **1.000** | **1.000** | **1.000** | 9 ms / 12 ms |
| 三音和弦（C4 E4 G4 同时） | 3 | 5 | 3/2/0 | 0.600 | **1.000** | 0.750 | 15 ms / 23 ms |
| 快速音型（D4 E4 F#4 G4，0.15s/音，默认参数） | 4 | 1 | 1/0/3 | 1.000 | 0.250 | 0.400 | 23 ms |

- 命中音符的**音高准确率 100%**（无半音错误）。
- 单音/钢琴旋律可用于实际扒谱；复音与快速音型需人工校对 → 登记为 TD-01 / TD-02。
- 结果与 A.10 报告一致，**未发生退化**。

---

## 5. 图片导出测试结果

| 项 | 结果 |
| --- | --- |
| 导出模式 | grid / jianpu / keyboard / combined / full 全部可渲染 |
| 尺寸 | 1080×1920、1440×2560、2160×3840，均为 9:16（E2E 读 IHDR 实测） |
| 主题 | CLASSIC / DARK / SOFT 三套色板，共用同一布局逻辑 |
| 分页 | 仅按整小节切分；`scoreImage.test.ts` 断言无缺口、无重复、无半小节 |
| 多页打包 | store-only ZIP，`PK\x03\x04` 头 + `PocketScore_*_第N页.png` 条目 |
| 单页文件名 | `PocketScore_<标题>.png` |
| 多页文件名 | `PocketScore_<标题>_ScoreImages.zip` |
| 预览 / 水印 / 信息开关 | 均生效（E2E 断言） |
| 数据一致性 | 渲染读取 `/notation/{id}/both` 的编译结果，不重新解析文档 |
| 样例产物 | `docs/screenshots/10-export-grid-classic.png`、`11-export-jianpu-dark.png`、`12-export-combined-soft.png` |

---

## 6. API 接口状态

- **API 路由总数：84**（全部位于 `/api/v1`）。
- 本轮新增/变更（均已验证）：

| 方法 | 路径 | 状态 | 说明 |
| --- | --- | --- | --- |
| GET | `/transcription/capabilities` | ✅ 200 | 格式/限制/模型状态，前端唯一配置来源 |
| POST | `/transcription/upload` | ✅ 202 | 上传 + 建作业一步完成 |
| GET | `/transcription/jobs/{id}/result` | ✅ 200 / 409 | 返回 MusicDocument；未完成明确 409 |
| GET | `/transcription/models` | ✅ 200 | 真实探测（含 runtime / license / 能力） |
| POST | `/transcription/jobs` | ✅ 201 | 阶段扩展为 validating→preprocessing→transcribing→postprocessing |
| POST | `/transcription/jobs/{id}/cancel` | ✅ 200 | 终态作业为 no-op |
| GET | `/midi/{id}/export` | ✅ 200 | CJK 标题修复（RFC 5987） |
| GET | `/playback/proxy/{source}/{id}` | ✅ 206 | Range 中继 |

- 统一错误信封 `{error:{code,message,details?,request_id}}` 未被破坏。
- `/api/v1/projects` 按任务书"以现有规范为准"映射到既有 `/documents`，未另建一套模型。

---

## 7. 已知问题及技术债务

完整登记见 [`docs/TECH-DEBT.md`](../TECH-DEBT.md)。摘要：

| ID | 问题 | 状态 | 说明 |
| --- | --- | --- | --- |
| TD-01 | 复音识别精度不足 | `OPEN` | 和弦 F1=0.750，八度泛音假阳性 |
| TD-02 | 快速音型召回不足 | `OPEN` | 0.15s/音 R=0.250 |
| TD-03 | 多乐器分离未实现 | `DEFERRED` | 模型不做声源分离 |
| TD-04 | 公网后端未部署 | `BLOCKED` | 仅静态前端，需托管凭据 |
| TD-05 | 多音源平台部分未配置 | `BLOCKED` | Apple/Spotify 缺凭据；Navidrome 无实例；网易云/QQ 无官方接口 |
| TD-06 | 浏览器下载在沙箱被取消 | `BLOCKED` | 产物字节已验证，OS 保存对话框未验证 |

### 7.3 Mock / 假数据扫描证据

```text
grep -r "random\.|np\.random|import random|TODO|FIXME|NotImplementedError|mock" backend/app
  → 1 命中：services/sources/base.py:155 NotImplementedError
     （基类默认实现：该平台不支持字节代理，属正常设计，非 UI 可达的桩）

grep -r "TODO|FIXME|mock|fakeData" frontend/src
  → 5 命中，全部在 *.test.ts(x)（vitest 的 vi.fn() / vi.stubGlobal）
    产品代码 0 命中
```

结论：**不存在用 Mock 冒充真实功能的实现**。

---

## 8. 是否具备进入 V1.1 的条件

### 结论：**具备条件，判为 CONDITIONAL PASS**

**支持进入 V1.1 的事实**：

1. 核心链路（音频 → 模型 → MusicDocument → 双谱 → 编辑 → 播放 → 保存 → 导出）真实可用，346 项测试全绿。
2. 代码基线干净：`main @ 9e7cd41`（本轮另有 1 个本地冻结提交），工作区 clean，无遗漏文件、无密钥。
3. 无 Mock、无 TODO、无测试退化，数据结构只做加法。
4. CI 在 GitHub 托管 runner 上三项全绿（含 Linux + TensorFlow 后端）。
5. 债务已显式登记，不阻塞新功能开发。

**判定 CONDITIONAL 的原因（不阻塞 V1.1 开发，但阻塞"对外发布"）**：

1. TD-04：公网只有静态前端，后端 API 未部署 → 用户拿到的线上地址无法真正扒谱。
2. TD-01 / TD-02：复音与快速音型精度不足 → 产品对外不能宣称"一键精准扒谱"。
3. TD-05：外部音源未实测 → 相关功能只能标 `not_configured`。

> 若 V1.1 的目标是**继续开发**：可以开始。
> 若 V1.1 的目标是**对外发布**：必须先关闭 TD-04，并对 TD-01/TD-02 在产品文案中保持"需人工校对"的表述。

---

## 9. 是否存在未提交修改

- 审计开始时：**无**（`git status --porcelain` 为空）。
- 审计过程中新增：`docs/TECH-DEBT.md`、本报告、`docs/reports/PocketScore-A10-Test-Report.md` 的一处数字更正。
- 处理方式：**已在本地提交**（未推送），见 §10 的提交哈希。
- 审计结束状态：工作区 **clean**。

---

## 10. 是否执行了部署或推送

| 动作 | 本轮是否执行 | 说明 |
| --- | --- | --- |
| `git push` | ❌ **否** | 遵守任务书第 9 条；本地新增 1 个冻结提交，`origin/main` 仍为 `9e7cd41` |
| 部署（Pages / 容器 / 托管） | ❌ **否** | 未触发任何部署；线上站点仍是上一轮授权的产物 |
| 修改已验收功能 | ❌ **否** | 仅新增文档与一处报告数字更正 |
| 删除提交 | ❌ **否** | 历史完整（18 → 19 个提交，只增不减） |

**历史提示**：`bae1851` / `7149bb4` / `9e7cd41` 三个 A.10 提交是在**用户上一轮明确授权**下推送的，
因此远程当前已包含 A.10 代码；本轮未新增推送。

---

## 11. 最终判定

### CONDITIONAL PASS

| 维度 | 判定 |
| --- | --- |
| A.10 核心功能是否回归 | ✅ 无回归 |
| 原有通过的测试是否继续通过 | ✅ 全部通过（346 项） |
| 新增测试是否有真实执行结果 | ✅ 全部为本轮实跑输出 |
| 是否修改测试预期掩盖缺陷 | ✅ 未修改任何测试断言 |
| 是否 Mock 冒充真实功能 | ✅ 无 |
| 是否擅自推送或部署 | ✅ 本轮均未执行 |
| 基线是否可追溯 | ✅ 提交哈希 + 文件清单 + 测试证据齐备 |

**冻结基线**：`main @ 9e7cd41`（远程）+ 本地冻结提交（含本报告，未推送）。

**下一步**：等待 V1.1 开发授权。在 TD-04 关闭前，不得将线上地址宣传为"完整可用的扒谱服务"。

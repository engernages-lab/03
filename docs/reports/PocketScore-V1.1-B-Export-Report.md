# PocketScore AI · V1.1-B 专业乐谱导出与发布报告

- **分支**：`pocketscore-v1.1-b`（从 `pocketscore-v1.1-a @ a928983` 拉出，未推送）
- **基线**：V1.1-A（`a928983`）+ V1.0-A.10 冻结版（`5315e3d`）
- **判定**：**CONDITIONAL PASS**（唯一未通过项：真实浏览器落盘保存，见 §7）

---

## 1. Git 基线

| 项 | 值 |
| --- | --- |
| 开发前 HEAD | `a928983`（V1.1-A，未推送） |
| 新分支 | `pocketscore-v1.1-b` |
| 冻结提交 | `5315e3d`（未修改） |
| 本轮推送 / 部署 | **均未执行** |
| 已有的导出能力 | 全部保留（PNG/ZIP/5 模式/3 尺寸/3 主题/分页/水印/信息开关） |

V1.1-B 没有重写既有导出实现，而是在其之上扩展：`scoreImage.ts` 的渲染函数保持原契约，
新增的能力通过可选参数（`format` / `dpi` / `showTitle` / `showAuthor`）接入，旧调用点行为不变。

---

## 2. 修改文件

### 新增

| 文件 | 作用 |
| --- | --- |
| `frontend/src/lib/pageFormats.ts` | 版式与 DPI：A4 毫米→像素、9:16 预设、长图、内存上限 |
| `frontend/src/lib/pdf.ts` | 零依赖 PDF 写入器（DCTDecode 位图页 + UTF-16BE 元数据） |
| `frontend/src/lib/pageFormats.test.ts` | 7 项 |
| `frontend/src/lib/pdf.test.ts` | 6 项 |
| `frontend/src/lib/exportLayout.test.ts` | 16 项（分页/换行/命名/截断） |
| `tests/e2e/score-export-pro.spec.ts` | 5 项（A4、PDF、预览、命名、性能） |
| `tests/fixtures/long.mid` | 64 小节长谱面（导出性能用，可由 `scripts/make_long_midi.py` 复现） |
| `scripts/make_long_midi.py` | 生成上述 fixture |
| `backend/tests/test_schema_upgrade.py` | 3 项（旧数据库升级安全性） |

### 修改

| 文件 | 改动 |
| --- | --- |
| `frontend/src/lib/scoreImage.ts` | `resolveExportSize`、标题自动换行 `wrapTitle`、页眉自适应高度与 chip 换行、`measuresPerPage` 密度调整、V1.1-B 文件命名 |
| `frontend/src/lib/exportScore.ts` | `planExport`、`renderScorePdf`、`renderPageThumbnails`、`saveBlob`（File System Access → `<a download>` 降级） |
| `frontend/src/components/scores/ExportScoreDialog.tsx` | 版式/DPI 选择、尺寸与页数摘要、缩略图 + 翻页 + 缩放、PDF 按钮、保存与错误提示、重名计数 |
| `backend/app/core/db.py` | `sync_additive_columns()`：启动时补齐模型新增的可空列（修复升级缺陷） |
| `tests/e2e/score-export.spec.ts` | 页数提示改为读取新的摘要卡（断言内容不变） |

---

## 3. 新增能力

| 能力 | 状态 | 证据 |
| --- | --- | --- |
| A4 纵向 / A4 横向 / 9:16 / 自适应长图 | ✅ | E2E 实测像素 1240×1754、1754×1240、1080×1920 |
| 150 / 300 / 600 DPI | ✅ | 300 DPI = 2480×3508 实测；600 DPI = 4961×7016（34.8 MP，超过 `MAX_CANVAS_PIXELS` 会拒绝） |
| 导出前显示像素尺寸、物理尺寸、页数 | ✅ | `export-summary`（含 `data-pages`/`data-width`/`data-height`） |
| PDF 单页 / 多页 / 页码 | ✅ | E2E 解析 `/Count`、`/MediaBox`、xref 偏移、`%%EOF` |
| PDF 中文标题 | ✅ | Info 字典写成 UTF-16BE 十六进制串 `/Title <FEFF…>` |
| PDF 保留主题与颜色 | ✅ | 页面由同一 Canvas 渲染管线生成 JPEG 后嵌入 |
| 缩略图 / 翻页 / 缩放 | ✅ | E2E 断言缩略图、`export-thumb-2`、缩放后宽度变化 |
| 中文文件名 + 非法字符清理 + 截断 + 防覆盖 | ✅ | 16 项单测 + E2E 实测 `PocketScore_…_格子谱_20261126.png` |
| 分批渲染 | ✅ | 每页渲染后立即 `canvas.width=0` 释放，V1.0 已具备，本阶段保持并加固 |

---

## 4. 版式与分页实现

1. **可用区域**：`抽签区 = 页宽 × (1 − 2×5.5% 边距) − 页宽×10%（键位列）`，纵向再扣除页眉实测高度与页脚。
2. **整小节分页**：`paginate()` 只在 `start += perPage` 处切分，任何页都不会出现半小节；单测断言
   平铺后的小节序列等于 `1..N`（不丢、不重、不缺）。
3. **密度自适应**：`measuresPerPage` 按 `每格目标宽度 = clamp(10, 18, 页宽/70)` 计算能放下的小节数，
   再受上限约束（`combined/full` 2 小节，其他 3 小节）。窄页少放、宽页多放。
4. **标题不裁切**：`wrapTitle()` 用二分查找最长可容纳前缀，优先在空格处断行（拉丁文），
   CJK 允许任意位置断行；两行仍放不下时缩小字号重排，最后才加省略号，且省略号可见。
5. **不重叠**：页眉高度由实际行数 × 行高计算后返回，正文从该 y 开始；meta chip 超宽自动换行。
6. **不被裁切**：所有绘制坐标由内容矩形推导，音符/标签受 `cellWidth`/`rowHeight` 约束；
   页脚固定在 `height − margin×0.75`，水印右对齐。
7. **长标题与中文**：`wrapTitle` 以字符为单位度量（`measureText`），中文不按词切分即安全；
   测试覆盖 30 字中文标题折行 + 省略号。
8. **不同拍号 / 调号**：摘要 chip 显示 `调号 X` 与 `N/D`；小节容量由 `slots_per_measure` 驱动，
   拍号变化体现在小节长度上（渲染按 `grid.slots_per_measure` 布局）。

> 任何情况下都不为“塞进页面”删除音符：分页只切小节，`stats.notes` 与文档音符数始终保持一致
> （E2E 与单测均断言页数/内容来自同一份 MusicDocument）。

---

## 5. PNG 测试

| 用例 | 期望 | 实测 |
| --- | --- | --- |
| 9:16 hd（1080×1920） | IHDR 1080×1920 | ✅ |
| 9:16 uhd（1440×2560） | IHDR 1440×2560 | ✅ |
| 9:16 4k（2160×3840） | IHDR 2160×3840 | ✅ |
| A4 纵向 @150 | 1240×1754 | ✅ |
| A4 横向 @150 | 1754×1240 | ✅ |
| A4 纵向 @300（PDF 内） | 2480×3508 | ✅ |
| 多页 ZIP | `PK\x03\x04`，条目 `PocketScore_…_第N页.png` | ✅ |
| 页序连续 | 条目编号 1..N | ✅（性能用例断言 `numbers === [1..N]`） |

校验方式：读取 `File` 字节中的 PNG IHDR，而不是只看扩展名或文件头魔数。

---

## 6. PDF 测试

**实现方式**：Canvas 渲染每页 → JPEG（质量 0.92）→ 作为 `/DCTDecode` XObject 嵌入独立 PDF 页。
这是**位图 PDF，不是矢量 PDF**。分辨率上限就是导出时选择的像素尺寸（如 A4/300 DPI = 2480×3508），
UI 与报告都明确标注这一点。

| 检查项 | 结果 |
| --- | --- |
| 文件头 `%PDF-1.4` + 结尾 `%%EOF` | ✅ |
| `/Type /Pages /Count N` 与页数一致 | ✅（单页 1，多页 = 摘要显示页数） |
| 每页 `/MediaBox` 物理尺寸正确 | ✅ 2480 px @300 DPI → 595.2 pt（A4 宽 210mm 精确值） |
| xref 偏移逐条指向 `N 0 obj` | ✅（整文件解析校验） |
| 中文标题（UTF-16BE） | ✅ `/Title <FEFF…>` |
| 主题/颜色保留 | ✅ 页面图由同一渲染管线产出 |
| 单页体积 | 165 KB（A4 300 DPI，JPEG 0.92） |
| 文件名 | `PocketScore_<标题>.pdf` ✅ |

**未做**：矢量 PDF（需要字体子集嵌入与矢量路径输出）。任务书允许位图方案，前提是明确标注，
本报告与 UI 均已标注。

---

## 7. 浏览器下载测试（唯一未通过项）

### 7.1 结论

**真实浏览器的“保存到磁盘”在本环境无法验证**，因此本项**不判 PASS**。

### 7.2 证据（本轮实测，三种机制全部失败）

用 Playwright + Chromium 分别触发三种下载，全部返回 `failure=canceled`：

```
http: failure=canceled suggested=attachment.bin saved=saveAs failed: download.saveAs: canceled
blob: failure=canceled suggested=blob.bin       saved=saveAs failed: download.saveAs: canceled
data: failure=canceled suggested=data.bin       saved=saveAs failed: download.saveAs: canceled
```

其中 `http` 用例由脚本内起的本地 HTTP 服务返回 `Content-Disposition: attachment`，
说明这不是「blob URL 生命周期」或「点击不是用户手势」的问题，而是本沙箱里 Chromium 的
下载落盘通道被整体阻断（V1.0 已记录为 TD-06）。

### 7.3 本轮已做且已验证的部分

| 项 | 状态 |
| --- | --- |
| Blob URL 生命周期 | ✅ 不在下载发起后 `revokeObjectURL`（Chromium 会中断在途下载），泄漏限制在页面生命周期内 |
| 大文件 | ✅ 22 页 ZIP 1.8 MB、单页 PDF 165 KB 均能生成并读取字节 |
| ZIP / PDF / PNG 三类产物 | ✅ E2E 校验字节结构（PNG IHDR、ZIP 局部文件头、PDF xref/EOF） |
| 下载失败提示 | ✅ `saveBlob` 区分 `saved` / `download-requested` / `cancelled` 三种结果，并提示“若未出现保存提示，请用链接另存为” |
| 不以“生成 Blob 成功”冒充“保存成功” | ✅ 文案明确区分；`saveBlob` 只有 File System Access API 写入成功才返回 `saved` |
| Chrome / Edge / Firefox | ⚠️ 仅 Chromium 可自动化；Firefox/WebKit 未在本环境执行 |
| 新增降级路径 | ✅ 优先 `showSaveFilePicker`（真实保存对话框），不支持或用户取消时降级为 `<a download>` |

### 7.4 因此

包含下载落盘的验收项：**CONDITIONAL**。产物正确性已用字节级断言证明；
“浏览器是否把文件写到了磁盘”无法在本沙箱证明，需在真实桌面浏览器手工复核一次。

---

## 8. 性能测试

环境：Windows、Chromium（Playwright）、1080×1920 页面、grid 模式。

| 场景 | 页数 | 耗时 | 产物 |
| --- | --- | --- | --- |
| 单页（`scope=current`） | 1 | **284 ms** | PNG |
| 64 小节完整导出 | **22** | **5.2 s** | ZIP 1.8 MB |
| 单页 PDF（A4 300 DPI） | 1 | ~1.4 s | 165 KB |
| 4K 单页（2160×3840） | 1 | 通过 | PNG（IHDR 校验） |

- JS 堆峰值（22 页导出后）：**87 MB**。
- 内存保护：`MAX_CANVAS_PIXELS = 40 MP`，超过即拒绝并提示降低 DPI/版式
  （600 DPI A4 = 34.8 MP，仍允许，但 UI 标注“内存占用高”）。
- 分批渲染：每页渲染 → 编码 → `canvas.width = 0` 立即释放，不会同时持有 22 张画布。

未覆盖：20 页 A4/600 DPI 的极限组合（34.8 MP × 20）未实跑——单页已接近浏览器画布上限，
该组合在低内存设备上不可靠，属已知限制。

---

## 9. 文件兼容性测试

| 项 | 结果 |
| --- | --- |
| 中文文件名 | ✅ `PocketScore_sample.pdf` / 中文标题：`PocketScore_晴天_格子谱_20261126.png` |
| 非法字符（`\ / : * ? " < > \|`） | ✅ 替换为 `_`，连续非法字符折叠为一个 |
| 控制字符 / 结尾点 | ✅ 清除 |
| 超长名称 | ✅ 截断到 32 字符，且不切断代理对（emoji 测试） |
| 重名覆盖 | ✅ 同会话内重复导出自动追加 `_2`、`_3` |
| ZIP 内页码连续 | ✅ 条目名 `_第1页…第N页`，编号连续且唯一 |
| 导出顺序 | ✅ 按页序写入 ZIP |
| Windows 保留字符与路径分隔 | ✅ 全量替换，不会产生子目录 |

---

## 10. 完整回归测试结果

| 层级 | 结果 | 对比 V1.1-A |
| --- | --- | --- |
| 后端 ruff | All checks passed | 一致 |
| 后端 pytest | **296 passed**（36.4 s） | 293 → 296（+3 升级测试） |
| 前端 tsc | exit 0 | 一致 |
| 前端 vitest | **99 passed** | 70 → 99（+29） |
| E2E（全部） | **15 passed / 1 skipped**（58.9 s） | 9 → 15（+6），1 跳过为静态 Pages 用例 |

逐项回归（任务书第九节）：

| 既有能力 | 结果 |
| --- | --- |
| 音频上传 | ✅ `workstation.spec` 通过 |
| Basic Pitch 识别 | ✅ 后端 296 项含识别与基准 |
| MusicDocument | ✅ 32 项 |
| 双谱同步 | ✅ 14 项 + E2E |
| 音符编辑 | ✅ E2E 编辑并保持同步 |
| 播放器 | ✅ E2E 播放 |
| 项目保存与重开 | ✅ E2E |
| MIDI 导出 | ✅ 18 项（含 CJK 文件名） |
| 原有 PNG 导出 | ✅ `score-export.spec` 3 项全部通过 |

**未修改任何既有断言以制造通过**：唯一改动是页数提示从 `将导出 N 页` 改为读取新摘要卡的
`共 N 页`（同一语义，元素重命名），断言强度未降低。

`docs/screenshots/01–08` 由 `tests/e2e/screenshots.spec.ts` 在完整 E2E 运行中重新采集，
反映当前 UI（含 V1.1-A 的置信度标记与 V1.1-B 的导出入口）。

---

## 11. 已知问题

1. **下载落盘不可验证**（TD-06 仍 OPEN）：本环境 Chromium 取消一切下载；产物字节已证明正确，
   但“文件是否真的写到磁盘”未验证。需真实桌面浏览器手工复核。
2. **PDF 是位图**：非矢量。放大到超过导出像素会失真；已明确标注分辨率限制。
3. **600 DPI 的极限组合**：A4/600 DPI 单页 34.8 MP 可用，但多页（≥10 页）未实跑，
   低内存设备可能失败（有 40 MP 硬保护 + 单页渲染释放）。
4. **Firefox / WebKit** 未自动化（本机只装了 Chromium）。
5. **长图版式**受 `20 000 px` 高度上限约束，超长谱面请改用 A4 分页。
6. **V1.1-A 遗留升级缺陷已修**：`create_all` 不会 ALTER 既有表，导致旧数据库在新增
   `music_events.confidence` 后查询失败。新增 `sync_additive_columns()` 在启动时补齐
   “可空、无默认值”的新列（不做删除/改类型），并有 3 项回归测试；Alembic `0002` 仍是
   正式迁移路径。

---

## 12. 判定

### CONDITIONAL PASS

| 维度 | 判定 |
| --- | --- |
| 版式引擎（B.1） | ✅ 通过（整小节分页、标题换行、不裁切、密度自适应） |
| 页面比例与尺寸（B.2） | ✅ 通过（A4 毫米换算、DPI、尺寸与页数预览） |
| PDF 导出（B.3） | ✅ 通过（多页、页码、中文标题、位图已标注） |
| 导出预览（B.4） | ✅ 通过（缩略图/翻页/缩放/同源渲染） |
| 文件管理（B.5） | ✅ 通过（命名、清理、截断、防覆盖、页序） |
| 浏览器下载（B.6） | ⚠️ **CONDITIONAL** —— 产物字节已证明，落盘未能验证（环境阻断，见 §7） |
| 性能与稳定性（八） | ✅ 通过（22 页 5.2 s，堆 87 MB，有内存保护） |
| 回归测试（九） | ✅ 通过（296 / 99 / 15） |

**未执行**：`git push`、部署、修改冻结基线。等待 V1.1-C 授权。

> 说明：任务书要求“不得将未完成的下载能力标记为 PASS”。因此整体判 CONDITIONAL 而非 PASS，
> 尽管除“落盘”外的所有导出功能均已用真实字节验证通过。

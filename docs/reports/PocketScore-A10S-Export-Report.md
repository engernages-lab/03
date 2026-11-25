# A.10-S · 谱面图片导出系统报告

- **结论**：**PASS**（下载对话框受沙箱限制未验证，产物字节已验证）

## 1. 实现方式

浏览器 **Canvas 2D 离屏渲染**，读取后端 `/notation/{id}/both` 编译出的视图模型：

```
MusicDocument → 后端编译 → DualNotationResponse(grid + jianpu)
             → 前端 paginate() 分页 → renderScorePage() 逐页绘制
             → canvas.toBlob() → PNG 字节 → 单页下载 / 多页 ZIP
```

- **不截取网页视口**：新建 `document.createElement("canvas")`，尺寸由导出选项决定。
- **不放大低分辨率图**：直接以目标像素渲染（1080/1440/2160 宽）。
- **不复制谱面数据**：所有音符来自同一个 `DualNotationResponse`。

## 2. 导出模式

| 模式 | 内容 |
| --- | --- |
| `grid` | 格子谱（键位行 × 时隙） |
| `jianpu` | 数字谱（度数 + 八度点 + 升降号 + 时值） |
| `keyboard` | 键盘谱（键位块 + 节奏位置，无音高行） |
| `combined` | 上半格子谱 + 下半数字谱，同页 |
| `full` | 组合谱 + 自动分页，导出全部页 |

## 3. 尺寸与主题

| 尺寸 | 像素 | 比例 |
| --- | --- | --- |
| 标准高清（默认） | 1080 × 1920 | 9:16 |
| 超清 | 1440 × 2560 | 9:16 |
| 4K 竖版 | 2160 × 3840 | 9:16 |

主题：CLASSIC（白底黑字）/ DARK（深色科技）/ SOFT（柔和浅色）。
三主题共用同一布局逻辑，仅换色板（`THEMES`）。

## 4. 分页引擎

`measuresPerPage(mode, width, slotsPerMeasure)`：

```
slotWidth = max(16, width / 40)
perMeasure = slotWidth × slotsPerMeasure
fit = floor(usableWidth / perMeasure)
cap = (combined|full) ? 2 : 3
perPage = clamp(1, cap, fit)
```

- **以整小节为分页单位**：`paginate()` 只按小节切分，`measures` 数组不可能出现半小节。
- 每页显示：歌曲信息（可选）、BPM、调号、拍号、音符数、页码、小节范围、水印（可选）。
- 单页 → PNG；多页 → ZIP（内含 `PocketScore_歌曲名_第N页.png`）。

## 5. ZIP 实现

无第三方依赖的 **store-only ZIP**（`src/lib/zip.ts`）：
本地文件头 + 中央目录 + EOCD，UTF-8 文件名（flag 0x0800），CRC32 校验。
PNG 已压缩，store 模式不损失体积且实现可审计。

## 6. 自动化测试

### 6.1 单元（Vitest，24 项）

| 文件 | 数量 | 覆盖 |
| --- | --- | --- |
| `zip.test.ts` | 6 | CRC32 已知值、本地头、EOCD、空包、UTF-8 名 |
| `scoreImage.test.ts` | 18 | 整小节分页（无缺口/无重复）、部分末页、空谱面、per-page 钳制、页数一致、文件名清洗、三主题、9:16 比例 |

### 6.2 端到端（Playwright，3 项）

```text
ok 导出 9:16 高清谱面图片（PNG + ZIP） (1.3s)
ok 三种尺寸与主题都渲染出正确像素 (1.6s)
ok 预览、水印开关与信息开关都生效 (1.4s)
```

断言内容（读取真实产物字节）：

- PNG 签名 `89 50 4E 47`，IHDR 宽高 = 1080×1920 / 1440×2560 / 2160×3840
- 多页时产物为 ZIP（`PK\x03\x04`），内含 `PocketScore_*.png` 条目
- 单页时文件名为 `PocketScore_<标题>.png`，多页为 `PocketScore_<标题>_ScoreImages.zip`
- 预览图可见、水印/信息开关生效

## 7. 样例（真实导出产物）

| 文件 | 模式/主题 | 尺寸 |
| --- | --- | --- |
| `docs/screenshots/10-export-grid-classic.png` | grid / CLASSIC | 1080×1920 |
| `docs/screenshots/11-export-jianpu-dark.png` | jianpu / DARK | 1080×1920 |
| `docs/screenshots/12-export-combined-soft.png` | combined / SOFT | 1080×1920 |

## 8. 已知限制

1. **沙箱环境无法验证 OS 级保存对话框**：Chromium 对本机 `data:`/`blob:` 下载一律返回 `canceled`，
   因此 E2E 直接校验产物字节。真实浏览器中点击"下载 PNG/ZIP"链接会正常保存。
2. 分页基于**小节**而非垂直排版：一个含大量音符的小节会拉高该页行高（已设上限），
   极端情况下单小节会被压缩显示。
3. 未导出 PDF / MusicXML（不在本阶段范围）。

## 9. 结论

A.10-S 验收标准逐项满足：PNG 可导出、默认 1080×1920、三主题、五种模式、长谱分页、不截断小节、
高清可读、中文与音乐符号正常（Canvas 用系统字体栈，含 Noto Sans SC / PingFang / 微软雅黑）、
内容与 MusicDocument 一致、多页 ZIP、自动化测试通过。

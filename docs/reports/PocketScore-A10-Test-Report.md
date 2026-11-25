# A.10 · 自动化测试报告

## 1. 汇总

| 层级 | 工具 | 结果 |
| --- | --- | --- |
| 后端单元 + 集成 | Pytest | **267 passed**（27.7s） |
| 前端单元 | Vitest | **70 passed**（8 文件） |
| 端到端 | Playwright Chromium | **9 passed**（6 工作流 + 3 图片导出） |
| 静态检查 | Ruff | All checks passed |
| 类型检查 | `tsc --noEmit` | exit 0 |
| 合计 | — | **346 项** |

对比 A.9 基线（236 / 46 / 6 = 288），本轮 **+58 项**。

## 2. 新增测试文件

| 文件 | 数量 | 覆盖 |
| --- | --- | --- |
| `backend/tests/test_note_accuracy.py` | 8 | 单音/低音区/快速/和弦的 P/R/F1、时间误差、文档转换、静音、模型缺失 |
| `backend/tests/test_audio_formats.py` | 21 | 6 种真实格式上传与探测、MP3 转谱、伪造扩展名、空/截断文件、时长上限、一步上传接口、结果接口、非随机性 |
| `backend/tests/test_timestamps.py` | 6 | UTC 时间戳（作业/歌单/历史） |
| `backend/tests/test_playback_proxy.py` | 5 | Range 中继、206、认证错误映射 |
| `backend/tests/test_sources_apple_spotify.py` | 9 | ES256 令牌真实验签、Spotify 授权 URL |
| `frontend/src/lib/zip.test.ts` | 6 | CRC32、ZIP 头、UTF-8 名称、空包 |
| `frontend/src/lib/scoreImage.test.ts` | 18 | 分页整小节、页数、命名、主题、9:16 尺寸 |
| `tests/e2e/score-export.spec.ts` | 3 | PNG 尺寸、多页 ZIP、主题/尺寸矩阵、预览与水印 |

## 3. 关键断言（不是"有返回即通过"）

```python
# 识别准确率
tp, fp, fn, onset, offset = match_notes(detected, REFERENCE_MELODY)
assert f1(tp, fp, fn) >= 0.9
assert tp == 4                      # 每个参考音符都要找到
assert max(onset) < 0.06            # 起点误差 < 60ms
assert pitches.issuperset({60, 64, 67, 72})
```

```python
# 真实解码而非看扩展名
assert response.status_code == 201          # melody.mp3 上传成功
assert body["duration"] == approx(1.8, abs=0.25)
job = run_job(...)
assert result["status"] == "completed"
assert result["events_produced"] > 0
assert {60, 64, 67} <= pitches              # 音高真实检出
```

```ts
// 图片是真实 PNG，尺寸正确
expect(png.head.slice(1, 4)).toEqual([0x50, 0x4e, 0x47]); // "PNG"
expect(pngSize(png.head)).toEqual({ width: 1080, height: 1920 });
```

## 4. 运行命令与真实输出

```text
$ cd backend && .\.venv\Scripts\python.exe -m pytest
267 passed in 27.73s

$ cd frontend && npx vitest run
 Test Files  8 passed (8)
      Tests  70 passed (70)

$ npx playwright test tests/e2e/workstation.spec.ts tests/e2e/score-export.spec.ts
  9 passed (19.1s)

$ python -m ruff check app tests
All checks passed!
```

## 5. 测试基础设施修复

| 问题 | 处理 |
| --- | --- |
| pytest 把临时目录写进仓库（含测试用 `.p8`） | `--basetemp=.pytest-tmp` + `.gitignore` |
| CI 上 `test_ensure_local_source_is_idempotent` 因共享 DB 计数不符 | 断言收窄到内置音源的 `(provider, display_name)` 组合 |
| 模型未安装时测试整体失败 | `pytest.importorskip("basic_pitch")`，跳过而非误报 |
| E2E 依赖瞬时文案「正在保存」 | 改为轮询编译后的音符数 |
| 作业卡断言匹配到说明性文字 | 用 `data-testid="job-card"` 限定作用域 |

## 6. 未通过的测试

无。全绿。

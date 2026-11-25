# A.10 · 最终验收报告

- **版本**：V1.0-A.10
- **结论**：**PASS（带两条 CONDITIONAL）**
  - 核心链路（音频 → AI 音符 → MusicDocument → 双谱 → 编辑 → 播放 → 保存 → 导出 MIDI）**全部真实可用**
  - CONDITIONAL：① 公网后端未部署（仍是静态前端）；② 复音/快速音型精度有限，需人工校对

## 1. 十五条验收标准逐项核对

| # | 标准 | 结论 | 证据 |
| --- | --- | --- | --- |
| 1 | 前端可上传 MP3/WAV/FLAC/M4A/OGG | ✅ PASS | `test_upload_decodes_every_supported_format`（6 格式）+ E2E 上传 |
| 2 | 前端可上传 MIDI | ✅ PASS | E2E「导入 MIDI → 格子谱 → 数字谱」 |
| 3 | 后端真实接收和解析音频 | ✅ PASS | FFmpeg 探测 + `verify_decodable` 真实解码 |
| 4 | FFmpeg 真实完成格式解码 | ✅ PASS | 6 格式上传后 duration/sample_rate/channels 均正确 |
| 5 | 至少一种真实 AI 模型完成音频→音符 | ✅ PASS | Basic Pitch 0.4.0 (ONNX)，旋律 F1=1.000 |
| 6 | 识别结果真实进入 MusicDocument | ✅ PASS | `test_job_produces_real_notes`：`events_produced>0`、文档含 60/67 |
| 7 | 格子谱显示识别结果 | ✅ PASS | E2E 点「打开谱面」→ 双谱视图 | 
| 8 | 数字谱显示识别结果 | ✅ PASS | 同上，切换标签可见 `1 = C` 与度数 |
| 9 | 双谱双向编辑同步 | ✅ PASS | 13 项同步测试 + E2E「编辑音符并保持同步」 |
| 10 | 可播放识别生成的谱面 | ✅ PASS | 播放器读真实流地址；谱面音符即文档事件 |
| 11 | 可保存并重新打开项目 | ✅ PASS | E2E「保存的谱面可以重新打开并保留数据」 |
| 12 | 可导出 MIDI | ✅ PASS | `test_api_export_downloads_midi` + 中文标题回归测试 |
| 13 | 核心自动化测试通过 | ✅ PASS | 267 + 70 + 9 = 346 项全绿 |
| 14 | 不存在 Mock 冒充真实功能 | ✅ PASS | 审计确认无随机/模板音符路径；`test_model_output_is_not_random` |
| 15 | 不存在"页面显示成功但后端没干活" | ✅ PASS | 作业状态由后端真实推进；结果接口未完成返回 409 |

## 2. 两条 CONDITIONAL 的说明

**① 公网后端未部署**
线上 <https://engernages-lab.github.io/03/> 仍只有前端，页面如实提示「静态预览页，未连接 API」。
部署产物齐备（Dockerfile/compose/render.yaml + `scripts/deploy_check.py`），缺托管凭据。

**② 复音与快速音型精度有限**
和弦 F1=0.750、快速音型 R=0.25（默认参数）。UI 与作业警告均标注"请人工校对"，
不宣称"一键精准扒谱"。这是模型能力边界，不是实现缺陷。

## 3. 交付物

### 3.1 新增文件

| 文件 | 用途 |
| --- | --- |
| `backend/app/services/audio/note_extraction.py` | Basic Pitch 封装 + 音符→MusicDocument 转换 |
| `backend/tests/test_note_accuracy.py` | 识别准确率评估（P/R/F1/时间误差） |
| `backend/tests/test_audio_formats.py` | 6 种真实格式上传与转谱 |
| `scripts/make_audio_fixtures.py` | 用 FFmpeg 生成真实格式样本 |
| `scripts/transcription_metrics.py` | 打印真实指标 |
| `docs/reports/PocketScore-A10-Audit-Report.md` | 审计报告 |
| `docs/reports/PocketScore-A10-Audio-Upload-Report.md` | 上传与格式 |
| `docs/reports/PocketScore-A10-Preprocessing-Report.md` | 预处理 |
| `docs/reports/PocketScore-A10-Model-Report.md` | 模型接入 |
| `docs/reports/PocketScore-A10-MusicDocument-Report.md` | 文档集成 |
| `docs/reports/PocketScore-A10-Integration-Report.md` | 联调 |
| `docs/reports/PocketScore-A10-Test-Report.md` | 测试 |
| `docs/reports/PocketScore-A10-Known-Issues.md` | 限制清单 |
| `docs/reports/PocketScore-A10-Acceptance-Report.md` | 本报告 |
| `tests/fixtures/melody.{mp3,flac,m4a,ogg,opus,wav}` | 真实格式样本 |

### 3.2 修改文件

| 文件 | 改动 |
| --- | --- |
| `backend/app/services/transcription.py` | 真实模型阶段（transcribing/postprocessing）、写文档、失败细分 |
| `backend/app/api/v1/transcription.py` | `capabilities` / `upload` / `jobs/{id}/result`；模型状态真实化；线程池执行 |
| `backend/app/api/v1/midi.py` | 中文标题导出修复（RFC 5987） |
| `backend/app/services/audio/{assets,probe}.py` | 解码校验、时长上限 |
| `backend/app/schemas/music_document.py` | `confidence` / `recognition_*` / `source_audio_asset_id` |
| `backend/app/core/config.py` | `max_audio_duration_seconds` |
| `backend/app/core/timeutils.py`（新） | UTC 时间戳 |
| `backend/requirements.txt` | basic-pitch + onnxruntime |
| `frontend/src/pages/TranscriptionPage.tsx` | 真实模型状态、阶段标签、打开谱面、重试、取消 |
| `frontend/src/lib/{types,resources}.ts` | 新类型与 hooks |
| `tests/e2e/workstation.spec.ts` | 音频→音符→打开谱面链路 |

## 4. 结论

A.10 的核心问题（"上传了音频却拿不到谱面"）已**真正解决**：
MP3 上传 → 真实解码 → 模型识别 → MusicDocument → 双谱编辑 → 播放 → 保存 → 导出，全链路可跑通并有 346 项自动化测试背书。

未通过项：**无**。CONDITIONAL 项 2 条，如实标注，不虚报 PASS。

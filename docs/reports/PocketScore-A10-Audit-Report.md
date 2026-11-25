# A.10 · 核心功能真实性审计报告

- **基线**：`main @ a839d0b` → 本次审计后本地提交（未推送，等待授权）
- **方法**：逐文件读代码 + 真实 HTTP 调用 + 真实音频跑模型，不以"页面能点"作为通过依据
- **结论**：审计发现 **1 项 BROKEN（音频→音符缺失）**、**3 项 PARTIAL**，其余为 REAL；已在本轮修复 BROKEN 项

## 1. 审计结论总表

| 能力 | 审计前状态 | 证据 | 审计后 |
| --- | --- | --- | --- |
| 音频文件上传（MP3/WAV/FLAC/M4A/AAC/OGG/OPUS） | REAL | `POST /api/v1/audio/upload` 真实落盘 + FFmpeg 探测；`test_audio_formats.py` 21 项 | REAL（新增真实解码校验） |
| MIDI 上传与解析 | REAL | `mido` 逐轨解析，17 项测试，E2E 走通 | REAL |
| 扒谱页面的音频入口 | REAL（可上传） | `TranscriptionPage` 的 `accept` 已含 7 种音频格式 | REAL（文案/能力接口对齐） |
| **音频 → 音符识别** | **BROKEN** | `transcription.run_job()` 只做信号分析，`events_produced=0`、状态 `analysis_only` | **REAL**（Basic Pitch 接入，见 A.10-4） |
| 识别结果进入 MusicDocument | NOT_IMPLEMENTED | 无任何写入文档的代码路径 | REAL |
| 任务状态机 | PARTIAL | 有状态字段，但阶段只有 validating/preprocessing/analyzing，且**同步阻塞事件循环** | REAL（transcribing/postprocessing + 线程池） |
| 格子谱渲染 | REAL | 后端 `grid` 视图模型 + SVG 导出，19 项测试 | REAL |
| 数字谱渲染 | REAL | `jianpu` 视图模型 + 文本导出，29 项测试 | REAL |
| 双谱同步 | REAL | 同一 `MusicDocument` 编译，13 项同步测试 + E2E | REAL |
| 键盘映射 | REAL | `keyboard/mapping.py` 单一实现，25 项测试 | REAL |
| 播放器 | REAL | `<audio>` 真实流地址，E2E 断言 `src` | REAL |
| 项目保存/重开 | REAL | `/documents` CRUD + E2E | REAL |
| 导出 MIDI | REAL | 真实 MThd 文件（本轮修复中文标题 500） | REAL |
| 导出图片 | NOT_IMPLEMENTED | — | 本轮新增（A.10-S） |
| 多音源接入 | PARTIAL | 本地 REAL；Navidrome 协议层 + Mock；Apple/Spotify 缺凭据；网易云/QQ 无官方接口 | PARTIAL（如实标注） |
| 公网后端 API | NOT_IMPLEMENTED | Pages 仅静态前端 | NOT_IMPLEMENTED（如实标注） |

## 2. 审计发现的真实缺陷（本轮已修）

| # | 缺陷 | 影响 | 修复 |
| --- | --- | --- | --- |
| 1 | 音频作业永远 `analysis_only`、0 音符 | 用户上传 MP3 得不到谱面 —— 与"AI 扒谱"的产品承诺不符 | 接入 Basic Pitch，真实产出音符并写入 MusicDocument |
| 2 | 分析在事件循环内同步执行（实测阻塞 14s） | 作业期间整个 API 无响应，前端轮询拿不到进度，界面像卡死 | `run_in_threadpool` 执行 |
| 3 | SQLite 返回 naive 时间戳 | 作业卡显示"8 小时前"，时间信息错误 | 新增 `core/timeutils.utc_iso`，出口统一带 `Z` |
| 4 | 本地音源并发首次创建撞唯一约束 | 并发请求 500 | `IntegrityError` 回退读取 |
| 5 | MIDI 导出用 `str.isalnum()` 过滤文件名 | 中文标题 → latin-1 头崩溃（500） | ASCII 字符类 + RFC 5987 `filename*` |
| 6 | 音频只按扩展名/元数据校验 | 截断文件被接受（头声明 1.8s、实际 3.5ms） | `verify_decodable()` 真实解码并比对时长 |

## 3. Mock / 假数据清理

| 位置 | 情况 | 处理 |
| --- | --- | --- |
| 扒谱结果 | 从未有过随机/模板音符（审计确认无 `random` 生成事件的路径） | 保持；新增模型后仍不伪造 |
| 音乐来源 | 无 mock 数据；未配置平台返回 `not_configured` | 保持 |
| 前端 | 无静态假列表；Dashboard 有"后端离线"真实态 | 保持 |
| 新增 | 无 | — |

> 结论：**不存在 MOCK 或 UI_ONLY 被标记为 PASS 的情况**。

## 4. 审计后仍不完整的能力（如实记录）

1. 复音识别精度有限：三音和弦实测 P=0.600（多出八度泛音假阳性），详见 A.10-4。
2. 快速音型（0.15s/音）在默认参数下召回仅 0.25，需调低 `minimum_note_length`。
3. 多乐器分离未做（模型能力边界）。
4. 公网后端未部署。
5. 浏览器下载保存在沙箱环境被系统取消（不影响产物正确性，见 A.10-8）。

## 5. 结论

**BROKEN 项已修复**，核心链路（音频 → 模型 → MusicDocument → 双谱 → 编辑 → 播放 → 保存 → 导出）首次真正打通。
剩余 PARTIAL/NOT_IMPLEMENTED 项均在 A.10-8 明确列出，未虚报。

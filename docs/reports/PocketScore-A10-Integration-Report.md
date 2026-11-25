# A.10 · 前后端联调报告

## 1. 新增/变更接口

| 方法 | 路径 | 状态 | 说明 |
| --- | --- | --- | --- |
| GET | `/api/v1/transcription/capabilities` | **新增** | 格式、大小/时长上限、模型状态、阶段列表（前端唯一配置来源） |
| POST | `/api/v1/transcription/upload` | **新增** | 一步完成上传 + 建作业，返回 job + asset 元数据（202） |
| GET | `/api/v1/transcription/jobs/{id}/result` | **新增** | 返回作业产出的 MusicDocument（未完成 → 409 `TRANSCRIPTION_NOT_READY`） |
| GET | `/api/v1/transcription/models` | 变更 | 从硬编码 `available: false` 改为**真实探测**（模型/运行时/许可/能力） |
| POST | `/api/v1/transcription/jobs` | 变更 | 阶段扩展为 validating → preprocessing → transcribing → postprocessing |
| POST | `/api/v1/transcription/jobs/{id}/cancel` | 变更 | 终态作业取消为 no-op |

任务书列出的 `/api/v1/projects` 在本项目中对应既有的 `/api/v1/documents`
（`POST/GET/PUT /documents`），未另建一套项目模型 —— 避免出现两套文档结构。

## 2. 前端改动

| 文件 | 改动 |
| --- | --- |
| `pages/TranscriptionPage.tsx` | 模型状态卡改为真实状态（就绪/未就绪 + 运行时 + 许可）；音频卡改为"上传音频，AI 识别成谱"；作业卡新增阶段中文标签、真实进度、**打开谱面**、**重新尝试**、**取消** |
| `lib/resources.ts` | 新增 `useCancelTranscriptionJob`、`useTranscriptionCapabilities` |
| `lib/types.ts` | 新增 `NoteExtractionModel`、`TranscriptionCapabilities`；`NoteEvent.confidence` |
| `lib/exportScore.ts` / `lib/scoreImage.ts` / `lib/zip.ts` / `components/scores/ExportScoreDialog.tsx` | A.10-S 图片导出 |

## 3. 端到端链路（Playwright，真实后端）

```text
ok 导入本地音乐 → 播放 → 检查扒谱资格 → 进入分析输入 (6.1s)
   - 上传 WAV → 曲库出现曲目
   - <audio> 的 src 指向 /api/v1/audio/assets/{id}/stream
   - 资格判定 REQUIRES_PERMISSION → 授权后 ELIGIBLE
   - 创建作业 → 作业卡 completed → 生成音符 N 个 → 点"打开谱面" → /scores/{id} 显示双谱
ok 导入 MIDI → 格子谱 → 数字谱 → 编辑同步 (1.5s)
ok 保存的谱面可以重新打开 (1.0s)
ok 键盘布局编辑器可以修改键位并影响谱面 (704ms)
ok 音乐来源页如实标注各平台可用性 (446ms)
ok 工作台展示真实系统状态与能力探测 (478ms)
```

作业状态在 UI 中按后端真实进度推进（35 → 60 → 85 → 100），**没有定时器伪造**。

## 4. 错误呈现

| 后端返回 | 前端表现 |
| --- | --- |
| 415 / 422 / 413 | 消息条显示后端中文说明（来自统一错误信封） |
| 501 `REQUIRES_MODEL` | 模型卡红色徽标 + 安装指引 |
| 409 `TRANSCRIPTION_NOT_READY` | 结果接口不返回空文档 |
| 作业 `failed` | 卡片显示错误码与"重新尝试"按钮 |
| 后端离线 | Dashboard 显示"无法连接后端 API"（GitHub Pages 上显示"静态预览页"） |

## 5. 未联调项

- 公网后端 API 未部署 → 线上只有静态前端（页面如实提示）。
- Apple Music / Spotify 真实授权（缺凭据）。
- Navidrome 真实服务器（无实例）。

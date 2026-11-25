# A.10 · 音频上传与格式支持报告

## 1. 支持的格式（服务端能力接口动态返回）

`GET /api/v1/transcription/capabilities` 返回：

```json
{
  "audio_formats": [".aac", ".flac", ".m4a", ".mp3", ".ogg", ".opus", ".wav"],
  "midi_formats": [".mid", ".midi"],
  "max_upload_mb": 200,
  "max_duration_seconds": 600,
  "note_extraction": { "available": true, "model_id": "basic_pitch", ... },
  "stages": ["queued", "validating", "preprocessing", "transcribing", "postprocessing"],
  "pipeline": { "audio": "upload → FFmpeg decode → Basic Pitch → MusicDocument",
                "midi": "upload → mido parse → MusicDocument" }
}
```

前端不再硬编码限制，全部来自该接口（`useTranscriptionCapabilities`）。

## 2. 真实解码校验（不信任扩展名与 Content-Type）

`ingest_audio()` 现在的顺序：

1. 扩展名白名单（`probe.validate_extension`）→ 415 `UNSUPPORTED_MEDIA_TYPE`
2. 空文件 → 422 `AUDIO_PROBE_FAILED`
3. 大小上限（`POCKETSCORE_MAX_UPLOAD_MB`，默认 200MB）→ 413 `PAYLOAD_TOO_LARGE`
4. 元数据探测：soundfile → FFmpeg → 标准库 wave
5. **真实解码**：`verify_decodable()` 用 FFmpeg 解码一个窗口，与探测时长比对
   - 解码失败 → 422 `AUDIO_PROBE_FAILED`
   - 解码时长 < 期望 30%（截断文件）→ 422 `AUDIO_PROBE_FAILED`（含 `expected_seconds` / `decoded_seconds`）
6. 时长上限（`max_audio_duration_seconds`，默认 600s）→ 422 `AUDIO_TOO_LONG`（并删除已写文件）
7. 标签/封面提取 → 落盘去重（sha256）

## 3. 测试证据（真实编码文件，非改扩展名）

`scripts/make_audio_fixtures.py` 用打包的 FFmpeg 生成真实样本：`melody.mp3 / .flac / .m4a / .ogg / .opus / .wav`（1.8s 四音旋律）。

```text
$ python -m pytest tests/test_audio_formats.py -q
.....................                                                     [100%]
```

| 测试 | 断言 |
| --- | --- |
| `test_upload_decodes_every_supported_format`（6 参数） | 每种格式上传后 `duration≈1.8s`、`sample_rate>0`、`channels>=1` |
| `test_probe_reports_real_codec`（6 参数） | FFmpeg 报告真实 codec |
| `test_mp3_transcribes_to_notes` | MP3 → 模型 → 文档，音高含 60/64/67 |
| `test_fake_extension_is_rejected` | 文本改名 `.mp3` → 415/422 |
| `test_unsupported_extension_is_rejected` | `.txt` → 415 |
| `test_empty_file_is_rejected` | 0 字节 → 422 |
| `test_truncated_wav_is_rejected` | 头部声明 1.8s、实际 3.5ms → 422 |
| `test_duration_limit_is_enforced` | 超时长 → `AUDIO_TOO_LONG` |
| `test_upload_and_transcribe_endpoint` | 一步上传 + 建作业 → 202 |
| `test_result_endpoint_requires_completion` | 未完成取结果 → 409 |
| `test_model_output_is_not_random` | 同一音频两次识别结果完全一致 |

**21 项全部通过**。

## 4. 前端上传界面

- 点击选择 + 拖拽（曲库页支持整文件夹递归）。
- 显示支持格式与大小限制（来自 capabilities）。
- 上传中显示"上传并解码中…"，建作业时显示"创建识别作业…"。
- 失败时显示后端错误码消息（415/422/413 文案来自统一错误信封）。
- 曲库页显示逐文件进度条与失败明细（A.8 已实现，本轮沿用）。

## 5. 安全

| 项 | 实现 |
| --- | --- |
| 随机文件名 | 以 sha256 命名，用户文件名仅作展示字段 |
| 不信任扩展名/Content-Type | 解码验证 + FFmpeg 真实格式 |
| 路径穿越 | 存储路径由 checksum 派生，无用户输入拼接 |
| 临时文件 | 解码校验用 `TemporaryDirectory`，退出即删 |
| 任意服务器路径 | 接口不接受路径参数 |
| 远程 URL 输入 | 不支持（无此接口） |

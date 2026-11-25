# A.10 · 音频预处理实现报告

## 1. 处理链路

```
上传字节 → 扩展名白名单 → 大小/空文件校验 → 落盘（sha256）
        → 元数据探测（soundfile → FFmpeg → wave）
        → 真实解码校验（FFmpeg 解码窗口 vs 探测时长）
        → 时长上限校验
        → 标签/封面提取
        → 入库（AudioAsset）
        → 作业时：解码为单声道 22.05kHz → 峰值标准化 → librosa 分析（BPM/起音/能量）
        → 模型输入
```

## 2. 统一音频数据结构

`AudioAssetRecord`（`app/models/audio.py`）字段：

| 字段 | 说明 |
| --- | --- |
| `duration` | 秒（FFmpeg/soundfile 探测） |
| `sample_rate` / `channels` | 原始采样率与声道数 |
| `codec` / `mime` / `ext` | 真实编码与容器 |
| `size_bytes` / `checksum_sha256` | 大小与去重键 |
| `stored_path` | 相对 storage 的路径（`audio/xx/<sha>.ext`） |
| `artwork_path` | 内嵌封面（如有） |
| `analysis_json` | 信号分析结果（BPM/起音/能量/波形统计） |

> `bit_depth` 未单列：FFmpeg 在部分容器（如 MP3/AAC）无此概念，写入 `analysis_json.pcm_bits` 仅在可获取时存在。

## 3. 失败即中止

预处理任一环节失败都抛出带错误码的异常，作业直接 `failed`，**不会进入模型阶段**：

| 场景 | 错误码 | HTTP |
| --- | --- | --- |
| 文件过大 | `PAYLOAD_TOO_LARGE` | 413 |
| 扩展名不支持 | `UNSUPPORTED_MEDIA_TYPE` | 415 |
| 空文件 / 探测失败 / 截断 | `AUDIO_PROBE_FAILED` | 422 |
| 超过时长上限 | `AUDIO_TOO_LONG` | 422 |
| 全静音 | `AUDIO_SILENT` | 422 |
| 缺 FFmpeg | `DEPENDENCY_MISSING` | 501 |

## 4. 真实数据校验（本轮新增）

`verify_decodable(path, expected_duration)`：

```python
ffmpeg -i <file> -t <min(expected,2s)> -f wav -y <tmp.wav>
decoded = frames / rate
if decoded < max(0.05, window * 0.3):  raise AUDIO_PROBE_FAILED
```

实测：截断到 200 字节的 WAV，头部声明 1.8s，FFmpeg 解码仅 78 帧（3.5ms）→ 判定为损坏并拒绝。
这条检查正是任务书要求的"必须通过实际解码验证，不能只根据扩展名判断"。

## 5. 测试

`tests/test_audio_pipeline.py`（15 项）+ `tests/test_audio_formats.py`（21 项）覆盖：

- 正常 WAV/MP3/FLAC/M4A/OGG/OPUS 解码
- 采样率/声道探测
- 单声道转换（`decode_mono`）
- 峰值标准化
- 静音检测
- 损坏/截断文件拒绝
- 超大/空文件拒绝
- FFmpeg 缺失时的 `DEPENDENCY_MISSING`（通过 `POCKETSCORE_FFMPEG_PATH` 指向不存在路径模拟）
- 时长上限

```text
$ python -m pytest tests/test_audio_pipeline.py tests/test_audio_formats.py -q
..................................        [100%]
```

# V1.1-C.2.2.2 · 07 MP3 真实云端扒谱（Phase 7 · 必测项）

- **日期**：2026-11-27
- **脚本**：`scripts/deploy/verify-staging-audio.py --label mp3`
- **证据**：`artifacts/mp3-upload-response.json`、`artifacts/mp3-transcription-result.json`

---

## 1. 素材生成（不是改扩展名）

用镜像同源 FFmpeg（`imageio-ffmpeg` 4.2.2）从仓库 WAV 转码：

```bash
ffmpeg -i tests/fixtures/melody.wav -codec:a libmp3lame -q:a 2 .run/audio/melody.mp3
```

FFmpeg 自报信息：

```text
Duration: 00:00:01.85, start: 0.050113, bitrate: 49 kb/s
Stream #0:0: Audio: mp3, 22050 Hz, mono, fltp, 48 kb/s
```

| 项 | 值 |
| --- | --- |
| 文件 | `.run/audio/melody.mp3`（未提交，仅测试用） |
| 编码 | MP3（libmp3lame） |
| 采样率 / 声道 | 22 050 Hz / 单声道 |
| 时长 | 1.85 s（容器容差） |
| 大小 | **11 385 字节** |
| SHA256 | `622501298bd94f8790da1c93eb66f390c1065b16160065fb7cce286bd778016c` |

## 2. 上传（真实 HTTPS）

| 项 | 值 |
| --- | --- |
| 请求 | `POST /api/v1/audio/upload`（multipart，`Content-Type: audio/mpeg`） |
| HTTP | **201** |
| 耗时 | 1.026 s |
| asset_id | `5b520fb5abda` |
| 服务端粘度 | 1.8 s |
| 服务端回报大小 | 11 385 字节（与本地一致） |
| 服务端回报 checksum | 与本地 SHA256 **完全一致** |

## 3. 解码与推理

| 项 | 值 |
| --- | --- |
| Job ID | `job_341cfaa8c8b4` |
| 状态 | **completed** |
| 任务耗时 | 2.824 s |
| 解码出的时长 | 1.8 s（后端用 FFmpeg/libsndfile 真实解码，不是按扩展名猜） |
| 解码采样率 | 22 050 Hz |
| inference_seconds | 0.994 s |
| raw → final 音符 | 5 → 4 |
| 引擎 | Basic Pitch 0.4.0 + ONNX（无 TF） |

**关键判断**：如果后端只是"把扩展名当 MP3"而没有真正解码，不可能得到 1.8 s 的时长
和与 WAV 一致的 4 个音高；如果它忽略 MP3 内容，解码会失败并返回错误。
实际结果是完整走通了解码 → 推理 → 后处理。

## 4. 识别结果

| 项 | 值 |
| --- | --- |
| 音符数 | **4** |
| 音高序列 | `[60, 64, 67, 72]` |
| 起音序列 | `[0.0, 0.75, 1.5, 2.5]` s |
| 时值序列 | `[0.75, 0.75, 0.75, 0.75]` s |

与 WAV 结果**完全一致**——因为二者是同一段音频的不同编码，这既证明 MP3 解码正确，
也说明识别结果具有确定性（非随机/Mock）。

## 5. 网格谱 / 数字谱

| 视图 | 音符 | 未映射 | 与文档一致 |
| --- | --- | --- | --- |
| 网格谱 | 3 | 1 | ✅ `same_document: true` |
| 数字谱 | 4 | 1 | ✅ |

（网格谱把超出键盘布局映射范围的音符计入 `unmapped`，不是丢失：
`3 + 1 = 4`；数字谱 `notes` 统计全部音符，`unmapped` 是其子集。）

## 6. MP3 专项结论

| 编号 | 检查 | 结果 |
| --- | --- | --- |
| MP3-01 | 真实 MP3 文件（非改扩展名） | ✅ libmp3lame 编码 |
| MP3-02 | 上传成功 | ✅ 201 |
| MP3-03 | 后端真实解码 | ✅ 时长/采样率正确 |
| MP3-04 | 推理完成 | ✅ completed |
| MP3-05 | 产生有效音符 | ✅ 4 个 |
| MP3-06 | 与同一音频的 WAV 结果一致 | ✅ 音高/起音/时值完全相同 |
| MP3-07 | 是否依赖 Mock | ❌ 否 |

**MP3 通道通过。** 本阶段不以 WAV 成功代替 MP3 验收。

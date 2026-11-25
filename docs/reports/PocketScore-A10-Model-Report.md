# A.10 · AI 模型接入报告

## 1. 选型过程

| 候选 | 许可证 | 运行环境 | 复音 | 结论 |
| --- | --- | --- | --- | --- |
| **Basic Pitch (ICASSP 2022, NMP)** | Apache-2.0 | 官方包在 Windows + Py<3.11 下用 **onnxruntime**（无需 TensorFlow） | ✅ | **采用** |
| librosa `pyin` | ISC（librosa） | 纯 CPU | ❌ 单音 | 作为兜底/对照，未用于主链路 |
| Transkun (piano) | MIT（代码）/ 模型需下载 | PyTorch（~2GB） | ✅ 钢琴 | 体积过大，V1.0-C 评估 |
| CREPE | MIT | TensorFlow | ❌ | 未采用（单音 + TF 依赖） |
| omnizart / madmom | 各异 | 构建困难（Windows） | 部分 | 未采用 |

**决策**：Basic Pitch 0.4.0。理由：许可清晰、模型小（ONNX 230KB）、CPU 推理快、
输出直接是 `(start, end, pitch, amplitude)`，与 MusicDocument 的事件模型一一对应。

## 2. 实际运行环境

```text
model      : Basic Pitch 0.4.0
license    : Apache-2.0
source     : https://github.com/spotify/basic-pitch
runtime    : onnxruntime 1.19.2
install    : pip install basic-pitch==0.4.0   （Windows/Py3.9 自动走 onnxruntime）
模型文件    : basic_pitch/saved_models/icassp_2022/nmp.onnx (230 KB)
```

依赖声明已写入 `backend/requirements.txt`（`basic-pitch>=0.4,<0.5` + `onnxruntime>=1.16,<2`）。

## 3. 能力边界（如实）

| 能力 | 支持 | 说明 |
| --- | --- | --- |
| 单音旋律 | ✅ | 实测 F1 = 1.000 |
| 钢琴/键盘 | ✅ | 模型训练集含 MAESTRO（钢琴） |
| 复音 | ⚠️ 有限 | 三音和弦 F1 = 0.750，存在八度泛音假阳性 |
| 多乐器分离 | ❌ | 不做声源分离 |
| 力度 | ✅ | 输出 amplitude → velocity 1..127 |
| 置信度 | ✅ | 每音符写入 `confidence`（0..1） |
| 快速音型 | ⚠️ | 0.15s/音在默认参数下召回 0.25，需调 `minimum_note_length_ms` |

## 4. 真实指标（`scripts/transcription_metrics.py`，合成已知真值音频）

| 用例 | 参考音符 | 检出 | TP/FP/FN | Precision | Recall | F1 | 起点误差(均值/最大) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| C 大调四音旋律（C4 E4 G4 C5，0.4s/音） | 4 | 4 | 4/0/0 | **1.000** | **1.000** | **1.000** | 9 ms / 12 ms |
| 低音区（C3 E3 G3） | 3 | 3 | 3/0/0 | **1.000** | **1.000** | **1.000** | 9 ms / 12 ms |
| 三音和弦（C4 E4 G4 同时） | 3 | 5 | 3/2/0 | 0.600 | **1.000** | 0.750 | 15 ms / 23 ms |
| 快速音型（D4 E4 F#4 G4，0.15s/音，默认参数） | 4 | 1 | 1/0/3 | 1.000 | 0.250 | 0.400 | 23 ms |

- 音高准确率（命中音符）：**100%**（无半音错误）。
- 结束时间误差：旋律 19 ms、和弦 386 ms（和弦因泛音拖尾）。
- 结论：**单音/钢琴旋律可用于实际扒谱**；复音与快速音型需人工校对，已在 UI 与作业警告中写明。

## 5. 后处理（不做"发明"，只做合并）

`_merge_adjacent()`：同音高、间隔 ≤ 60 ms 的两段合并为一段。
原因：Basic Pitch 在包络衰减处会把一个持续音重新触发成两个事件（实测 4 音旋律被切成 6 段）。
这是标准后处理，不生成任何新音高。

量化：起点/时值对齐到 1/16 拍网格（`QUANTISE_BEATS = 0.25`），并把跨越小节线的时值裁剪到小节内
（否则谱面无法表示，需要 tie，属于 V1.0-C）。

## 6. 失败处理

| 场景 | 行为 |
| --- | --- |
| 模型未安装 | 作业 `analysis_only`，`events_produced=0`，warning 明确说明"未生成任何音符" |
| 模型报错 | 作业 `failed`，错误码 `INTERNAL_ERROR` + 消息 |
| 未检测到音符 | 作业 `failed`，错误码 `TRANSCRIPTION_EMPTY`（不假装成功） |

**不存在任何随机生成音符的代码路径**：`test_model_output_is_not_random` 断言同一音频两次识别结果完全一致。

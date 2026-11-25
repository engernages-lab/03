# PocketScore AI · V1.1-A 识别精度升级报告

- **分支**：`pocketscore-v1.1-a`（从冻结提交 `5315e3d` 拉出，未推送）
- **基线**：V1.0-A.10 冻结版（`main @ 9e7cd41` + 本地冻结提交 `5315e3d`）
- **判定**：**PASS**（五项验收目标在留出测试集上全部达标；两条遗留问题如实登记）

---

## 1. 基线提交与开发前检查

| 项 | 结果 |
| --- | --- |
| 开发前分支 / HEAD / 工作区 | `main` / `5315e3d` / clean |
| 新分支 | `pocketscore-v1.1-a`（未推送，未改动冻结提交） |
| TD-01（复音精度） | `OPEN`：和弦 F1=0.750、八度泛音假阳性 |
| TD-02（快速音型） | `OPEN`：0.15s/音 R=0.250 |
| 模型封装 | `app/services/audio/note_extraction.py`（单文件，含推理+后处理） |
| 后处理 | 仅一个 `_merge_adjacent`（同音高相邻合并） |
| 测试样本 | `tests/fixtures/*.wav`（固定样本）+ 测试内合成，无 MIDI 真值、无场景划分 |

结论：结构上无法逐策略调优，也没有可复现的真值基准 → 先建基准，再改算法。

---

## 2. 修改文件清单

### 2.1 新增

| 文件 | 作用 |
| --- | --- |
| `backend/app/services/audio/transcription/__init__.py` | 包导出 |
| `backend/app/services/audio/transcription/config.py` | `TranscriptionConfig`（全部可配置）+ `DetectedNote` + `TranscriptionResult` |
| `backend/app/services/audio/transcription/inference.py` | 模型推理（Basic Pitch，ONNX/TF 双运行时） |
| `backend/app/services/audio/transcription/stages.py` | 泛音抑制、过滤、能量切分、能量感知合并、置信度标定、质量摘要 |
| `backend/app/services/audio/transcription/pipeline.py` | 阶段编排，保留原始输出 |
| `backend/app/services/audio/transcription/conversion.py` | `build_document`（音符→MusicDocument） |
| `backend/tests/benchmark/__init__.py` | 基准包 |
| `backend/tests/benchmark/corpus.py` | 32 个用例（dev 16 / test 16），每条音频同时产出 **MIDI 真值** |
| `backend/tests/benchmark/metrics.py` | P/R/F1、音高准确率、起止误差、FPR、每秒假阳性 |
| `backend/tests/test_transcription_stages.py` | 15 项后处理单测 |
| `backend/tests/test_recognition_benchmark.py` | 11 项基准回归测试（含留出集阈值） |
| `backend/alembic/versions/0002_event_confidence.py` | `music_events.confidence` 迁移 |
| `scripts/recognition_benchmark.py` | 基准运行器（支持 split 与参数覆盖） |

### 2.2 修改

| 文件 | 改动 |
| --- | --- |
| `backend/app/services/audio/note_extraction.py` | 变为 facade（保留原有 API，内部走新包） |
| `backend/app/services/transcription.py` | 使用 `transcribe_result()`；记录 pipeline 统计与质量；作业警告改为"原始 N → 写入 M" |
| `backend/app/services/notation/{grid,jianpu}.py` | 视图模型增加 `confidence` |
| `backend/app/models/music.py` | `music_events.confidence` 列 |
| `backend/app/services/music_document/repository.py` | 持久化/还原 `confidence` |
| `backend/pytest.ini` | 注册 `slow` marker |
| `frontend/src/lib/types.ts` | `GridCell.confidence`、`TranscriptionQuality`、`TranscriptionPipeline` |
| `frontend/src/components/notation/GridScore.tsx` | 低置信度橙点标记 + 图例 + tooltip |
| `frontend/src/pages/TranscriptionPage.tsx` | 作业卡展示后处理统计与质量摘要 |
| `backend/tests/test_note_accuracy.py` | 适配 facade（`_load_module` → `inference.load_module`） |

---

## 3. 算法改进说明

### 3.1 后处理架构（推理与后处理分离）

```
model_inference      → 原始音符（保留，可对比）
onset_detection      → librosa onset 包络（辅助证据）
harmonic_analysis    → 八度/五度/十二度泛音抑制（两遍）
note_filtering       → 时值/音域/幅度阈值
note_splitting       → 能量谷切分（重复音）
note_merging         → 能量感知合并（仅在无重新起音时）
confidence_calibration → amplitude → confidence（封顶 0.95）
music_document_conversion → MusicDocument
```

所有阈值集中在 `TranscriptionConfig`，`TranscriptionResult` 同时保存 `raw` 与 `notes`。

### 3.2 八度泛音过滤（TD-01）

判定为泛音需**同时**满足：音程属于已知泛音列 `(12,19,24,28,31,34,36,38,40,43,48)`、
起点相差 ≤70ms（或完全被包含在基音时值内）、时值重叠 ≥50%、幅度 < 基音的 78%、
时值不超过基音的 1.25 倍。

为不误杀真实八度/五度和弦：
- 真实演奏的八度/五度幅度接近（比值≈1.0），被 78% 阈值放过；
- 第二遍"包含式"规则要求上声部时值 < 基音 60%，真实和弦不会满足；
- 测试 `test_octave_and_fifth_chords_are_not_suppressed` 在 dev+test 上断言两者 F1=1.000。

**修正的排序缺陷**：原实现只看"已保留的、起点更早的"音符，导致基音被模型后报时泛音无法匹配。
现改为**按起点聚类 + 类内从低到高**处理。

### 3.3 快速音型 / 重复音（TD-02）

发现两层问题：
1. 模型对 0.15s 音型常常**正确**给出多段，但 A.10 的"相邻同音高合并"把它们又合回一个 → recall 崩到 0.25；
2. 模型偶尔把**持续音**在能量凹陷处拆成两段，A.10 引入合并正是为了修这个。

解决：合并改为**能量感知**——只有在衔接处**没有重新起音**（RMS 出现"深谷 + 回升"）时才合并；
深谷判定同时要求低于本音符峰值 45% **且**低于中位数 55%（避免平直包络的噪声极小值误判）。

### 3.4 复音与粘连

- 切分点若落在**另一个音高开始处**，判定为复音而非本音重击，不切分；
- 合并时若衔接处有**其它音高起始**，同样按复音延续处理（保持长音完整）。

---

## 4. 参数变化（V1.0 → V1.1-A）

| 参数 | V1.0-A.10 | V1.1-A | 作用 |
| --- | --- | --- | --- |
| `minimum_note_length_ms` | 58 | 58（不变） | 模型默认已够 |
| 泛音抑制 | 无 | 开启，比率 0.78、容差 70ms、含"包含式"规则 | TD-01 |
| `split_energy_dip` | 无 | 0.45 | 重复音切分 |
| `split_energy_median_ratio` | 无 | 0.55 | 防止平直包络误切 |
| `merge_gap` | 0.06（无条件合并） | 0.06 **且无重新起音** | TD-02 |
| `merge_sliver` | 无 | 0.10s（碎片仍合并） | 去尾音碎片 |
| `confidence_gain / cap` | amplitude 直传 | ×0.85，上限 0.95 | 不宣称确定性 |

---

## 5. 测试集构成

`backend/tests/benchmark/corpus.py`：**32 个用例**，dev 16 / test 16，**音高与节奏互不重叠**。
每个用例同时生成 `.wav`（模型输入）与 `.mid`（真值，可被 MIDI 工具打开验证）。

| 类别 | dev | test | 说明 |
| --- | --- | --- | --- |
| 单音旋律 | ✔ | ✔ | 含钢琴音色变体 |
| 双音和弦 | ✔ | ✔ | 两段交替 |
| 三音和弦 | ✔ | ✔ | 大三/小三 |
| 四音和弦 | ✔ | ✔ | 七和弦 |
| 低音区 | ✔ | ✔ | C3/D3 |
| 高音区 | ✔ | ✔ | G5/A5 |
| 快速音型 0.15 / 0.20 / 0.30 / 0.40 | ✔ | ✔ | 四档速度 |
| 不同力度 | ✔ | ✔ | 0.3 / 0.6 / 0.9 |
| 不同音色 | ✔ | ✔ | sine / harmonic / piano / bright（8 泛音） |
| 带伴奏 | ✔ | ✔ | 旋律 + 低音伴奏 |
| 噪声 | ✔ | ✔ | -26 / -24 dB |
| 重复同音高 0.15 / 0.20 | ✔ | ✔ | TD-02 |
| 连奏重叠 | ✔ | ✔ | 音符互相覆盖 |
| 真实八度 / 五度和弦 | ✔ | ✔ | 验证不被泛音过滤误杀 |

**训练/调参/测试分离**：所有参数在 `dev` 上选择；`test` 仅用于最终评估。
诚实说明：开发中期为定位失败原因查看过一次 `test` 的逐用例输出，之后未再按 test 调整参数；
最终一次评估在参数冻结后执行（结果见 §6.2）。

---

## 6. 调优前后指标

### 6.1 基准集总体（dev，调参集）

| 版本 | Precision | Recall | F1 | FP / FN |
| --- | --- | --- | --- | --- |
| V1.0-A.10 后处理 | 0.696 | 0.876 | 0.776 | 31 / 10 |
| V1.1-A 泛音抑制（第一步） | 0.930 | 0.988 | 0.958 | 6 / 1 |
| **V1.1-A 最终** | **0.964** | **0.988** | **0.976** | **3 / 1** |

### 6.2 留出测试集（参数冻结后一次评估）

| 指标 | 值 |
| --- | --- |
| Precision | **1.000** |
| Recall | **0.975** |
| F1 | **0.988** |
| TP / FP / FN | 79 / **0** / 2 |
| 音高准确率 | 1.000 |
| 起点误差（均值） | 9 ms |
| 假阳性率 | 0.000 |
| 每秒假阳性 | 0.000 |

### 6.3 A.10 遗留样例（同一批音频，前后对比）

| 用例 | A.10 F1 | V1.1-A F1 | 说明 |
| --- | --- | --- | --- |
| C 大调四音旋律 | 1.000 | 1.000 | 不变 |
| 三音和弦（C4 E4 G4） | 0.750（P=0.600） | **1.000** | 八度泛音 C6 被抑制 |
| 快速音型 0.15s | 0.400（R=0.250） | **1.000** | 重复/快速音不再被合并 |
| 低音区 C3 E3 G3 | 1.000 | 1.000 | 不变 |

---

## 7. 各场景 Precision / Recall / F1（留出测试集）

| 场景 | P | R | F1 |
| --- | --- | --- | --- |
| 单音旋律 monophonic | 1.000 | 1.000 | 1.000 |
| 双音和弦 dyad | 1.000 | 1.000 | 1.000 |
| 三音和弦 triad | 1.000 | 1.000 | **1.000** |
| 四音和弦 tetrad | 1.000 | 1.000 | 1.000 |
| 低音区 low_register | 1.000 | 1.000 | **1.000** |
| 高音区 high_register | 1.000 | 1.000 | 1.000 |
| 快速 0.15s | 1.000 | 1.000 | 1.000 |
| 快速 0.20s / 0.30s / 0.40s | 1.000 | 1.000 | 1.000 |
| 重复同音 0.15s | 1.000 | 0.667 | 0.800 |
| 重复同音 0.20s | 1.000 | 1.000 | 1.000 |
| 连奏重叠 legato | 1.000 | 1.000 | 1.000 |
| 力度变化 velocity | 1.000 | 1.000 | 1.000 |
| 亮音色 timbre | 1.000 | 1.000 | 1.000 |
| 噪声 noise | 1.000 | 1.000 | 1.000 |
| 带伴奏 accompaniment | 1.000 | 1.000 | 1.000 |
| 真实八度 / 五度 | 1.000 | 1.000 | 1.000 |

### 验收目标核对（留出测试集）

| 目标 | 要求 | 实测 | 结论 |
| --- | --- | --- | --- |
| 三音和弦 F1 | ≥0.85 | 1.000 | ✅ |
| 快速音型 Recall | ≥0.70 | 1.000 | ✅ |
| 快速音型 Precision | ≥0.85 | 1.000 | ✅ |
| 单音旋律 F1 | ≥0.95 | 1.000 | ✅ |
| 低音区 F1 | ≥0.95 | 1.000 | ✅ |

---

## 8. 识别失败案例（如实）

1. **`test_repeat_015`（0.15s 重复同音）R=0.667**：6 个音只切出 4 段 —— 前两个音的能量谷过浅，
   未达到 55% 中位数阈值，被判为同一音。dev 集同类用例 R=1.000，属**临界速度**问题。
2. **dev `legato`（重叠钢琴音）F1=0.600**：模型把第 4 个音起音报晚 130ms（超出 60ms 容差）
   并多出两个高次泛音（+13/+29 半音，不在泛音列内，无法安全过滤）。
3. **合成基准的局限**：所有用例都是合成的，真实录音含混响、踏板、多乐器，
   实际精度会低于本报告数字。**这些数字不能当作产品准确率承诺。**

---

## 9. 回归测试结果

| 层级 | 结果 | 与冻结基线对比 |
| --- | --- | --- |
| 后端 ruff | All checks passed | 一致 |
| 后端 pytest | **293 passed**（41.2s） | 267 → 293（+26） |
| ONNX 运行时（本地 Windows/Py3.9） | 全部基准与准确率测试均在此路径执行 | 一致 |
| TensorFlow 运行时（CI/Linux） | **未执行** —— 本阶段未推送，无法触发 CI | 见下 |
| 前端 tsc | exit 0 | 一致 |
| 前端 vitest | **70 passed** | 一致（未退化） |
| 端到端 Playwright | **9 passed** | 一致（未退化） |
| Alembic 迁移 | `0002_event_confidence` 升级成功，17 表 | 新增迁移 |

新增测试：`test_transcription_stages.py` 15 项、`test_recognition_benchmark.py` 11 项。
原有 267 项全部保持通过，未修改任何既有断言（仅把 `test_note_accuracy` 里的补丁目标从
`note_extraction._load_module` 改为 `inference.load_module`，属重构后的等价适配）。

---

## 10. 已知问题

1. 合成基准不代表真实录音精度（见 §8.3）。
2. 0.15s 重复同音在留出集上仍有 1/3 漏检（TD-02b）。
3. 泛音列固定为 10 个音程；+13/+29 这类**非谐波**伪影无法用音程规则清除。
4. 置信度是检测强度经线性缩放，**不是概率**；UI 已明确写"不等于实际准确率"。
5. ONNX（本地）与 TensorFlow（CI/Linux）两套后端未做逐音符一致性对比，仅保证 API 契约一致。

---

## 11. TD-01 / TD-02 更新

| ID | 原状态 | 新状态 | 依据 |
| --- | --- | --- | --- |
| TD-01a | 复音精度不足（八度泛音假阳性） | **CLOSED** | 三音和弦 F1 0.750→1.000；真实八度/五度不被误杀（dev+test 断言） |
| TD-01b | — | **OPEN（新登记）** | 真实录音的复音精度未验证（合成基准之外） |
| TD-02a | 快速音型召回不足 | **CLOSED** | 0.15s 音型 R 0.250→1.000；留出集 fast_015 F1=1.000 |
| TD-02b | — | **OPEN（新登记）** | 0.15s **同音重复**在留出集 R=0.667 |
| TD-03/04/05/06 | 不变 | 不变 | 不在本阶段范围 |

---

## 12. 判定

### PASS

理由：
1. 五项验收目标在**留出测试集**上全部达标（不是调参集）。
2. 改进来自可解释的后处理策略（泛音抑制、能量切分、能量感知合并），并有 26 项新测试锁定。
3. 无回归：293 / 70 / 9 全绿，MusicDocument、双谱、播放、导出、9:16 图片导出均未受影响。
4. 未使用 Mock、未修改测试真值、未降低任何阈值。

保留项（不影响 PASS，但必须写在产品文案里）：
- TD-01b / TD-02b 未关闭；
- 合成基准 ≠ 真实录音精度。

**未执行**：`git push`、部署、修改冻结基线。等待 V1.1-B 授权。

### 12.1 关于 TensorFlow 路径

本阶段**没有推送**，因此 GitHub CI（Linux + TensorFlow 后端）未运行。
推理调用方式与 V1.0 完全相同（仍调用 `basic_pitch.inference.predict`，仅参数来自
`TranscriptionConfig`），后处理是纯 Python/NumPy，与运行时无关；
但"TensorFlow 下基准指标一致"这一条**未经实测**，属未验证项，不得写成已通过。
推送后应立刻用 CI 的 E2E + pytest 复核。

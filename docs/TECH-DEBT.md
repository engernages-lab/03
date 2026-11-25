# PocketScore AI · 正式技术债务清单

> 本清单为 **V1.0-A.10 基线冻结**时的权威债务登记。
> 状态约定：`OPEN` = 未完成、`BLOCKED` = 缺外部条件、`DEFERRED` = 已排期到后续版本。
> **任何 `OPEN` / `BLOCKED` 项都不得在验收报告中被标记为已完成。**

| ID | 问题 | 严重度 | 状态 | 证据 | 目标版本 |
| --- | --- | --- | --- | --- | --- |
| TD-01a | 复音识别：八度泛音假阳性 | 高 | `CLOSED`（V1.1-A） | 三音和弦 F1 0.750→**1.000**；泛音抑制两遍规则；真实八度/五度在 dev+test 上 F1=1.000（`test_octave_and_fifth_chords_are_not_suppressed`） | 已关闭 |
| TD-01b | 真实录音（混响/踏板/多乐器）的复音精度未经评测 | 高 | `OPEN` | 基准集全为合成音频，见 `PocketScore-V1.1-A-Recognition-Report.md` §8.3 | V1.1-C |
| TD-02a | 快速音型召回不足 | 高 | `CLOSED`（V1.1-A） | 0.15s 音型 R 0.250→**1.000**；留出集 `fast_015` F1=1.000；能量谷切分 + 能量感知合并 | 已关闭 |
| TD-02b | 0.15s **同音重复**在留出集仍有漏检 | 中 | `OPEN` | `test_repeat_015` R=0.667（6 音切出 4 段），能量谷未达 55% 中位数阈值 | V1.1-C |
| TD-03 | 多乐器分离未实现 | 中 | `DEFERRED` | 模型（Basic Pitch）不做声源分离；混音曲目识别质量随乐器数下降 | V1.0-D |
| TD-04 | 公网后端 API 未部署 | 高 | `BLOCKED` | 线上仅静态前端 <https://engernages-lab.github.io/03/>，页面显示「静态预览页，未连接 API」；缺托管账号/凭据 | 待用户授权 |
| TD-05 | 多音源平台部分未配置 | 中 | `BLOCKED` | Apple Music / Spotify 返回 `not_configured`（缺 Team ID/.p8、Client ID/Secret）；Navidrome 无真实实例；网易云/QQ 无官方接口 | 待用户提供凭据 |
| TD-06 | 浏览器下载在沙箱环境被取消 | 低 | `BLOCKED` | Chromium 对 `data:`/`blob:` 下载一律返回 `canceled`；产物字节已由 E2E 校验，OS 保存对话框未验证 | 环境限制 |
| TD-07 | 泛音抑制只覆盖 10 个谐波音程 | 低 | `OPEN` | +13/+29 半音这类非谐波伪影无法用音程规则清除（dev `legato` 可见） | V1.1-C |
| TD-08 | 置信度为检测强度缩放，非概率 | 低 | `OPEN` | `confidence = min(0.95, amplitude × 0.85)`；UI 已注明"不等于实际准确率"，未做概率标定 | V1.1-C |

## 附：本轮审计确认「不构成债务」的项

| 检查 | 结论 |
| --- | --- |
| `NotImplementedError`（`services/sources/base.py:155`） | 基类默认实现，表示该平台不支持字节代理，属正常设计 |
| 前端 `mock` 字样 | 仅出现在 `*.test.ts(x)` 的 vitest stub 中，产品代码无 mock |
| `random` / 模板音符 | 全仓库 0 处；`test_model_output_is_not_random` 断言同音频两次结果一致 |
| TODO / FIXME | 0 处 |

## 维护规则

1. 新增债务必须给出 **ID + 证据（可复现的命令或测试名）+ 目标版本**。
2. 关闭债务必须同时提供回归测试，不能只改状态。
3. 每次版本冻结时重新核对本表，未关闭项自动进入下一版验收的已知问题章节。

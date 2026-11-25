# PocketScore AI · 正式技术债务清单

> 本清单为 **V1.0-A.10 基线冻结**时的权威债务登记。
> 状态约定：`OPEN` = 未完成、`BLOCKED` = 缺外部条件、`DEFERRED` = 已排期到后续版本。
> **任何 `OPEN` / `BLOCKED` 项都不得在验收报告中被标记为已完成。**

| ID | 问题 | 严重度 | 状态 | 证据 | 目标版本 |
| --- | --- | --- | --- | --- | --- |
| TD-01 | 复音识别精度不足 | 高 | `OPEN` | 三音和弦实测 P=0.600 / R=1.000 / F1=0.750；检出多出八度泛音（C6 假阳性）。见 `docs/reports/PocketScore-A10-Model-Report.md` §4 | V1.0-C |
| TD-02 | 快速音型召回率不足 | 高 | `OPEN` | 0.15s/音、默认参数下 R=0.250 / F1=0.400，4 音只检出 1 音；需调低 `minimum_note_length` 或自适应 | V1.0-C |
| TD-03 | 多乐器分离未实现 | 中 | `DEFERRED` | 模型（Basic Pitch）不做声源分离；混音曲目识别质量随乐器数下降 | V1.0-D |
| TD-04 | 公网后端 API 未部署 | 高 | `BLOCKED` | 线上仅静态前端 <https://engernages-lab.github.io/03/>，页面显示「静态预览页，未连接 API」；缺托管账号/凭据 | 待用户授权 |
| TD-05 | 多音源平台部分未配置 | 中 | `BLOCKED` | Apple Music / Spotify 返回 `not_configured`（缺 Team ID/.p8、Client ID/Secret）；Navidrome 无真实实例；网易云/QQ 无官方接口 | 待用户提供凭据 |
| TD-06 | 浏览器下载在沙箱环境被取消 | 低 | `BLOCKED` | Chromium 对 `data:`/`blob:` 下载一律返回 `canceled`（最小复现见 `tests/e2e/score-export.spec.ts` 注释）；产物字节已由 E2E 校验，OS 保存对话框未验证 | 环境限制 |

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

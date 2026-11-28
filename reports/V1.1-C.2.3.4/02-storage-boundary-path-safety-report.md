# PocketScore AI V1.1-C.2.3.4.2 · Storage Boundary & Path Safety Hardening Report

## 1. 项目信息

| 项 | 值 |
| --- | --- |
| 项目 | PocketScore AI |
| 阶段 | V1.1-C.2.3.4.2 · Storage Boundary & Path Safety Hardening |
| 完成日期 | 2026-11-28 |
| 分支 | `pocketscore-v1.1-b` |
| 开始时 HEAD | `ef6a18df717a9c1f29a130536c8c06442b81a3e1` |
| 结束时 HEAD | `ef6a18df717a9c1f29a130536c8c06442b81a3e1`（**未提交**） |
| `origin/main` | `9e7cd419ea6576b89053ef1596d0dd155d422410`（未变） |
| `origin/pocketscore-v1.1-b` | `a94dfb98f562a0dcf9df44397ac7b09f3c333ec3`（未变） |
| 工作区 | 6 改 + 新增（含 C.2.3.2/3/4.1 既有未提交工作，全部保留） |

## 2. 阶段结论

```text
CONDITIONAL PASS
```

理由：路径安全的核心目标全部实测达成（穿越全拒、绝对/Windows/UNC 全拒、
目录链接逃逸被拒、错误响应无绝对路径、API 集成验证恶意 `stored_path` 无法读取/删除根外文件、
87 个新测试通过、全量 513 passed 无新增失败）。**唯一未完全验证项**是**文件级符号链接**
（本机 Windows 无 symlink 权限，`WinError 1314`）——该类测试自动 skip 并在 §8 标注，
目录级逃逸已用 **junction** 真实验证。按任务书"符号链接保护只在部分平台验证应给 CONDITIONAL PASS"。

## 3. 原始安全问题（C.2.3.4.1）

| ID | 问题 | 实测证据 |
| --- | --- | --- |
| P1-1 | `absolute_path` 无包含性校验，5/6 篡改 `stored_path` 可读存储根外文件 | 探针 200 + 外泄字节 |
| P1-2 | 解码失败 `details.reason` 泄露绝对路径 | `Permission denied: 'D:\…\storage'` |
| P2-1 | `../../escape.wav` 文件名原样入库并回显 | 上传 201，`filename` 原样 |

## 4. 实际修改内容

| 文件 | 函数/位置 | 修复 | 机制 | 兼容性影响 |
| --- | --- | --- | --- | --- |
| `app/core/paths.py`（**新增** 371 行） | `safe_resolve_storage_path`、`canonical_root`、`ensure_within`、`sanitize_upload_filename`、`sanitize_extension`、`scrub_paths`、`is_within` | 统一安全边界 + 文件名清洗 + 错误脱敏 | 规范化 + `resolve` + `relative_to` | 无（新模块） |
| `app/services/audio/assets.py` | `absolute_path` | 所有读取/解码/下载/删除/扒谱路径统一走安全解析 | `safe_resolve_storage_path(..., allow_missing=True)` | 合法路径行为不变；越界改抛 400 |
| 同上 | `delete_asset` | 删除前二次确认 | `ensure_within` | 越界资产删除变 400（原会删外部文件） |
| 同上 | `_finalise_asset` | 展示文件名清洗；`stored_path` 统一正斜杠 | `sanitize_upload_filename` + `as_posix()` | 新入库记录跨平台可移植；旧记录两者都接受 |
| 同上 | `_store_artwork` | artwork 写入路径过边界校验 | `safe_resolve_storage_path` | 不变 |
| `app/api/v1/audio.py` | 上传与 probe 入口 | 客户端文件名在进入服务层前清洗 | `sanitize_upload_filename` | `../../x.wav` 存为 `x.wav`；扩展名校验不变 |
| `app/services/audio/probe.py` | `verify_decodable` / `AUDIO_DECODE_FAILED` | 异常文本不再拼原始 `exc`（避免绝对路径） | `scrub_paths` + 仅保留异常类型名 | 错误码不变，`reason` 变脱敏文本 |
| `app/core/errors.py` | —（未改） | 复用现有异常体系 | — | — |
| `app/main.py` | `_error_response` | 客户端响应统一脱敏（防御纵深） | `scrub_paths(message/details)` | 合法错误文案不受影响 |

未修改：模型、迁移、路由签名、`/static` 挂载、认证架构、备份模块、CI 工作流、前端。

## 5. 路径安全设计

### 5.1 storage_root 规范化

`canonical_root()`：`resolve(strict=True)` → 必须存在且 `is_dir()`；
不存在或不是目录 → `STORAGE_UNAVAILABLE`（500，不泄露路径）。

### 5.2 路径穿越与格式校验

`_normalise_relative()` 依次拒绝：

| 检查 | 例子 |
| --- | --- |
| 非 str/Path | `42`、`None`、`bytes` |
| 空 / `.` / `..` | `""`、`"."` |
| 控制字符、NUL | `x.wav\x00.png` |
| 反斜杠统一为正斜杠后判断 | `..\..\x.wav` |
| POSIX 绝对 / UNC | `/etc/passwd`、`//host/share/x` |
| Windows 盘符 | `C:\Windows\system.ini` |
| 任意 `..` 段 | `audio/../../x` |
| `~` 开头 | `~/secret` |
| 段尾空格或点（Windows 会静默剥离 → 别名） | `audio/ab/name.` |

**禁止字符串前缀判断**：最终判定用 `resolved.relative_to(root)`，
因此 `/data/storage-evil` 不会被 `/data/storage` 误判为内部。

### 5.3 符号链接防护

`resolve(strict=False)` 会展开链接；若展开结果落在 root 外 → `relative_to` 抛 `ValueError`
→ `StoragePathViolation`。因此**不跟随**指向外部的链接，也不会对其写入或删除。

### 5.4 文件不存在场景

`allow_missing=True` 时仍会：

1. 规范化 + 拒绝所有越界形式；
2. 校验最近存在的**父目录** `resolve(strict=True)` 后仍在 root 内。

因此"目标不存在"不会放宽边界（悬空链接、缺失中间目录都被拒绝）。

### 5.5 写入与删除

- 写入：物理路径由服务端生成（内容寻址 `audio/<sha2>/<sha><ext>`），
  客户端文件名只作展示；目录创建仍经边界确认。
- 删除：`ensure_within` → `unlink`；越界在**删除数据库行之前**抛出，避免"行没了文件还在"。

### 5.6 TOCTOU 边界（明确声明）

检查与 `open`/`unlink` 是两次系统调用，理论上存在竞态窗口。本实现通过
"解析到规范路径 + 拒绝链接"收窄窗口，但**未**引入 `openat`/`O_NOFOLLOW` 级别的原子保证。
缓解前提：storage 目录仅由应用进程可写（当前部署满足）。

## 6. 文件名安全

| 规则 | 实现 |
| --- | --- |
| 分隔符 | 先 `\`→`/`，只取最后一段；产物中不含 `/` 或 `\` |
| Unicode | `NFKC` 规范化（防止全角/兼容字符伪装分隔符） |
| 控制字符 | 正则剔除 `\x00-\x1f\x7f` 与双向控制符（U+202A–202E、U+2066–2069） |
| 长度 | 主干 ≤ 120 字符，保留扩展名 |
| 首尾 | 去首尾空白与点 |
| Windows 保留名 | `CON`/`NUL`/`COM1`… → 加前缀 |
| 空/异常输入 | 回退 `audio`（probe 用 `upload.bin`） |
| 扩展名 | `sanitize_extension()` 只接受 `\.[a-z0-9]{1,8}`；`song.wav.exe` → `.exe`，仍被 `validate_extension` 拒绝 |
| 物理路径 | **始终**内容寻址，与文件名无关 |

兼容性：`.wav/.mp3/.flac/.m4a/.aac/.ogg/.opus` 全部保留；中文/日文/空格文件名保留（有测试）。

## 7. 路径信息泄露整改

| 场景 | 修改前 | 修改后 |
| --- | --- | --- |
| 解码失败 | `details.reason = "[Errno 13] Permission denied: 'D:\\…\\storage'"` | `details.reason = "<redacted>"`（或空），`reason_type` 给异常类型 |
| `verify_decodable` 失败 | `message` 拼 `str(exc)`（含路径） | `message = "decoded audio is unreadable (OSError)"` |
| 路径违规 | 无此错误（直接尝试打开） | `STORAGE_PATH_INVALID`，**不含**任何路径 |
| 兜底 | 无 | `_error_response` 对 `message`/`details` 统一 `scrub_paths()`（POSIX 根、盘符、UNC、`\\host\share`） |

## 8. 自动化测试

| 文件 | 数量 | 结果 |
| --- | --- | --- |
| `tests/test_storage_path_safety.py` | 36 | **34 passed, 2 skipped** |
| `tests/test_upload_filename_safety.py` | 35 | **35 passed** |
| `tests/test_storage_api_security.py` | 18 | **18 passed** |
| 合计新增 | **89** | **87 passed / 2 skipped** |

（全量 426 → **513** passed；跳过 1 → 3。）

| 类别 | 覆盖 |
| --- | --- |
| 路径穿越 | P01–P06 六类载荷全拒；另加反斜杠/重复分隔符/`./`/`~`/空/NUL/尾点 11 种 |
| 绝对路径 | POSIX 绝对、盘符、UNC 全拒；`tmp_path` 外部文件不可读 |
| 符号链接 | 目录级（junction）逃逸 **实测拒绝**；文件级与悬空链接 → skip（无 symlink 权限） |
| 缺失目标 | `allow_missing` 仍校验父目录；缺失但合法 → 404 `STORAGE_FILE_MISSING` |
| 正常访问 | 合法读写、删除、playback、waveform 全通 |
| 文件名 | 35 例，含中文/日文/空格/超长/控制字符/NUL/保留名/双扩展名 |
| API 集成 | 上传→串流→波形→篡改库→再读→400；篡改后删除**未**影响根外文件 |
| 泄露检查 | 响应体不含 `storage`、`/data/`、`backend/`、`Traceback`、`FileNotFoundError`、`PermissionError` |

## 9. 回归测试

| 项 | 命令 | 结果 |
| --- | --- | --- |
| 后端全量 | `pytest` | **513 passed, 3 skipped** in 96.52 s |
| Ruff | `ruff check app tests` | **All checks passed** |
| 上传/格式回归 | `pytest tests/test_audio_pipeline.py tests/test_audio_formats.py` | 通过（含在 102 passed 组合中） |
| 扒谱回归 | `pytest tests/test_transcription.py tests/test_transcription_stages.py` | **25 passed** |
| 备份模块回归 | `pytest test_database_backup test_project_backup test_storage_audit test_project_restore_e2e` | **72 passed, 1 skipped** |
| CI 工作流静态检查 | YAML 解析 + 步骤核对 | 32 步；C.2.3.2/3 步骤完整；本阶段未改动该文件 |

类型检查：项目未配置 `mypy`，**未执行**。

## 10. 验收矩阵

| ID | 项目 | 结果 | 证据 |
| --- | --- | --- | --- |
| SP-01 | 统一安全路径解析 | **PASS** | 全部读取/删除入口经 `safe_resolve_storage_path`；`rg absolute_path` 仅剩统一实现 |
| SP-02 | 相对路径穿越 | **PASS** | P01–P03 + 11 变体全 400 |
| SP-03 | 绝对路径 | **PASS** | POSIX 绝对路径被拒；外部文件未读出 |
| SP-04 | Windows 路径 | **PASS** | 盘符、UNC、反斜杠变体全拒 |
| SP-05 | 符号链接读取 | **CONDITIONAL** | 目录级 junction 实测拒绝；文件级 symlink 本机不可用 → skip |
| SP-06 | 符号链接写入 | **CONDITIONAL** | 同上（写入目标由服务端生成，越界在解析阶段即拒） |
| SP-07 | 符号链接删除 | **CONDITIONAL** | 同上（删除前 `ensure_within`） |
| SP-08 | 缺失目标文件 | **PASS** | `allow_missing` 仍校验父目录 |
| SP-09 | 正常音频访问 | **PASS** | 上传→stream 200→waveform 200 |
| SP-10 | 正常谱面访问 | **PASS** | 扒谱 25 passed；notation 由文档生成，不涉路径 |
| SP-11 | 文件名清理 | **PASS** | 35 例；响应与落库均无分隔符 |
| SP-12 | 文件名兼容性 | **PASS** | 中文/日文/空格/7 种扩展名 |
| SP-13 | 路径信息泄露 | **PASS** | 响应体断言无绝对路径 |
| SP-14 | API 集成安全 | **PASS** | 篡改 `stored_path` → 400，根外文件字节未泄露 |
| SP-15 | 扒谱回归 | **PASS** | 25 passed |
| SP-16 | 数据备份回归 | **PASS** | 72 passed（含端到端联合恢复） |
| SP-17 | 全量后端测试 | **PASS** | 513 passed，0 失败 |
| SP-18 | 代码质量 | **PASS** | Ruff 通过 |
| SP-19 | Git 边界 | **PASS** | 未提交/未推送/未合并 |
| SP-20 | 真实环境隔离 | **PASS** | 仅临时目录；未连 Railway |

## 11. 风险与遗留

| # | 项 | 等级 | 说明 |
| --- | --- | --- | --- |
| 1 | 文件级 symlink 未在本机验证 | P2（验证缺口） | Windows 无权限；逻辑已由 `resolve`+`relative_to` 覆盖，目录级已实测 |
| 2 | TOCTOU 窗口未消除 | P2 | 未上 `O_NOFOLLOW`/`openat`；依赖 storage 目录独占写权限 |
| 3 | `/static` 整树暴露 | **P0（未修，属 C.2.3.4.4）** | 本阶段明确不改，避免破坏业务接口 |
| 4 | 无用户身份/所有权 | **P0（未修，C.2.3.4.4）** | 同上 |
| 5 | 未加密备份 | P1（C.2.3.4.5） | 未涉及 |
| 6 | 无 API 限流 | P2（C.2.3.4.3） | 未涉及 |
| 7 | 旧的 `stored_path`（反斜杠）兼容 | 低 | 解析器两侧都接受；新记录统一正斜杠 |

**明确声明**：C.2.3.4.2 **不代表**已解决用户身份、资源所有权、跨用户隔离、
`/static` 暴露、文件引用保护、备份加密、API 限流。

## 12. Git 与环境边界

| 项 | 状态 |
| --- | --- |
| 修改 Railway | ❌ 无 |
| 访问真实 Volume | ❌ 无 |
| 修改真实数据库 | ❌ 无 |
| Commit | ❌ 无 |
| Push | ❌ 无 |
| Merge | ❌ 无 |
| 影响 `origin/main` | ❌ 无（`9e7cd41` 未动） |
| C.2.3.2/3 未提交工作 | ✅ 完整保留（`backend/app/ops/`、4 个测试、`docs/operations/`、`reports/V1.1-C.2.3/`、CI 21 行改动） |

本阶段新增/修改文件：

```text
新增  backend/app/core/paths.py
新增  backend/tests/test_storage_path_safety.py
新增  backend/tests/test_upload_filename_safety.py
新增  backend/tests/test_storage_api_security.py
新增  reports/V1.1-C.2.3.4/02-storage-boundary-audit.md
新增  reports/V1.1-C.2.3.4/02-storage-boundary-path-safety-report.md
修改  backend/app/services/audio/assets.py   (+18/-4)
修改  backend/app/api/v1/audio.py            (+2/-1)
修改  backend/app/main.py                    (+7)
修改  backend/app/services/audio/probe.py    (+5/-2)
```

## 13. 下一阶段建议

可以进入 **C.2.3.4.3 · Upload Rate Limiting, Supply-chain & Runtime Hardening**。
但请注意：**P0 仍未清除**（身份/所有权、`/static` 暴露），因此**仍不允许**开放多用户试用，
也不允许进入 C.2.4。建议 4.3 与 4.4 并行推进，4.4 完成后才做试用评估。

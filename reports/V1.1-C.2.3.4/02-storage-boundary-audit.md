# PocketScore AI V1.1-C.2.3.4.2 · 存储边界审计（实施前）

> 只读审计，2026-11-28。目标是把 C.2.3.4.1 的路径类问题定位到具体行号与调用链，
> 再决定最小修改面。

## 1. Git 基线（审计时实测）

| 项 | 值 |
| --- | --- |
| 分支 | `pocketscore-v1.1-b` |
| HEAD | `ef6a18df717a9c1f29a130536c8c06442b81a3e1` |
| `origin/pocketscore-v1.1-b` | `a94dfb98f562a0dcf9df44397ac7b09f3c333ec3` |
| `origin/main` | `9e7cd419ea6576b89053ef1596d0dd155d422410` |
| 未提交（必须保留） | `M .github/workflows/docker-verify.yml`、`M .gitignore`；`?? backend/app/ops/`、4 个测试文件、`?? docs/operations/`、`?? reports/V1.1-C.2.3/` |

上述未提交内容属于 C.2.3.2 / C.2.3.3 / C.2.3.4.1，本阶段**不触碰**。

## 2. 风险代码位置

| 位置 | 代码 | 问题 |
| --- | --- | --- |
| `app/services/audio/assets.py:305-306` | `def absolute_path(record): return get_settings().storage_path / record.stored_path` | **唯一路径解析点**，无任何校验：绝对路径会覆盖左操作数，`..` 会逃逸 |
| `app/services/audio/assets.py:130` | `target = settings.artwork_path / f"{sha}{ext}"` | sha 来自 checksum，安全；但 `_store_artwork` 无边界确认（防御性） |
| `app/services/audio/assets.py:338-345` | `delete_asset`：`path = absolute_path(record)` → `unlink()` | 删除跟随逃逸路径 |
| `app/services/audio/assets.py:284` | `stored_path=str(target.relative_to(settings.storage_path))` | 写入侧正确（相对路径） |
| `app/services/audio/assets.py:174/231-234` | `target.write_bytes` / `os.replace` | 写入目标是服务端计算的内容寻址路径，用户不可控 |
| `app/services/audio/assets.py:41` | `open(path)` 读文件用于 hash | 入参来自服务端 |
| `app/api/v1/audio.py:205-213` | `stream`: `absolute_path` → `FileResponse` | 逃逸即任意文件下载 |
| `app/api/v1/audio.py:227` | `path.open("rb")`（Range 分支） | 同上 |
| `app/services/transcription.py:120` | `path = audio_assets.absolute_path(asset)` | 扒谱入口也会跟着逃逸 |
| `app/services/audio/assets.py:349/354/361/371` | waveform / analysis / thumbnail / copy | 全部经 `absolute_path` |
| `app/services/audio/probe.py`（异常处） | 抛 `AUDIO_PROBE_FAILED` 时 `details.reason` 带 `[Errno 13] Permission denied: 'D:\…'` | **绝对路径泄露**（C.2.3.4.1 实测复现） |
| `app/api/v1/audio.py:96-118` | `tempfile.mkdtemp` + `rmtree` | 临时目录在系统 tmp，非用户可控，安全 |

## 3. 调用链

```
GET /api/v1/audio/assets/{id}/stream
  → assets.get_asset(db, id)            （DB 行，stored_path 来自库）
  → assets.absolute_path(record)        ← 唯一解析点，无校验
  → FileResponse / path.open()

GET /api/v1/audio/assets/{id}/waveform
  → assets.asset_waveform → decode_mono(absolute_path(record)) → librosa/soundfile

POST /api/v1/transcription/upload  → transcription.run_job
  → audio_assets.absolute_path(asset)   → 推理

DELETE /api/v1/audio/assets/{id}
  → assets.delete_asset → absolute_path → unlink()

GET /static/{path}
  → StaticFiles(directory=storage_path)  ← 不在本阶段范围（C.2.3.4.4）
```

**结论**：只要把 `absolute_path` 换成统一安全解析，上述读取/解码/删除/扒谱入口全部收敛；
写入侧本来就由服务端生成路径，只需补文件名清洗与目录创建校验。

## 4. 读取 / 写入 / 删除入口清单

| 类型 | 入口 | 路径来源 | 需要校验 |
| --- | --- | --- | --- |
| 读取 | `/assets/{id}/stream`、`/waveform`、`/analysis`、transcription | `absolute_path` | ✅ 本阶段 |
| 读取 | artwork（`/static/artwork/*`） | StaticFiles | 范围外（C.2.3.4.4） |
| 读取 | MIDI 导入（`midi.py`） | 上传临时文件 | 临时目录，服务端生成 |
| 写入 | `ingest_audio` / `ingest_audio_from_path` | 内容寻址 `audio/<sha2>/<sha><ext>` | ✅ 目录创建 + 相对路径 |
| 写入 | `_store_artwork` | `artwork/<sha><ext>` | ✅ 边界确认 |
| 写入 | 上传临时文件 | `tempfile.mkdtemp` | 系统临时目录 |
| 删除 | `delete_asset` | `absolute_path` | ✅ 本阶段 |
| 删除 | 上传失败清理 | 服务端 tmp 路径 | 范围外（安全） |

## 5. 现有测试覆盖

| 测试 | 覆盖 |
| --- | --- |
| `test_audio_pipeline.py` / `test_audio_formats.py` | 正常上传、格式探测、去重（只走合法路径） |
| `test_database_backup.py`（C.2.3.2） | 备份/恢复，不涉及 API 路径 |
| `test_storage_audit.py` / `test_project_backup.py`（C.2.3.3） | 审计工具的 `is_within`，**不覆盖 API 读取** |
| C.2.3.4.1 探针 | 已证明 5/6 篡改 `stored_path` 可逃逸（临时脚本，未入库） |

**缺口**：没有任何仓库内测试断言 API 对恶意 `stored_path` 的拒绝。

## 6. 修改计划（最小面）

| 文件 | 变更 |
| --- | --- |
| `app/core/paths.py`（新增） | `safe_resolve_storage_path`、`sanitize_upload_filename`、`scrub_paths`、异常类型 |
| `app/services/audio/assets.py` | `absolute_path` 改走安全解析；文件名清洗；artwork/写入目录边界 |
| `app/api/v1/audio.py` | 上传响应/错误不再带绝对路径；`stream` 复用安全解析 |
| `app/core/errors.py` | `details` 统一脱敏（防御性） |
| `app/services/audio/probe.py` | `reason` 只保留错误类别 |
| `backend/tests/test_storage_path_safety.py`（新增） | 路径穿越 + 符号链接 |
| `backend/tests/test_upload_filename_safety.py`（新增） | 文件名清洗与兼容性 |
| `backend/tests/test_storage_api_security.py`（新增） | API 集成 + 泄露检查 |

不修改：模型、迁移、路由签名、`/static` 挂载、认证架构、备份模块、CI 工作流。

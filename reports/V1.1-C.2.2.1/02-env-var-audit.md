# V1.1-C.2.2.1 · 02 环境变量名称审计（部署前置硬门槛）

- **日期**：2026-11-26
- **结论**：**代码只读取 `POCKETSCORE_` 前缀，没有任何别名机制**

---

## 1. 代码依据

`backend/app/core/config.py`：

```python
# L43
class Settings(BaseSettings):
    # L46-L49
    model_config = SettingsConfigDict(
        env_prefix="POCKETSCORE_",
        env_file=(str(BACKEND_DIR / ".env"), str(PROJECT_ROOT / ".env")),
        env_file_encoding="utf-8",
    )
```

检索结果：

```text
$ grep -nE "validation_alias|AliasChoices|alias=" backend/app/core/config.py
（无匹配）
```

→ **不存在** `validation_alias` / `AliasChoices` / 字段级 `alias`。
Pydantic Settings 的规则是 `env_prefix + field_name.upper()`，因此：

- `POCKETSCORE_ACCESS_GATE_TOKEN` ✅ 被读取
- `ACCESS_GATE_TOKEN` ❌ **完全被忽略**（Railway 里只写这个 → 容器启动即失败）

C.2.2 报告正文里出现过一次裸写 `ACCESS_GATE_TOKEN`（`05-final-acceptance.md` §5 的命令片段），
属于**文档简写错误**，已在本次修正为全名，并补了"四条斜杠"提醒。

## 2. 环境变量映射表（每行都有代码依据）

| 配置用途 | 代码实际读取名称 | 是否支持别名 | Railway 应配置名称 | 必需 |
| --- | --- | --- | --- | --- |
| Staging 环境 | `POCKETSCORE_ENVIRONMENT`（`config.py:99` 附近，`environment: str = "development"`） | ❌ 无 | `POCKETSCORE_ENVIRONMENT=staging` | ✅ 是 |
| Session Secret | `POCKETSCORE_SESSION_SECRET` | ❌ 无 | 同名 | ✅ 是 |
| Token Encryption Key | `POCKETSCORE_TOKEN_ENCRYPTION_KEY` | ❌ 无 | 同名（Fernet key） | ✅ 是 |
| Access Gate 模式 | `POCKETSCORE_ACCESS_GATE_MODE`（默认 `auto`） | ❌ 无 | 可省略（auto 在 staging 自动启用） | 建议显式 |
| Access Gate Token | `POCKETSCORE_ACCESS_GATE_TOKEN` | ❌ 无 | 同名 | ✅ 是（或改用 user+password） |
| Access Gate 基本认证 | `POCKETSCORE_ACCESS_GATE_USER` / `POCKETSCORE_ACCESS_GATE_PASSWORD` | ❌ 无 | 二选一 | 条件必需 |
| CORS Origins | `POCKETSCORE_CORS_ORIGINS` | ❌ 无 | `https://engernages-lab.github.io` | ✅ 是 |
| Private Network Sources | `POCKETSCORE_ALLOW_PRIVATE_NETWORK_SOURCES` | ❌ 无 | `false` | ✅ 是 |
| Database URL | `POCKETSCORE_DATABASE_URL` | ❌ 无 | `sqlite:////data/pocketscore.db` | ✅ 是 |
| Storage Directory | `POCKETSCORE_STORAGE_DIR` | ❌ 无 | `/data/storage` | ✅ 是 |
| Model Preload | `POCKETSCORE_MODEL_PRELOAD`（默认 `False`） | ❌ 无 | `true` | 建议 |
| Maximum Upload Size | `POCKETSCORE_MAX_UPLOAD_MB`（默认 `100`） | ❌ 无 | `50` | ✅ 是 |
| 推理并发 | `POCKETSCORE_MAX_CONCURRENT_INFERENCES`（默认 1） | ❌ 无 | 可省略 | 否 |
| 推理超时 | `POCKETSCORE_INFERENCE_TIMEOUT_SECONDS`（默认 300） | ❌ 无 | 可省略 | 否 |
| HTTP 端口 | **`PORT`**（**不是** Settings 读取） | — | Railway 自动注入 | 自动 |

### 2.1 `PORT` 的特殊说明（易错点）

`Settings` 里确实有 `port` 字段（环境名 `POCKETSCORE_PORT`），但**容器实际监听端口不来自它**：

```dockerfile
CMD ["sh", "-c", "exec python -m uvicorn app.main:app --host 0.0.0.0 \
     --port \"${PORT:-8000}\" --timeout-graceful-shutdown 25 ..."]
```

即 `PORT` 由 **shell** 展开给 uvicorn。Railway 注入 `PORT` 即可生效，
**不要**去设置 `POCKETSCORE_PORT`（两者互不影响，设了反而容易误判）。

## 3. 两个会静默丢数据的坑（实测确认）

```python
# config.py:256-283
def _resolve(self, raw): p = Path(raw).expanduser(); return p if p.is_absolute() else (BACKEND_DIR / p).resolve()
def sqlite_file_path(self): _, _, raw = self.database_url.partition(":///"); return self._resolve(raw)
```

实测（本机 Python 3.9.13）：

| 配置值 | 实际落点 | 容器内后果 |
| --- | --- | --- |
| `POCKETSCORE_DATABASE_URL=sqlite:////data/pocketscore.db` | `/data/pocketscore.db` | ✅ 卷内，持久 |
| `POCKETSCORE_DATABASE_URL=sqlite:///data/pocketscore.db` | `<backend>/data/pocketscore.db` | ❌ 写到 `/app/data/`，**重启即丢** |
| `POCKETSCORE_STORAGE_DIR=/data/storage` | `/data/storage` | ✅ 卷内 |
| `POCKETSCORE_STORAGE_DIR=./data/storage` | `<backend>/data/storage` | ❌ 临时层 |

**必须四条斜杠**（`sqlite:////`）。少一条不会报错，只会安静地把数据存到临时文件系统。

## 4. CORS 解析行为

自定义 `_CsvEnvSource` 覆盖了 `prepare_field_value`，实测：

```text
POCKETSCORE_CORS_ORIGINS=https://engernages-lab.github.io      -> ['https://engernages-lab.github.io']
POCKETSCORE_CORS_ORIGINS="https://a.example, https://b.example" -> ['https://a.example', 'https://b.example']（自动去空格）
```

单值写错成 JSON 数组会直接启动失败（这是 C.2 修复过的历史 bug，当前行为正确）。

## 5. 访问门禁在 staging 的实际解析

```text
Settings(environment=staging, ..., access_gate_token=...) → validate_hardened_secrets() == []
build_gate(...).describe() → {'mode': 'token', 'enabled': True, 'token_configured': True,
                              'basic_configured': False, 'exempt_paths': ['/health', '/ready']}
```

即：给了 token → `auto` 解析为 `token` 模式并启用；不给 → 启动期直接拒绝。

## 6. 结论

| 项 | 结果 |
| --- | --- |
| 变量名不一致 | ❌ 代码层面不存在；仅一处文档简写已修正 |
| 是否需要改代码 | ❌ 不需要（无配置缺陷） |
| 是否需要重跑 Docker CI | ❌ 不需要（未改运行时代码） |
| 部署时唯一必须记住的 | 全部带 `POCKETSCORE_` 前缀；DB URL **四条斜杠**；端口用 `PORT` |

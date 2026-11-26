# V1.1-C.2.2.1 · 03 部署前本地检查（阶段 4）

- **日期**：2026-11-26
- **范围**：后端 / 前端 / 构建产物 / 配置文件静态核验
- **不含**：Docker 构建（由 GitHub Actions 承担）、云端任何项目

---

## 1. 后端

```text
$ python -m ruff check app tests
All checks passed!

$ python -m pytest
346 passed in 36.11s
```

覆盖范围（与阶段 4.1 要求对应）：

| 要求 | 对应测试 | 结果 |
| --- | --- | --- |
| Access Gate 单元测试 | `tests/test_access_gate.py`（19 项） | ✅ |
| Settings 安全校验 | `tests/test_production_config.py` | ✅ |
| Health / Ready | `tests/test_health.py` | ✅ |
| 音频上传 | `tests/test_upload_limits.py` 等 | ✅ |
| Basic Pitch 推理 | `tests/test_model_manager.py`、`test_note_accuracy.py` | ✅ |
| 项目保存 / 读取 | 文档 API 测试 | ✅ |
| SQLite 持久化 | DB 层测试 | ✅ |
| 文件存储 | 资产测试 | ✅ |
| API 权限检查 | 门禁测试（401/200/429/OPTIONS） | ✅ |

## 2. 前端

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 类型检查 | `npx tsc --noEmit` | ✅ exit 0 |
| 单元测试 | `npx vitest run` | ✅ **103 passed**（12 文件） |
| 生产构建 | `npm run build` | ✅ `built in 9.92s` |
| Sourcemap | 计数 | ✅ **0** 个 `.map` |

### 2.1 构建产物密钥扫描

```text
clean: ACCESS_GATE_TOKEN
clean: SESSION_SECRET
clean: TOKEN_ENCRYPTION_KEY
clean: Bearer
clean: smoke-access-token
```

即 `frontend/dist` 内**不含**后端共享凭据，也不含 Authorization 头构造代码。

## 3. 部署配置静态核验

### 3.1 `railway.json`

```json
{
  "build": { "builder": "DOCKERFILE", "dockerfilePath": "backend/Dockerfile" },
  "deploy": {
    "healthcheckPath": "/health",
    "healthcheckTimeout": 180,
    "startCommand": null,
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 5,
    "numReplicas": 1
  }
}
```

| 项 | 结论 |
| --- | --- |
| 构建方式 | Dockerfile ✅ |
| Dockerfile 路径 | `backend/Dockerfile`（相对仓库根）✅ |
| Healthcheck | `/health` ✅（该路径在门禁中豁免，不会被 401 拦住） |
| 超时 | 180 s（模型加载 + 预热约 10 s，余量充足）✅ |
| 副本数 | 1（与内存限流、单文件 SQLite 一致）✅ |
| startCommand | `null`（用镜像 CMD，保留 `$PORT` 展开）✅ |

### 3.2 `backend/Dockerfile`

```text
WORKDIR /app
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3
CMD ["sh","-c","exec python -m uvicorn app.main:app --host 0.0.0.0 --port \"${PORT:-8000}\" --timeout-graceful-shutdown 25 --proxy-headers --forwarded-allow-ips='*'"]
```

| 项 | 结论 |
| --- | --- |
| `$PORT` 注入 | ✅ shell 展开，默认 8000 |
| 优雅退出 | ✅ `--timeout-graceful-shutdown 25` |
| 数据卷声明 | ✅ `/data` |
| 模型包 | ✅ `--no-deps` 安装，构建期断言无 TensorFlow |

### 3.3 持久化路径一致性

| 用途 | 生产中必须的值 | 默认值（危险） |
| --- | --- | --- |
| SQLite | `sqlite:////data/pocketscore.db` | `sqlite:///./data/pocketscore.db` → `/app/data/`（临时） |
| 音频/存储 | `/data/storage` | `./data/storage` → `/app/data/storage`（临时） |

**未在 Railway 上核验 Volume 是否真的挂到 `/data`** —— 无登录权限，见 04 报告。

## 4. Docker CI（远程证据，非本地执行）

| 项 | 值 |
| --- | --- |
| 最近绿色 run | `45828419659` |
| 提交 | `1dcaecc` |
| 结果 | 29 步全绿（构建、镜像断言、PORT 8123、ready、真实扒谱、持久化重建、优雅退出、门禁断言） |
| 当前 HEAD 差异 | `9856378` 仅改 `tests/e2e/*.spec.ts` 与 `reports/**`，不进入镜像 |

## 5. 结论

本地与静态检查全部通过，具备部署条件。
**未执行**：Docker 构建（本机无 Docker）、Railway 部署、云端任何测试。

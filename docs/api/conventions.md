# API 约定 · PocketScore AI V1.0-A

## 1. 版本与路径

- 所有业务接口位于 `/api/v1` 之下；新增能力只增不改，破坏性变更才升 `v2`。
- 资源命名使用复数名词：`/documents`、`/keyboard-layouts`、`/sources`。
- 动作型接口用子路径：`/documents/{id}/duplicate`、`/midi/import`。

## 2. 请求

- `Content-Type: application/json`（文件上传为 `multipart/form-data`）。
- 可选请求头 `X-Request-ID`：客户端自带的追踪 ID，会回显到响应头与错误体。
- 时间一律使用 ISO-8601 UTC 字符串（`2026-11-24T09:00:00Z`）。

## 3. 响应

成功响应直接返回资源 JSON（2xx）。列表响应统一结构：

```json
{ "items": [], "total": 0, "limit": 50, "offset": 0 }
```

删除成功返回 `204 No Content`。

## 4. 错误信封

```json
{
  "error": {
    "code": "MUSIC_DOCUMENT_NOT_FOUND",
    "message": "MusicDocument not found",
    "details": { "document_id": "..." },
    "request_id": "9f2c..."
  }
}
```

| HTTP | 典型 code |
| --- | --- |
| 400 | `BAD_REQUEST` / `SSRF_BLOCKED` |
| 401 | `UNAUTHORIZED` / `PROVIDER_AUTH_FAILED` |
| 403 | `FORBIDDEN` / `PROVIDER_RESTRICTED` |
| 404 | `NOT_FOUND` |
| 409 | `CONFLICT` |
| 413 | `PAYLOAD_TOO_LARGE` |
| 415 | `UNSUPPORTED_MEDIA_TYPE` |
| 422 | `VALIDATION_ERROR`（`details.fields[]` 给出字段级原因） |
| 500 | `INTERNAL_ERROR` |
| 501 | `DEPENDENCY_MISSING`（例如缺少 FFmpeg） |
| 502/503 | `PROVIDER_ERROR` / `PROVIDER_UNAVAILABLE` |

前端 `ApiError` 直接暴露 `code` / `message` / `details` / `requestId`。

## 5. 分页

查询参数 `limit`（默认 50，最大 200）与 `offset`（默认 0），响应回传同样的
`limit` / `offset` / `total`。

## 6. 文件与静态资源

- 音频/封面由 `/static/...` 提供，路径由后端返回，前端通过 `staticUrl()` 拼接。
- 上传限制由 `POCKETSCORE_MAX_UPLOAD_MB` 控制，超限返回 `413`。
- 类型白名单：音频 `mp3/wav/flac/m4a/aac/ogg/opus`，MIDI `mid/midi`。

## 7. 健康检查

| 端点 | 用途 |
| --- | --- |
| `GET /api/v1/health` | 存活 + 运行时能力探测 |
| `GET /api/v1/health/ready` | 依赖就绪（数据库、FFmpeg、MIDI） |
| `GET /api/v1/health/capabilities` | 仅能力矩阵 |

## 8. 鉴权（预留）

V1.0-A 为单用户本地工作站，未启用登录。第三方平台的 OAuth 令牌由后端
加密存储，任何响应都不会回传明文令牌，仅返回 `connected` 状态与账号展示名。

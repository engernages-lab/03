# 架构总览 · PocketScore AI V1.0-A

## 1. 分层

```
┌─────────────────────────────────────────────────────────────┐
│  Frontend (React 18 + TS + Vite)                            │
│  AppShell · 页面 · Zustand store · TanStack Query           │
│  只负责交互与渲染，不重复实现音乐数据转换                    │
└───────────────────────────┬─────────────────────────────────┘
                            │  /api/v1 (JSON, 统一错误信封)
┌───────────────────────────▼─────────────────────────────────┐
│  FastAPI (app/api/v1/*)                                     │
│  路由层：参数校验（Pydantic）→ 调用 service → 序列化响应     │
├─────────────────────────────────────────────────────────────┤
│  Service 层 (app/services/*)                                │
│  music_document · keyboard · notation(grid/jianpu) · midi   │
│  audio · sources(adapters) · library · playback · eligibility│
├─────────────────────────────────────────────────────────────┤
│  Repository / ORM (app/models/*, SQLAlchemy 2)              │
│  SQLite (WAL) · Alembic 迁移                                │
└─────────────────────────────────────────────────────────────┘
```

## 2. 关键约束

### 2.1 单一数据源

`MusicDocument` 是唯一音符数据来源。格子谱（`GridNotationEngine`）与数字谱
（`JianpuNotationEngine`）都是**纯函数**：`MusicDocument + KeyboardLayout + NotationSettings -> ViewModel`。
任何编辑都作用于 `MusicDocument`，两种谱面从同一份数据重新推导，因此天然同步。

### 2.2 逻辑单一实现

| 转换 | 唯一实现位置 | 前端职责 |
| --- | --- | --- |
| 音高 → 键位 | `services/keyboard/mapping.py` | 渲染 `mapped_key` |
| 音高 → 简谱数字 / 八度点 | `services/notation/jianpu.py` | 渲染数字与点 |
| 音符 → 格子坐标 | `services/notation/grid.py` | 渲染格子 |
| MIDI → MusicDocument | `services/midi/importer.py` | 无 |

前端不实现上述任何算法，只消费后端返回的视图模型。

### 2.3 能力探测

`GET /api/v1/health` 在进程内探测 FFmpeg / librosa / soundfile / mido /
pretty_midi / music21 / mutagen 是否可用。前端据此禁用依赖缺失的功能，
避免“看起来能用、点了报错”。

### 2.4 权限分层（A.8）

扒谱资格不是布尔值，而是五个独立权限的组合：

| 权限 | 含义 |
| --- | --- |
| `metadata_access` | 可读取曲目元数据 |
| `playback_access` | 可通过官方方式播放 |
| `audio_read_access` | 可读取原始音频字节 |
| `ai_processing_permission` | 允许送入 AI 处理 |
| `model_training_permission` | 允许用于模型训练（与单次处理分离） |

判定结果：`ELIGIBLE` / `INELIGIBLE` / `REQUIRES_USER_UPLOAD` /
`REQUIRES_PERMISSION` / `PROVIDER_RESTRICTED` / `UNKNOWN`，并附带人类可读原因。

## 3. 错误与日志

- 所有错误响应统一为 `{ "error": { code, message, details?, request_id } }`。
- 每个请求分配 `X-Request-ID`（可透传），贯穿日志与错误响应。
- 5xx 只记录服务端日志，响应不含堆栈。

## 4. 目录职责

| 路径 | 职责 |
| --- | --- |
| `backend/app/api/v1/` | HTTP 边界，不做业务计算 |
| `backend/app/services/` | 领域逻辑，可被测试直接调用 |
| `backend/app/models/` | ORM 表结构 |
| `backend/app/schemas/` | Pydantic 契约 |
| `frontend/src/lib/` | API 客户端、类型、格式化 |
| `frontend/src/store/` | 跨组件状态（播放器、文档编辑、撤销栈） |

## 5. 部署形态

前端静态资源（CDN/Nginx）与后端 API 独立部署，通过 `VITE_API_BASE_URL`
与后端 `POCKETSCORE_CORS_ORIGINS` 对接；数据库为单文件 SQLite，
部署时挂载持久卷；`/api/v1/health/ready` 供反向代理健康检查使用。

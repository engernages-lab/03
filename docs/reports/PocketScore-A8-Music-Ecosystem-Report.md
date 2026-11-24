# PocketScore A.8 — 多音源音乐中心与完整播放器报告

- **版本**：V1.0-A
- **阶段**：A.8 MusicSourceEngine · UnifiedMusicLibrary · PlaybackEngine · TranscriptionEligibilityService
- **结论**：**CONDITIONAL PASS**（本地音乐与 Navidrome 协议层完整可用；Apple Music / Spotify / 网易云 / QQ 因**缺少真实平台凭据与官方授权**，按政策如实交付为"可配置/不可用"，未伪造任何连接成功状态）

---

## 1. 交付内容

| 模块 | 状态 | 说明 |
| --- | --- | --- |
| 本地音乐上传/索引/播放 | ✅ | 多文件、**文件夹授权（目录选择 + 拖拽递归扫描）**、元数据、封面、搜索、收藏、歌单、历史 |
| Navidrome / OpenSubsonic | ✅ 协议完整实现 | `ping/getAlbumList2/getArtists/getPlaylists/getPlaylist/search3/getRandomSongs/stream`，MD5 token 认证，MockTransport 全量测试 |
| Apple Music | 🟡 代码就绪，缺凭据 | Developer Token（ES256 JWT）生成、MusicKit 播放指引、资料库接口；**未做真实账号验证**（无 Apple 开发者凭据） |
| Spotify | 🟡 仅元数据能力 | OAuth2 + 歌单/收藏/搜索 + 政策硬限制；**未做真实账号验证**（无 Client ID/Secret） |
| 网易云 / QQ 音乐 | ⛔ 不可用（如实） | 无官方第三方接口，适配器返回 `unsupported` + 官方链接证据 |
| 统一曲库 | ✅ | 16 张表，保留 `external_track_id`，ISRC 归组 |
| 完整播放器 | ✅ | 队列、随机、循环、音量、进度、历史、收藏、来源标识 |
| 扒谱资格判断 | ✅ | 五项权限 + 六种结论 + 理由 |
| 音乐工作台界面 | ✅ | 10 个页面 + 响应式侧边栏 + 底部播放条 |

## 2. 统一曲库模型

`UnifiedTrack`：`track_id`(=sha1(source:external) 前 24 位) · `source_id` · `external_track_id` ·
`title/artist/album` · `duration` · `artwork` · `source_url` · `availability` · `metadata` ·
`canonical_group_id` · `stream_url` · `is_local` · `play_count`

**合并规则（严格）**：只有 ISRC 相同才产生 `canonical_group_id`。
标题/艺人/时长**不参与**合并 —— 同名不同平台永远视为不同曲目（`test_same_title_different_sources_is_not_merged`）。

## 3. 各平台真实状态（关键，请勿误读）

| 平台 | 本机实测结果 | 依据 |
| --- | --- | --- |
| 本地音乐 | **可用**：上传 → 索引 → 播放 → 资格 → 作业，E2E 实测通过 | 真实请求 |
| Navidrome | **协议层通过**：使用 `httpx.MockTransport` 按官方 OpenSubsonic JSON 响应验证全部端点、认证签名、错误映射 | 12 项测试；**未连接真实服务器**（本机无 Navidrome 实例与凭据） |
| Apple Music | **未连接**：`test_connection()` 返回 `not_configured`（缺 team_id/key_id/.p8） | 配置缺失，如实上报 |
| Spotify | **未连接**：`not_configured`（缺 client_id/secret/redirect） | 配置缺失，如实上报 |
| 网易云 | **不可用**：`unsupported` + 证据链接 | 无官方第三方接口 |
| QQ 音乐 | **不可用**：`unsupported` + 证据链接 | 无官方第三方接口 |

> 本报告**不声称**任何平台"已授权连接成功"。Apple/Spotify 需要在 `.env` 填入
> 开发者凭据并完成 OAuth 后才能进行真实测试；相关代码路径已具备并在
> Mock 层验证了错误映射（401/403/429）。

## 4. 扒谱资格（TranscriptionEligibilityService）

五项独立权限：`metadata_access` · `playback_access` · `audio_read_access` ·
`ai_processing_permission` · `model_training_permission`

判定优先级：
`PROVIDER_RESTRICTED`（平台政策）→ `INELIGIBLE`（无接口/无元数据）→
`REQUIRES_USER_UPLOAD`（无音频读权限）→ `REQUIRES_PERMISSION`（缺用户授权）→ `ELIGIBLE`

| 来源 | 判定 | 理由 |
| --- | --- | --- |
| Spotify | `PROVIDER_RESTRICTED`（**不可覆盖**） | 政策禁止分析/输入 AI，代码强制清零三项权限 |
| Apple Music | `REQUIRES_USER_UPLOAD` | 播放可用但音频不可读，需上传自有音频 |
| 本地 / Navidrome | 默认 `REQUIRES_PERMISSION`，用户勾选授权后 `ELIGIBLE` | 需显式同意；训练权限独立且默认关闭 |
| 网易云 / QQ | `INELIGIBLE` | 无官方接口 |

## 5. 播放器

- 状态机：`queue/index/isPlaying/volume/muted/repeat/shuffle/shuffleOrder/currentTime/duration`
- 纯函数：`computeNextIndex` / `computePreviousIndex` / `buildShuffleOrder` / `cycleRepeatMode`（18 项 Vitest）
- 播放方式按来源分流：
  - 本地 → `/api/v1/audio/assets/{id}/stream`（支持 Range）
  - Navidrome → 后端代理 `/api/v1/playback/proxy/{source_id}/{external_id}`（凭据不暴露给浏览器）
  - Apple/Spotify → `mode="provider_sdk"`，前端提示“需在官方播放器中播放”，**不代理音频流**
- 播放历史在换曲时写入，`play_count` 累加。

## 6. 安全

| 项 | 实现 |
| --- | --- |
| 令牌加密 | Fernet（`POCKETSCORE_TOKEN_ENCRYPTION_KEY`，缺省用 `storage/.token_key`） |
| 明文密码 | Navidrome 密码仅用于换 token+salt，`/test` 成功后从 config 中**移除密码** |
| 令牌回传 | 任何接口都不返回 token，仅返回 `status` 与 `account_name` |
| SSRF | 协议白名单、拒绝环回/链路本地/云元数据、**逐解析地址校验**（防 DNS rebinding）、不跟随重定向 |
| 上传 | 大小上限 + 扩展名白名单 + 内容探测 |

## 7. 接口（新增 47 条）

- `/api/v1/sources`：`providers` · CRUD · `/{id}/test` · `/{id}/sync` · `/{id}/permissions` ·
  `/{id}/apple/developer-token`（ES256 JWT，测试中用公钥验签）· `/{id}/spotify/authorize-url`
- `/api/v1/library`：`tracks` · `import` · `stats` · `albums` · `artists` · `favorites` ·
  `playlists`(+tracks) · `history`
- `/api/v1/playback`：`stream/{track_id}` · `proxy/{source_id}/{external_id}`（转发 Range 并中继 206/Content-Range）
- `/api/v1/eligibility`：`/{track_id}` · `/source/{source_id}`
- `/api/v1/transcription`：`models` · `jobs` · `jobs/{id}` · `run` · `cancel`

## 8. 测试证据

```text
$ .\.venv\Scripts\python.exe -m pytest tests/test_library.py tests/test_eligibility.py \
    tests/test_sources_subsonic.py tests/test_sources_ssrf.py tests/test_transcription.py -q
................................................................  (64 passed)
```

覆盖要点：

- 本地导入（WAV）→ 曲目/艺人/专辑聚合、收藏往返、歌单增删、历史与 `play_count`。
- ISRC 相同 → 同一 `canonical_group_id`，但 `track_id` 不同；无 ISRC → 不归组。
- Subsonic：token = md5(password+salt) 且**不含明文密码**；`status="failed"` code 40 → 认证失败；
  401 → 认证失败；连接异常 → 服务不可用；非 JSON → 协议错误；专辑/搜索/歌单字段映射。
- SSRF：`file://`、`localhost`、`127.0.0.1`、`[::1]`、`169.254.169.254`、`100.100.100.200`、
  带凭据 URL 全部拒绝；私网在 `allow_private=False` 时拒绝。
- 资格：Spotify 即使授予全部权限仍 `PROVIDER_RESTRICTED`；Apple 播放可用但不 `ELIGIBLE`；
  本地默认 `REQUIRES_PERMISSION`，授权后 `ELIGIBLE` 且训练权限仍关闭。
- 播放：本地 `mode=direct`；Spotify 代理返回 403。

## 9. 前端页面

| 路由 | 内容 |
| --- | --- |
| `/dashboard` | 资料库统计、来源状态、能力探测、阶段进度、继续工作 |
| `/music-library` | 统计卡、搜索、拖拽上传、**文件夹导入**、曲目/专辑/歌手三视图、播放全部 |
| `/music-favorites` | 收藏列表 |
| `/music-playlists` | 歌单列表 + 曲目管理 + 新建/删除 |
| `/music-recent` | 播放历史 + 清空 |
| `/music-sources` | 平台卡片（能力矩阵/政策/官方文档）+ 连接表单 + 五项权限开关 |
| `/music-player` | 大封面、真实波形、进度拖拽、队列、音量、快捷键 |
| `/transcription` | 模型真实状态、MIDI 导入、音频分析、资格判定、作业记录 |
| `/scores` `{id}` | 谱面列表、双谱编辑器 |
| `/keyboard` | 布局编辑器 |

## 10. 已知问题 / 未完成

| 项 | 说明 | 后续 |
| --- | --- | --- |
| Apple Music 真实账号测试 | 缺开发者凭据（Team/Key/.p8）与 MusicKit 前端集成；**Token 生成已实现并用真实公钥验签** | 提供凭据后补 |
| Spotify 真实 OAuth | 缺 Client ID/Secret；**授权 URL 端点已实现**，且政策禁止 AI 分析，仅元数据 | 提供凭据后补 |
| Navidrome 真实服务器 | 无实例；协议层已按官方 API 实现并 Mock 验证 | 提供地址后可实测 |

> 收尾补齐的两项（已不再列为缺口）：
> 1. **文件夹授权导入** —— `<input webkitdirectory>` 目录选择 + 拖拽文件夹递归扫描
>    （`webkitGetAsEntry` 逐层遍历，含 100 条目分批读取），带进度条与失败明细；
>    非音频文件自动跳过，不会误传。
> 2. **Subsonic 播放代理 Range 透传** —— `open_stream()` 转发 `Range` 并中继
>    `206` / `Content-Range` / `Content-Length`，5 项测试覆盖。

## 11. 验收

- [x] 本地音乐可导入、索引、播放、收藏、歌单、历史、资格判定
- [x] Navidrome/OpenSubsonic 协议实现完整并通过 Mock 全量验证（**真实服务器待凭据**）
- [x] Apple Music 代码就绪，`test_connection` 如实返回缺配置（**待授权**）
- [x] Spotify 仅元数据，永久 `PROVIDER_RESTRICTED`，不进入 AI 链路
- [x] 网易云/QQ 如实标注不可用，附官方链接，无逆向接口
- [x] 资格判断五项权限独立、理由清晰
- [x] 完整播放器交互与状态机（18 项单元测试）
- [x] 工作台界面 10 个路由 + 响应式 + 深色主题（8 张截图见 `docs/screenshots/`）

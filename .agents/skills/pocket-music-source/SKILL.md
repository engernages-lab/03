---
name: pocket-music-source
description: PocketScore AI 的多音源接入契约。定义 MusicSource Adapter、统一曲库模型、播放能力与扒谱资格（五项权限）、SSRF/令牌安全与各平台合规边界；接入任何音乐平台前必读。
---

# pocket-music-source

## 1. 职责

- 定义 `MusicSourceAdapter` 协议与统一曲库模型（`UnifiedTrack/Album/Artist/Playlist`）。
- 实现各平台适配器：本地文件、Navidrome/OpenSubsonic、Apple Music、Spotify、网易云、QQ 音乐。
- 提供播放能力抽象（`PlaybackEngine` 消费）与**扒谱资格判定**（`TranscriptionEligibilityService`）。
- 负责令牌加密存储、连接测试、错误映射、SSRF 防护。

不负责：音频信号分析与 MIDI 解析（→ `pocket-audio-transcription`）、谱面（→ grid / jianpu）。

## 2. 统一曲库模型

### 2.1 MusicSource

`{source_id, provider, display_name, status, capabilities, config, connected_at, last_error}`

`provider ∈ {local, subsonic, apple_music, spotify, netease, qqmusic}`

### 2.2 UnifiedTrack

| 字段 | 说明 |
| --- | --- |
| `track_id` | 内部 ID（`{provider}:{external_id}` 的稳定哈希） |
| `source_id` | 来源 |
| `external_track_id` | **原始来源 ID，必须保留** |
| `title` / `artist` / `album` | 元数据 |
| `duration` | 秒 |
| `artwork` | 封面 URL/本地路径 |
| `source_url` | 平台页面地址 |
| `availability` | `streamable`/`metadata_only`/`unavailable` |
| `metadata` | 原始 provider 字段（只存允许存储的部分） |

### 2.3 合并规则（重要）

- **禁止仅按标题合并**。同名不同平台/不同版本的曲目一律视为不同 `UnifiedTrack`。
- 允许"元数据级"关联：`canonical_group_id`（同 ISRC + 同艺人 + 时长差 < 2s 才可归组）。
- 不同平台同名歌曲**不得**共享音频或播放权限。

## 3. 适配器协议

```python
class MusicSourceAdapter(Protocol):
    provider: str
    async def test_connection(self) -> ConnectionResult: ...
    async def list_albums(self, limit, offset) -> Page[UnifiedAlbum]: ...
    async def list_artists(self, limit, offset) -> Page[UnifiedArtist]: ...
    async def list_playlists(self) -> list[UnifiedPlaylist]: ...
    async def get_playlist_tracks(self, playlist_id) -> Page[UnifiedTrack]: ...
    async def search(self, query, limit) -> SearchResult: ...
    async def get_stream_info(self, external_track_id) -> StreamInfo: ...
    def capabilities(self) -> SourceCapabilities: ...
```

## 4. 各平台合规边界（**硬约束**）

| 平台 | 允许 | 禁止 |
| --- | --- | --- |
| 本地 | 用户授权目录上传/索引、播放、扒谱 | 未经同意上传；把用户文件用于训练 |
| Navidrome / OpenSubsonic | 官方 API 认证、元数据、列表、流播放（用户自己的服务器） | 绕过服务器鉴权；把他人服务器当公共资源 |
| Apple Music | MusicKit 官方授权、Developer Token、用户资料库/歌单/搜索/播放、播放状态 | 绕过 DRM；下载/转存音频流；把播放流当音频资产 |
| Spotify | OAuth 2.0、元数据、用户歌单、收藏、当前播放、官方播放控制 | **分析 Spotify 内容**；**输入 AI/ML**；抓取音频；下载；绕过 Premium；用外部音源规避政策 |
| 网易云 | 仅官方开放平台已授权能力 | 盗取 Cookie、逆向接口、模拟登录、非官方 API 作为正式功能 |
| QQ 音乐 | 仅官方开放平台已授权能力 | 同上，且不得虚构连接成功 |

- Spotify 内容**永久** `PROVIDER_RESTRICTED`，`ai_processing_permission=false`。
- Apple Music 支持播放 ≠ 可扒谱；必须 `audio_read_access=false` 且资格为
  `REQUIRES_USER_UPLOAD`（除非用户另行上传拥有权利的音频）。
- 未获官方授权的平台，`status="unsupported"`，Adapter 保留但接口返回
  `PROVIDER_UNSUPPORTED` 与真实原因（附证据链接）。

## 5. 扒谱资格判定（`app/services/eligibility.py`）

五项权限独立求值：

| 权限 | 取值来源 |
| --- | --- |
| `metadata_access` | 适配器能力 + 是否已连接 |
| `playback_access` | 官方播放能力 |
| `audio_read_access` | 是否可读取原始字节（本地/自有服务器=是；流媒体服务=否） |
| `ai_processing_permission` | 平台政策 + 用户显式同意 |
| `model_training_permission` | 与上者**分离**，默认 false |

结果枚举：`ELIGIBLE` / `INELIGIBLE` / `REQUIRES_USER_UPLOAD` / `REQUIRES_PERMISSION` /
`PROVIDER_RESTRICTED` / `UNKNOWN`，并必须附带 `reasons: string[]` 与
`permissions` 明细。

判定优先级：`PROVIDER_RESTRICTED`(政策) > `INELIGIBLE`(无任何权限) >
`REQUIRES_PERMISSION`(缺用户同意) > `REQUIRES_USER_UPLOAD`(无音频读权限) > `ELIGIBLE`。

## 6. 安全约束

- **SSRF**：仅允许 `http/https`；默认拒绝环回（127/8、::1）与云元数据地址
  （169.254.169.254、fd00:ec2::254）；私网地址仅在
  `POCKETSCORE_ALLOW_PRIVATE_NETWORK_SOURCES=true` 且用户显式勾选时放行；
  解析后再校验解析结果（防 DNS rebinding）；请求不跟随跨域重定向。
- **令牌**：Fernet 加密后落库；`GET /sources` 只返回 `connected` 与账号展示名；
  日志与错误中不出现 token；注销时真删除。
- **密码**：不落库；仅用于换取短期 token / 会话 cookie（存于内存+短期缓存）。
- **速率**：对每个 provider 做 429 退避，错误映射为 `PROVIDER_RATE_LIMITED`。
- **CORS 与回调**：OAuth 回调地址来自配置，不接受请求体指定。

## 7. 错误处理

| 场景 | 错误码 | HTTP |
| --- | --- | --- |
| 未连接 | `SOURCE_NOT_CONNECTED` | 409 |
| 令牌失效 | `PROVIDER_AUTH_FAILED` | 401 |
| 平台不可用 | `PROVIDER_UNAVAILABLE` | 503 |
| 政策禁止 | `PROVIDER_RESTRICTED` | 403 |
| 无官方接口 | `PROVIDER_UNSUPPORTED` | 501 |
| 地址非法 | `SSRF_BLOCKED` | 400 |
| 曲目不存在 | `TRACK_NOT_FOUND` | 404 |

## 8. 测试规范

- `tests/test_eligibility.py`：每个平台的权限组合 → 期望资格与理由；
  Spotify 恒为 `PROVIDER_RESTRICTED`；Apple 播放可用但不 `ELIGIBLE`。
- `tests/test_sources_subsonic.py`：用 `httpx.MockTransport` 模拟真实 OpenSubsonic
  响应（`ping`/`getAlbumList2`/`search3`/`stream`），断言解析与错误映射。
- `tests/test_sources_ssrf.py`：私网/环回/元数据地址被拒；`file://` 被拒。
- `tests/test_library_merge.py`：同名不同来源不合并；ISRC 相同时可归组。
- 真实平台测试用 `@pytest.mark.provider` 标记并默认跳过；报告中必须区分
  **Mock 结果**与**真实平台结果**。

## 9. 验收标准

- [ ] 本地音乐可导入、索引、播放、收藏、歌单、历史、资格判定。
- [ ] Navidrome 真实授权连接与功能验证（或用 Mock 验证协议实现并在报告注明）。
- [ ] Apple Music / Spotify / 网易云 / QQ 按真实授权情况交付，未授权项明确标注。
- [ ] 五项权限独立、理由清晰、Spotify 被政策拦截。
- [ ] 无明文令牌、无 SSRF 漏洞、无逆向接口。

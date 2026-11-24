"""Music source adapter contract (owner: pocket-music-source skill).

Every provider implements :class:`SourceAdapter`.  Adapters return plain DTOs so
the library layer never sees provider-specific payloads, and they never decide
whether AI transcription is allowed - that is the eligibility service's job.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SourceCapabilities:
    """What a provider can actually do (declared, not aspirational)."""

    metadata: bool = False
    playback: bool = False
    audio_read: bool = False
    ai_processing: bool = False
    model_training: bool = False
    playlists: bool = False
    search: bool = False
    favorites: bool = False
    requires_auth: bool = True
    #: provider policy text shown in the UI
    policy_note: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "metadata": self.metadata,
            "playback": self.playback,
            "audio_read": self.audio_read,
            "ai_processing": self.ai_processing,
            "model_training": self.model_training,
            "playlists": self.playlists,
            "search": self.search,
            "favorites": self.favorites,
            "requires_auth": self.requires_auth,
            "policy_note": self.policy_note,
        }


@dataclass
class TrackDTO:
    external_id: str
    title: str
    artist: str = ""
    album: str = ""
    duration: float = 0.0
    artwork: Optional[str] = None
    source_url: Optional[str] = None
    availability: str = "metadata_only"
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_local: bool = False
    audio_asset_id: Optional[str] = None
    stream_url: Optional[str] = None
    canonical_group_id: Optional[str] = None


@dataclass
class AlbumDTO:
    external_id: str
    title: str
    artist: str = ""
    year: Optional[int] = None
    artwork: Optional[str] = None
    track_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ArtistDTO:
    external_id: str
    name: str
    artwork: Optional[str] = None
    album_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PlaylistDTO:
    external_id: str
    name: str
    description: str = ""
    artwork: Optional[str] = None
    track_count: int = 0
    is_user_owned: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PageResult:
    items: List[Any] = field(default_factory=list)
    total: int = 0
    offset: int = 0
    limit: int = 50


@dataclass
class ConnectionResult:
    ok: bool
    status: str = "disconnected"
    message: str = ""
    server_version: Optional[str] = None
    account_name: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)


class SourceAdapter(ABC):
    """Base class for provider adapters."""

    provider: str = "unknown"
    display_name: str = "Unknown"
    capabilities: SourceCapabilities = SourceCapabilities()

    def __init__(self, source_id: str, config: Optional[Dict[str, Any]] = None) -> None:
        self.source_id = source_id
        self.config = config or {}
        self.account_name: Optional[str] = None

    # -- lifecycle ---------------------------------------------------------
    @abstractmethod
    async def test_connection(self) -> ConnectionResult:
        """Verify credentials and reachability without side effects."""

    # -- library -----------------------------------------------------------
    async def list_tracks(self, limit: int = 50, offset: int = 0, **_kwargs) -> PageResult:
        return PageResult(items=[], total=0, offset=offset, limit=limit)

    async def list_albums(self, limit: int = 50, offset: int = 0) -> PageResult:
        return PageResult(items=[], total=0, offset=offset, limit=limit)

    async def list_artists(self, limit: int = 50, offset: int = 0) -> PageResult:
        return PageResult(items=[], total=0, offset=offset, limit=limit)

    async def list_playlists(self) -> List[PlaylistDTO]:
        return []

    async def get_playlist_tracks(self, playlist_id: str, limit: int = 100, offset: int = 0) -> PageResult:
        return PageResult(items=[], total=0, offset=offset, limit=limit)

    async def search(self, query: str, limit: int = 30) -> Dict[str, List[Any]]:
        return {"tracks": [], "albums": [], "artists": [], "playlists": []}

    # -- playback ----------------------------------------------------------
    async def get_stream(self, external_track_id: str) -> Optional[Dict[str, Any]]:
        """Return ``{"mode": "proxy"|"direct"|"provider_sdk", ...}`` info."""
        return None

    async def fetch_stream_bytes(self, external_track_id: str):
        """Yield chunks for proxied playback (used by /playback/proxy)."""
        raise NotImplementedError

    # -- helpers -----------------------------------------------------------
    def capability_report(self) -> Dict[str, Any]:
        return self.capabilities.as_dict()


def provider_policy(provider: str) -> str:
    """Human readable policy summary surfaced in the UI and reports."""
    return {
        "local": "用户自有文件：分析权限取决于用户是否拥有处理权。",
        "subsonic": "用户自有服务器（Navidrome/OpenSubsonic）：仅通过官方 API 访问。",
        "apple_music": (
            "MusicKit 官方授权播放；不下载、不转存音频流；扒谱需要用户另行上传拥有权利的音频。"
        ),
        "spotify": (
            "Spotify 政策禁止分析其内容或输入 AI/ML 模型；本应用仅使用元数据，"
            "且永不进入 AI 扒谱链路。"
        ),
        "netease": "网易云音乐暂无面向第三方客户端的官方开放接口，仅保留适配器占位。",
        "qqmusic": "QQ 音乐暂无面向第三方客户端的官方开放接口，仅保留适配器占位。",
    }.get(provider, "")

"""Providers without a usable official API for third-party clients.

NetEase Cloud Music and QQ Music do not currently offer an official open
platform that grants account authorisation, playlist access and playback to
third-party desktop/web clients.  RFC-level honesty is a requirement of
PocketScore, so these adapters exist as explicit,非功能 placeholders that report
``unsupported`` with evidence links instead of scraping, cookie theft or
reverse-engineered endpoints.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.services.sources.base import (
    ConnectionResult,
    PageResult,
    PlaylistDTO,
    SourceAdapter,
    SourceCapabilities,
    provider_policy,
)

EVIDENCE = {
    "netease": [
        "https://open.music.163.com/",
        "https://developer.music.163.com/",
    ],
    "qqmusic": [
        "https://y.qq.com/",
        "https://open.y.qq.com/",
    ],
}


class UnsupportedOfficialSourceAdapter(SourceAdapter):
    """Reports honestly that there is no official third-party integration."""

    provider = "unsupported"
    display_name = "Unsupported"
    capabilities = SourceCapabilities(
        metadata=False,
        playback=False,
        audio_read=False,
        ai_processing=False,
        model_training=False,
        requires_auth=False,
        policy_note="",
    )

    unsupported_reason = ""
    evidence: List[str] = []

    async def test_connection(self) -> ConnectionResult:
        return ConnectionResult(
            ok=False,
            status="unsupported",
            message=self.unsupported_reason,
            details={"evidence": self.evidence, "adapter": "placeholder"},
        )

    async def list_playlists(self) -> List[PlaylistDTO]:
        return []

    async def search(self, query: str, limit: int = 30) -> Dict[str, List[Any]]:
        return {"tracks": [], "albums": [], "artists": [], "playlists": []}

    async def list_tracks(self, limit: int = 50, offset: int = 0, **_kwargs) -> PageResult:
        return PageResult(items=[], total=0, offset=offset, limit=limit)

    async def get_stream(self, external_track_id: str) -> Optional[Dict[str, Any]]:
        return None


class NetEaseAdapter(UnsupportedOfficialSourceAdapter):
    provider = "netease"
    display_name = "网易云音乐"
    capabilities = SourceCapabilities(
        requires_auth=True, policy_note=provider_policy("netease")
    )
    unsupported_reason = (
        "网易云音乐目前未提供面向第三方客户端/Web 应用的官方开放接口"
        "（账号授权、歌单读取与播放能力均不可用）。为避免违规，"
        "PocketScore 不提供模拟登录、Cookie 注入或逆向接口，仅保留适配器占位。"
    )
    evidence = EVIDENCE["netease"]


class QQMusicAdapter(UnsupportedOfficialSourceAdapter):
    provider = "qqmusic"
    display_name = "QQ 音乐"
    capabilities = SourceCapabilities(
        requires_auth=True, policy_note=provider_policy("qqmusic")
    )
    unsupported_reason = (
        "QQ 音乐未向第三方客户端开放账号授权、歌单与播放接口。"
        "PocketScore 不实现任何非官方接口，也不伪造连接成功状态，仅保留适配器占位。"
    )
    evidence = EVIDENCE["qqmusic"]

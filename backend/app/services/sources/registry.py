"""Adapter registry and provider metadata."""

from __future__ import annotations

from typing import Any, Dict, Optional, Type

from sqlalchemy.orm import Session

from app.core.errors import BadRequestError
from app.models.source import MusicSourceRecord
from app.services.sources.apple import AppleMusicAdapter
from app.services.sources.base import SourceAdapter, provider_policy
from app.services.sources.local import LocalSourceAdapter
from app.services.sources.spotify import SpotifyAdapter
from app.services.sources.subsonic import SubsonicAdapter
from app.services.sources.unsupported import NetEaseAdapter, QQMusicAdapter

ADAPTERS: Dict[str, Type[SourceAdapter]] = {
    "local": LocalSourceAdapter,
    "subsonic": SubsonicAdapter,
    "apple_music": AppleMusicAdapter,
    "spotify": SpotifyAdapter,
    "netease": NetEaseAdapter,
    "qqmusic": QQMusicAdapter,
}

#: Providers that can be created by a user (local is auto-provisioned).
USER_CREATABLE = ("subsonic", "apple_music", "spotify", "netease", "qqmusic")

PROVIDER_INFO: Dict[str, Dict[str, Any]] = {
    "local": {
        "display_name": "本地音乐",
        "description": "用户上传或授权的本地音频文件。",
        "auth": "none",
        "docs": [],
        "can_import": True,
    },
    "subsonic": {
        "display_name": "Navidrome / OpenSubsonic",
        "description": "连接你自己的音乐服务器（官方 OpenSubsonic API）。",
        "auth": "user_password",
        "docs": ["https://opensubsonic.netlify.app/", "https://navidrome.org/docs/"],
        "can_import": True,
    },
    "apple_music": {
        "display_name": "Apple Music",
        "description": "通过 MusicKit 官方授权访问资料库与播放。",
        "auth": "musickit",
        "docs": ["https://developer.apple.com/documentation/musickitjs"],
        "can_import": True,
    },
    "spotify": {
        "display_name": "Spotify",
        "description": "元数据与官方播放控制；政策禁止用于 AI 扒谱。",
        "auth": "oauth2",
        "docs": [
            "https://developer.spotify.com/documentation/web-api",
            "https://developer.spotify.com/policy",
        ],
        "can_import": True,
    },
    "netease": {
        "display_name": "网易云音乐",
        "description": "暂无官方第三方接口，仅保留适配器。",
        "auth": "none",
        "docs": ["https://open.music.163.com/"],
        "can_import": False,
    },
    "qqmusic": {
        "display_name": "QQ 音乐",
        "description": "暂无官方第三方接口，仅保留适配器。",
        "auth": "none",
        "docs": ["https://open.y.qq.com/"],
        "can_import": False,
    },
}


def build_adapter(
    record: MusicSourceRecord,
    *,
    session: Optional[Session] = None,
    transport=None,
    config: Optional[Dict[str, Any]] = None,
) -> SourceAdapter:
    adapter_class = ADAPTERS.get(record.provider)
    if adapter_class is None:
        raise BadRequestError(f"unknown provider {record.provider!r}", code="UNKNOWN_PROVIDER")
    payload = dict(record.config or {}) if isinstance(record.config, dict) else {}
    if config:
        payload.update(config)
    kwargs: Dict[str, Any] = {}
    if transport is not None:
        kwargs["transport"] = transport
    adapter = adapter_class(record.id, payload, **kwargs)
    if isinstance(adapter, LocalSourceAdapter):
        adapter.session = session
    return adapter


def provider_list() -> list:
    items = []
    for provider, info in PROVIDER_INFO.items():
        adapter_class = ADAPTERS[provider]
        items.append(
            {
                "provider": provider,
                "display_name": info["display_name"],
                "description": info["description"],
                "auth": info["auth"],
                "docs": info["docs"],
                "can_import": info["can_import"],
                "capabilities": adapter_class.capabilities.as_dict(),
                "policy_note": provider_policy(provider),
            }
        )
    return items

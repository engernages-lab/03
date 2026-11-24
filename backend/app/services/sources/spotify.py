"""Spotify adapter - metadata only, AI processing is forbidden by policy.

Spotify Developer Policy forbids analysing Spotify Content and feeding it into
AI/ML models, and restricts integrating Spotify content with other services.
PocketScore therefore exposes metadata, user playlists, favourites and the
official playback control only, and the eligibility service hard-codes
``PROVIDER_RESTRICTED`` for every Spotify track.
"""

from __future__ import annotations

import base64
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import httpx

from app.core.config import get_settings
from app.core.errors import ProviderAuthError, ProviderError
from app.core.logging import get_logger
from app.services.sources.base import (
    ConnectionResult,
    PageResult,
    PlaylistDTO,
    SourceAdapter,
    SourceCapabilities,
    TrackDTO,
    provider_policy,
)

logger = get_logger("pocketscore.sources.spotify")

AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
API_BASE = "https://api.spotify.com/v1"
SCOPES = [
    "user-read-private",
    "user-read-email",
    "playlist-read-private",
    "playlist-read-collaborative",
    "user-library-read",
    "user-read-playback-state",
    "user-modify-playback-state",
]


class SpotifyAdapter(SourceAdapter):
    provider = "spotify"
    display_name = "Spotify"
    SCOPES = SCOPES
    capabilities = SourceCapabilities(
        metadata=True,
        playback=True,          # via Web Playback SDK / official controls
        audio_read=False,       # never
        ai_processing=False,    # policy: forbidden
        model_training=False,
        playlists=True,
        search=True,
        favorites=True,
        requires_auth=True,
        policy_note=provider_policy("spotify"),
    )

    def __init__(self, source_id: str, config: Optional[Dict[str, Any]] = None,
                 *, transport: Optional[httpx.AsyncBaseTransport] = None) -> None:
        super().__init__(source_id, config)
        settings = get_settings()
        self.client_id = self.config.get("client_id") or settings.spotify_client_id or ""
        self.client_secret = self.config.get("client_secret") or settings.spotify_client_secret or ""
        self.redirect_uri = self.config.get("redirect_uri") or settings.spotify_redirect_uri or ""
        self.access_token = self.config.get("access_token")
        self.refresh_token = self.config.get("refresh_token")
        self._transport = transport

    # -- OAuth -------------------------------------------------------------
    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret and self.redirect_uri)

    def authorize_url(self, state: str) -> str:
        if not self.is_configured():
            raise ProviderError(
                "Spotify 集成未配置（client_id / client_secret / redirect_uri）",
                code="PROVIDER_NOT_CONFIGURED",
                status_code=501,
            )
        query = urlencode(
            {
                "client_id": self.client_id,
                "response_type": "code",
                "redirect_uri": self.redirect_uri,
                "scope": " ".join(SCOPES),
                "state": state,
                "show_dialog": "false",
            }
        )
        return f"{AUTH_URL}?{query}"

    def _basic_auth(self) -> str:
        raw = f"{self.client_id}:{self.client_secret}".encode()
        return base64.b64encode(raw).decode()

    async def exchange_code(self, code: str) -> Dict[str, Any]:
        if not self.is_configured():
            raise ProviderError("Spotify 集成未配置", code="PROVIDER_NOT_CONFIGURED", status_code=501)
        async with httpx.AsyncClient(timeout=20, transport=self._transport) as client:
            response = await client.post(
                TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": self.redirect_uri,
                },
                headers={"Authorization": f"Basic {self._basic_auth()}"},
            )
        if response.status_code >= 400:
            raise ProviderAuthError(
                "Spotify 授权失败", details={"status": response.status_code, "body": response.text[:300]}
            )
        payload = response.json()
        self.access_token = payload.get("access_token")
        self.refresh_token = payload.get("refresh_token")
        return payload

    async def refresh_access_token(self) -> Optional[str]:
        if not self.refresh_token:
            return None
        async with httpx.AsyncClient(timeout=20, transport=self._transport) as client:
            response = await client.post(
                TOKEN_URL,
                data={"grant_type": "refresh_token", "refresh_token": self.refresh_token},
                headers={"Authorization": f"Basic {self._basic_auth()}"},
            )
        if response.status_code >= 400:
            raise ProviderAuthError("Spotify 令牌刷新失败")
        payload = response.json()
        self.access_token = payload.get("access_token")
        return self.access_token

    # -- API ---------------------------------------------------------------
    async def _get(self, path: str, **params: Any) -> Dict[str, Any]:
        if not self.access_token:
            raise ProviderAuthError("Spotify 未授权，请先连接账号")
        async with httpx.AsyncClient(timeout=20, transport=self._transport) as client:
            response = await client.get(
                f"{API_BASE}{path}",
                params=params or None,
                headers={"Authorization": f"Bearer {self.access_token}"},
            )
        if response.status_code == 401:
            if await self.refresh_access_token():
                return await self._get(path, **params)
            raise ProviderAuthError("Spotify 令牌已失效")
        if response.status_code == 403:
            raise ProviderError(
                "Spotify 拒绝该请求（可能需要 Premium）", code="PROVIDER_RESTRICTED", status_code=403
            )
        if response.status_code >= 400:
            raise ProviderError(
                f"Spotify 返回 HTTP {response.status_code}",
                details={"body": response.text[:300]},
            )
        return response.json()

    async def test_connection(self) -> ConnectionResult:
        if not self.is_configured():
            return ConnectionResult(
                ok=False,
                status="not_configured",
                message="缺少 Spotify 开发者凭据（client_id / client_secret / redirect_uri）",
            )
        if not self.access_token:
            return ConnectionResult(
                ok=False, status="needs_authorization", message="尚未完成 OAuth 授权"
            )
        try:
            profile = await self._get("/me")
        except (ProviderAuthError, ProviderError) as exc:
            return ConnectionResult(ok=False, status="error", message=str(exc))
        self.account_name = profile.get("display_name") or profile.get("id")
        return ConnectionResult(
            ok=True,
            status="connected",
            message="连接成功（仅元数据与官方播放控制）",
            account_name=self.account_name,
            details={"product": profile.get("product"), "country": profile.get("country")},
        )

    async def list_playlists(self) -> List[PlaylistDTO]:
        payload = await self._get("/me/playlists", limit=50)
        items = []
        for raw in payload.get("items") or []:
            images = raw.get("images") or []
            items.append(
                PlaylistDTO(
                    external_id=raw.get("id") or "",
                    name=raw.get("name") or "",
                    description=(raw.get("description") or "")[:500],
                    artwork=images[0].get("url") if images else None,
                    track_count=int((raw.get("tracks") or {}).get("total") or 0),
                    is_user_owned=bool(raw.get("owner", {}).get("id") == self.account_name),
                    metadata={"owner": (raw.get("owner") or {}).get("display_name")},
                )
            )
        return items

    async def get_playlist_tracks(
        self, playlist_id: str, limit: int = 100, offset: int = 0
    ) -> PageResult:
        payload = await self._get(f"/playlists/{playlist_id}/tracks", limit=min(limit, 100), offset=offset)
        items = []
        for entry in payload.get("items") or []:
            raw = (entry or {}).get("track") or {}
            if not raw.get("id"):
                continue
            items.append(self._to_dto(raw))
        return PageResult(items=items, total=int(payload.get("total") or len(items)), offset=offset, limit=limit)

    async def search(self, query: str, limit: int = 30) -> Dict[str, List[Any]]:
        payload = await self._get("/search", q=query, type="track,album,artist,playlist", limit=limit)
        return {
            "tracks": [self._to_dto(raw) for raw in (payload.get("tracks") or {}).get("items") or []],
            "albums": [],
            "artists": [],
            "playlists": [],
        }

    async def list_tracks(self, limit: int = 50, offset: int = 0, **_kwargs) -> PageResult:
        payload = await self._get("/me/tracks", limit=min(limit, 50), offset=offset)
        items = [self._to_dto((entry or {}).get("track") or {}) for entry in payload.get("items") or []]
        return PageResult(
            items=[i for i in items if i.external_id],
            total=int(payload.get("total") or len(items)),
            offset=offset,
            limit=limit,
        )

    async def get_stream(self, external_track_id: str) -> Optional[Dict[str, Any]]:
        # Playback happens inside the Web Playback SDK with the user's own token;
        # PocketScore never proxies or downloads Spotify audio.
        return {
            "mode": "provider_sdk",
            "provider": "spotify",
            "sdk": "web-playback-sdk",
            "reason": "Spotify 播放必须通过官方 SDK / 官方控制接口完成，本应用不代理音频流。",
        }

    def _to_dto(self, raw: Dict[str, Any]) -> TrackDTO:
        images = (raw.get("album") or {}).get("images") or []
        artists = ", ".join(a.get("name", "") for a in raw.get("artists") or [])
        return TrackDTO(
            external_id=raw.get("id") or "",
            title=raw.get("name") or "",
            artist=artists,
            album=(raw.get("album") or {}).get("name") or "",
            duration=float(raw.get("duration_ms") or 0) / 1000.0,
            artwork=images[0].get("url") if images else None,
            source_url=(raw.get("external_urls") or {}).get("spotify"),
            availability="metadata_only",
            metadata={
                "preview_url": raw.get("preview_url"),
                "isrc": (raw.get("external_ids") or {}).get("isrc"),
                "explicit": raw.get("explicit"),
            },
        )

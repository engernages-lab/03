"""Apple Music adapter.

Playback must go through MusicKit on the web with a developer token signed with
the user's MusicKit key.  PocketScore only mints that token server-side and
returns it to the browser; it never receives or stores Apple audio.
"""

from __future__ import annotations

import base64
import json
import os
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import httpx

from app.core.config import get_settings
from app.core.errors import DependencyMissingError, ProviderAuthError, ProviderError
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

logger = get_logger("pocketscore.sources.apple")

API_BASE = "https://api.music.apple.com/v1"
TOKEN_TTL_SECONDS = 180 * 24 * 3600  # Apple allows up to 6 months


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


class AppleMusicAdapter(SourceAdapter):
    provider = "apple_music"
    display_name = "Apple Music"
    capabilities = SourceCapabilities(
        metadata=True,
        playback=True,        # MusicKit on the web only
        audio_read=False,     # never; playback stream is DRM protected
        ai_processing=False,  # not because of playback access
        model_training=False,
        playlists=True,
        search=True,
        favorites=True,
        requires_auth=True,
        policy_note=provider_policy("apple_music"),
    )

    def __init__(self, source_id: str, config: Optional[Dict[str, Any]] = None,
                 *, transport: Optional[httpx.AsyncBaseTransport] = None) -> None:
        super().__init__(source_id, config)
        settings = get_settings()
        self.team_id = self.config.get("team_id") or settings.apple_music_team_id or ""
        self.key_id = self.config.get("key_id") or settings.apple_music_key_id or ""
        self.private_key_path = (
            self.config.get("private_key_path") or settings.apple_music_private_key_path or ""
        )
        self.storefront = self.config.get("storefront") or settings.apple_music_storefront or "us"
        self.music_user_token = self.config.get("music_user_token")
        self._transport = transport
        self._cached_token: Optional[str] = None
        self._cached_expiry: float = 0.0

    # -- developer token ---------------------------------------------------
    def is_configured(self) -> bool:
        return bool(self.team_id and self.key_id and self.private_key_path)

    def _load_private_key(self) -> str:
        if not self.private_key_path:
            raise ProviderError(
                "Apple Music 私钥未配置（POCKETSCORE_APPLE_MUSIC_PRIVATE_KEY_PATH）",
                code="PROVIDER_NOT_CONFIGURED",
                status_code=501,
            )
        if not os.path.exists(self.private_key_path):
            raise ProviderError(
                f"私钥文件不存在：{self.private_key_path}", code="PROVIDER_NOT_CONFIGURED", status_code=501
            )
        with open(self.private_key_path, "r", encoding="utf-8") as handle:
            return handle.read()

    def developer_token(self) -> str:
        """Mint (and cache) the ES256 developer token required by MusicKit."""
        now = time.time()
        if self._cached_token and now < self._cached_expiry - 60:
            return self._cached_token

        if not self.is_configured():
            raise ProviderError(
                "Apple Music 集成未配置（team_id / key_id / private_key_path）",
                code="PROVIDER_NOT_CONFIGURED",
                status_code=501,
            )
        try:
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import ec
            from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
        except ImportError as exc:  # pragma: no cover - dependency is installed
            raise DependencyMissingError(
                "generating an Apple Music developer token requires 'cryptography'"
            ) from exc

        header = {"alg": "ES256", "kid": self.key_id, "typ": "JWT"}
        issued = int(now)
        payload = {"iss": self.team_id, "iat": issued, "exp": issued + TOKEN_TTL_SECONDS}
        signing_input = f"{_b64url(json.dumps(header, separators=(',', ':')).encode())}." \
                        f"{_b64url(json.dumps(payload, separators=(',', ':')).encode())}"

        private_key = serialization.load_pem_private_key(
            self._load_private_key().encode(), password=None
        )
        if not isinstance(private_key, ec.EllipticCurvePrivateKey):
            raise ProviderError("Apple Music 私钥必须是 EC P-256 密钥", code="PROVIDER_NOT_CONFIGURED")
        der_signature = private_key.sign(signing_input.encode(), ec.ECDSA(hashes.SHA256()))
        r, s = decode_dss_signature(der_signature)
        raw_signature = r.to_bytes(32, "big") + s.to_bytes(32, "big")

        token = f"{signing_input}.{_b64url(raw_signature)}"
        self._cached_token = token
        self._cached_expiry = issued + TOKEN_TTL_SECONDS
        return token

    # -- API ---------------------------------------------------------------
    async def _get(self, path: str, **params: Any) -> Dict[str, Any]:
        token = self.developer_token()
        headers = {"Authorization": f"Bearer {token}"}
        if self.music_user_token:
            headers["Music-User-Token"] = self.music_user_token
        async with httpx.AsyncClient(timeout=20, transport=self._transport) as client:
            response = await client.get(f"{API_BASE}{path}", params=params or None, headers=headers)
        if response.status_code == 401:
            raise ProviderAuthError("Apple Music 拒绝了开发者令牌")
        if response.status_code == 403:
            raise ProviderError(
                "Apple Music 拒绝该请求（需要有效的 Music-User-Token）",
                code="PROVIDER_RESTRICTED", status_code=403,
            )
        if response.status_code >= 400:
            raise ProviderError(
                f"Apple Music 返回 HTTP {response.status_code}",
                details={"body": response.text[:300]},
            )
        return response.json()

    async def test_connection(self) -> ConnectionResult:
        if not self.is_configured():
            return ConnectionResult(
                ok=False,
                status="not_configured",
                message="缺少 Apple Music 配置（team_id / key_id / .p8 私钥路径）",
            )
        try:
            self.developer_token()
        except (ProviderError, DependencyMissingError) as exc:
            return ConnectionResult(ok=False, status="error", message=str(exc))

        if not self.music_user_token:
            return ConnectionResult(
                ok=False,
                status="needs_authorization",
                message="开发者令牌可用，但尚未获得用户授权（MusicKit 授权后需要 Music-User-Token）",
                details={"developer_token": "ok"},
            )
        try:
            await self._get("/me/library/playlists", limit=1)
        except (ProviderAuthError, ProviderError) as exc:
            return ConnectionResult(ok=False, status="error", message=str(exc))
        return ConnectionResult(
            ok=True,
            status="connected",
            message="连接成功（MusicKit 官方授权）",
            account_name="Apple Music 用户",
            details={"storefront": self.storefront},
        )

    async def list_playlists(self) -> List[PlaylistDTO]:
        payload = await self._get("/me/library/playlists", limit=50)
        items = []
        for raw in payload.get("data") or []:
            attributes = raw.get("attributes") or {}
            items.append(
                PlaylistDTO(
                    external_id=raw.get("id") or "",
                    name=attributes.get("name") or "",
                    description=(attributes.get("description") or {}).get("standard") or "",
                    track_count=int((attributes.get("trackCount") or 0)),
                    is_user_owned=True,
                    metadata={"canEdit": attributes.get("canEdit")},
                )
            )
        return items

    async def get_playlist_tracks(
        self, playlist_id: str, limit: int = 100, offset: int = 0
    ) -> PageResult:
        payload = await self._get(f"/me/library/playlists/{playlist_id}/tracks", limit=min(limit, 100), offset=offset)
        items = [self._to_dto(raw) for raw in payload.get("data") or []]
        return PageResult(items=items, total=int(payload.get("meta", {}).get("total") or len(items)),
                          offset=offset, limit=limit)

    async def search(self, query: str, limit: int = 30) -> Dict[str, List[Any]]:
        payload = await self._get(
            f"/catalog/{self.storefront}/search", term=query, types="songs,albums,artists", limit=limit
        )
        results = (payload.get("results") or {})
        songs = (results.get("songs") or {}).get("data") or []
        return {"tracks": [self._to_dto(raw) for raw in songs], "albums": [], "artists": [], "playlists": []}

    async def list_tracks(self, limit: int = 50, offset: int = 0, **_kwargs) -> PageResult:
        payload = await self._get("/me/library/songs", limit=min(limit, 100), offset=offset)
        items = [self._to_dto(raw) for raw in payload.get("data") or []]
        return PageResult(items=items, total=int(payload.get("meta", {}).get("total") or len(items)),
                          offset=offset, limit=limit)

    async def get_stream(self, external_track_id: str) -> Optional[Dict[str, Any]]:
        return {
            "mode": "provider_sdk",
            "provider": "apple_music",
            "sdk": "musickit-js",
            "developer_token": self.developer_token(),
            "storefront": self.storefront,
            "reason": "Apple Music 播放必须通过 MusicKit 完成，本应用不代理或下载音频流。",
        }

    def _to_dto(self, raw: Dict[str, Any]) -> TrackDTO:
        attributes = raw.get("attributes") or {}
        artwork = attributes.get("artwork") or {}
        artwork_url = None
        if artwork.get("url"):
            artwork_url = artwork["url"].replace("{w}", "600").replace("{h}", "600")
        return TrackDTO(
            external_id=raw.get("id") or "",
            title=attributes.get("name") or "",
            artist=attributes.get("artistName") or "",
            album=attributes.get("albumName") or "",
            duration=float(attributes.get("durationInMillis") or 0) / 1000.0,
            artwork=artwork_url,
            source_url=attributes.get("url"),
            availability="streamable",
            metadata={"isrc": attributes.get("isrc"), "genre": (attributes.get("genreNames") or [None])[0]},
        )

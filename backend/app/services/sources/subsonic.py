"""Navidrome / OpenSubsonic adapter.

Implements the official OpenSubsonic JSON API (``ping``, ``getAlbumList2``,
``search3``, ``getPlaylists``, ``getPlaylist``, ``stream``).  Features that a
server does not advertise are reported as unavailable instead of assumed.
"""

from __future__ import annotations

import hashlib
import secrets
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import httpx

from app.core.errors import ProviderAuthError, ProviderError, ProviderUnavailableError
from app.core.logging import get_logger
from app.services.sources.base import (
    AlbumDTO,
    ArtistDTO,
    ConnectionResult,
    PageResult,
    PlaylistDTO,
    SourceAdapter,
    SourceCapabilities,
    TrackDTO,
    provider_policy,
)

logger = get_logger("pocketscore.sources.subsonic")

API_VERSION = "1.16.1"
CLIENT_NAME = "PocketScore"
TIMEOUT = 20.0


class SubsonicAdapter(SourceAdapter):
    provider = "subsonic"
    display_name = "Navidrome / OpenSubsonic"
    capabilities = SourceCapabilities(
        metadata=True,
        playback=True,
        audio_read=True,       # user's own server; content rights still user's
        ai_processing=False,   # decided per-track by the eligibility service
        model_training=False,
        playlists=True,
        search=True,
        favorites=True,
        requires_auth=True,
        policy_note=provider_policy("subsonic"),
    )

    def __init__(self, source_id: str, config: Optional[Dict[str, Any]] = None,
                 *, transport: Optional[httpx.AsyncBaseTransport] = None) -> None:
        super().__init__(source_id, config)
        self.base_url = (self.config.get("base_url") or "").rstrip("/")
        self.username = self.config.get("username") or ""
        self._password = self.config.get("password") or ""
        self._token = self.config.get("token")
        self._salt = self.config.get("salt")
        self._transport = transport
        self.server_type = self.config.get("server_type") or "navidrome"

    # -- auth --------------------------------------------------------------
    def _auth_params(self) -> Dict[str, str]:
        params = {"u": self.username, "v": API_VERSION, "c": CLIENT_NAME, "f": "json"}
        if self._token and self._salt:
            params.update({"t": self._token, "s": self._salt})
        elif self._password:
            salt = secrets.token_hex(6)
            token = hashlib.md5((self._password + salt).encode("utf-8")).hexdigest()
            params.update({"t": token, "s": salt})
        return params

    def auth_signature(self) -> Dict[str, str]:
        """Credentials to persist (token+salt, never the plain password)."""
        if self._token and self._salt:
            return {"token": self._token, "salt": self._salt}
        salt = secrets.token_hex(6)
        token = hashlib.md5((self._password + salt).encode("utf-8")).hexdigest()
        return {"token": token, "salt": salt}

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            timeout=TIMEOUT,
            follow_redirects=False,
            transport=self._transport,
            headers={"User-Agent": "PocketScore/1.0"},
        )

    async def _call(self, endpoint: str, **params: Any) -> Dict[str, Any]:
        if not self.base_url:
            raise ProviderUnavailableError(
                "server URL is not configured", code="SOURCE_NOT_CONFIGURED"
            )
        query = {**self._auth_params(), **{k: v for k, v in params.items() if v is not None}}
        url = f"/rest/{endpoint}"
        try:
            async with self._client() as client:
                response = await client.get(url, params=query)
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(
                f"could not reach the server: {exc}", details={"base_url": self.base_url}
            ) from exc

        if response.status_code in (401, 403):
            raise ProviderAuthError(
                "the server rejected the credentials", code="PROVIDER_AUTH_FAILED"
            )
        if response.status_code >= 400:
            raise ProviderError(
                f"server returned HTTP {response.status_code}", details={"endpoint": endpoint}
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderError(
                "server did not return JSON (is this an OpenSubsonic server?)",
                details={"endpoint": endpoint},
            ) from exc

        body = payload.get("subsonic-response") or payload.get("subsonicResponse") or {}
        if str(body.get("status", "")).lower() == "failed":
            error = body.get("error") or {}
            code = error.get("code")
            message = error.get("message") or "server reported a failure"
            if code in (40, 41, 44):
                raise ProviderAuthError(message, code="PROVIDER_AUTH_FAILED")
            raise ProviderError(message, details={"subsonic_code": code})
        return body

    # -- lifecycle ---------------------------------------------------------
    async def test_connection(self) -> ConnectionResult:
        try:
            body = await self._call("ping.view")
        except (ProviderAuthError, ProviderError, ProviderUnavailableError) as exc:
            return ConnectionResult(ok=False, status="error", message=str(exc))
        version = body.get("version") or "unknown"
        open_subsonic = bool(body.get("openSubsonic"))
        self.server_type = "opensubsonic" if open_subsonic else "subsonic"
        return ConnectionResult(
            ok=True,
            status="connected",
            message="连接成功",
            server_version=str(version),
            account_name=self.username,
            details={
                "open_subsonic": open_subsonic,
                "type": body.get("type"),
                "serverVersion": body.get("serverVersion"),
            },
        )

    # -- library -----------------------------------------------------------
    async def list_albums(self, limit: int = 50, offset: int = 0) -> PageResult:
        body = await self._call(
            "getAlbumList2.view", type="alphabeticalByArtist", size=limit, offset=offset
        )
        albums = (body.get("albumList2") or {}).get("album") or []
        items = [self._album_dto(raw) for raw in albums]
        return PageResult(items=items, total=len(items), offset=offset, limit=limit)

    async def list_artists(self, limit: int = 50, offset: int = 0) -> PageResult:
        body = await self._call("getArtists.view")
        indexes = (body.get("artists") or {}).get("index") or []
        artists: List[ArtistDTO] = []
        for index in indexes:
            for raw in index.get("artist") or []:
                artists.append(
                    ArtistDTO(
                        external_id=str(raw.get("id")),
                        name=raw.get("name") or "",
                        artwork=raw.get("artistImageUrl"),
                        album_count=int(raw.get("albumCount") or 0),
                        metadata=raw,
                    )
                )
        window = artists[offset : offset + limit]
        return PageResult(items=window, total=len(artists), offset=offset, limit=limit)

    async def list_playlists(self) -> List[PlaylistDTO]:
        body = await self._call("getPlaylists.view")
        playlists = (body.get("playlists") or {}).get("playlist") or []
        return [
            PlaylistDTO(
                external_id=str(raw.get("id")),
                name=raw.get("name") or "",
                description=raw.get("comment") or "",
                artwork=raw.get("coverArt") and f"/rest/getCoverArt.view?id={raw.get('coverArt')}",
                track_count=int(raw.get("songCount") or 0),
                is_user_owned=bool(raw.get("owner") == self.username) if self.username else True,
                metadata=raw,
            )
            for raw in playlists
        ]

    async def get_playlist_tracks(
        self, playlist_id: str, limit: int = 100, offset: int = 0
    ) -> PageResult:
        body = await self._call("getPlaylist.view", id=playlist_id)
        songs = (body.get("playlist") or {}).get("entry") or []
        items = [self._track_dto(raw) for raw in songs]
        window = items[offset : offset + limit]
        return PageResult(items=window, total=len(items), offset=offset, limit=limit)

    async def search(self, query: str, limit: int = 30) -> Dict[str, List[Any]]:
        body = await self._call(
            "search3.view", query=query, artistCount=limit, albumCount=limit,
            songCount=limit, playlistCount=limit,
        )
        result = body.get("searchResult3") or {}
        return {
            "tracks": [self._track_dto(raw) for raw in result.get("song") or []],
            "albums": [self._album_dto(raw) for raw in result.get("album") or []],
            "artists": [
                ArtistDTO(
                    external_id=str(raw.get("id")),
                    name=raw.get("name") or "",
                    album_count=int(raw.get("albumCount") or 0),
                    metadata=raw,
                )
                for raw in result.get("artist") or []
            ],
            "playlists": [],
        }

    async def list_tracks(self, limit: int = 50, offset: int = 0, **_kwargs) -> PageResult:
        # OpenSubsonic has no global "all songs" endpoint; use a random sample.
        body = await self._call("getRandomSongs.view", size=limit)
        songs = (body.get("randomSongs") or {}).get("song") or []
        items = [self._track_dto(raw) for raw in songs]
        return PageResult(items=items, total=len(items), offset=offset, limit=limit)

    # -- playback ----------------------------------------------------------
    async def get_stream(self, external_track_id: str) -> Optional[Dict[str, Any]]:
        query = urlencode({**self._auth_params(), "id": external_track_id, "format": "raw"})
        return {
            "mode": "proxy",
            "provider": self.provider,
            "proxy_url": f"/api/v1/playback/proxy/{self.source_id}/{external_track_id}",
            "upstream": f"{self.base_url}/rest/stream.view?{query}",
        }

    async def fetch_stream_bytes(self, external_track_id: str):
        query = {**self._auth_params(), "id": external_track_id}
        async with (
            self._client() as client,
            client.stream("GET", "/rest/stream.view", params=query) as response,
        ):
            if response.status_code in (401, 403):
                raise ProviderAuthError("stream was rejected by the server")
            if response.status_code >= 400:
                raise ProviderError(f"server returned HTTP {response.status_code}")
            async for chunk in response.aiter_bytes(64 * 1024):
                yield chunk

    # -- mapping -----------------------------------------------------------
    def _track_dto(self, raw: Dict[str, Any]) -> TrackDTO:
        duration = raw.get("duration")
        return TrackDTO(
            external_id=str(raw.get("id")),
            title=raw.get("title") or raw.get("name") or "(未命名)",
            artist=raw.get("artist") or "",
            album=raw.get("album") or "",
            duration=float(duration) if duration else 0.0,
            artwork=(
                f"{self.base_url}/rest/getCoverArt.view?"
                f"{urlencode({**self._auth_params(), 'id': raw.get('coverArt')})}"
            ) if raw.get("coverArt") else None,
            source_url=f"{self.base_url}/app/#/album/{raw.get('albumId')}" if raw.get("albumId") else None,
            availability="streamable",
            metadata={
                "suffix": raw.get("suffix"),
                "contentType": raw.get("contentType"),
                "bitRate": raw.get("bitRate"),
                "size": raw.get("size"),
                "track": raw.get("track"),
                "discNumber": raw.get("discNumber"),
                "isrc": (raw.get("isrc") or [None])[0] if isinstance(raw.get("isrc"), list) else raw.get("isrc"),
            },
            stream_url=f"/api/v1/playback/proxy/{self.source_id}/{raw.get('id')}",
        )

    def _album_dto(self, raw: Dict[str, Any]) -> AlbumDTO:
        return AlbumDTO(
            external_id=str(raw.get("id")),
            title=raw.get("name") or raw.get("title") or "",
            artist=raw.get("artist") or "",
            year=raw.get("year"),
            artwork=raw.get("coverArt"),
            track_count=int(raw.get("songCount") or 0),
            metadata=raw,
        )

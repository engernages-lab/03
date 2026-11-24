"""OpenSubsonic adapter tests using httpx.MockTransport (no network)."""

from __future__ import annotations

import hashlib

import httpx
import pytest

from app.core.errors import ProviderAuthError, ProviderError, ProviderUnavailableError
from app.services.sources.subsonic import SubsonicAdapter

BASE = "http://music.example.lan:4533"


def make_adapter(handler, *, password: str = "secret") -> SubsonicAdapter:
    transport = httpx.MockTransport(handler)
    return SubsonicAdapter(
        "src_test",
        {"base_url": BASE, "username": "alice", "password": password},
        transport=transport,
    )


def ping_ok(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "subsonic-response": {
                "status": "ok",
                "version": "1.16.1",
                "openSubsonic": True,
                "type": "navidrome",
                "serverVersion": "0.50.1",
            }
        },
    )


@pytest.mark.asyncio
async def test_test_connection_reports_version_and_type():
    adapter = make_adapter(ping_ok)
    result = await adapter.test_connection()
    assert result.ok is True
    assert result.status == "connected"
    assert result.server_version == "1.16.1"
    assert result.details["open_subsonic"] is True
    assert adapter.server_type == "opensubsonic"


@pytest.mark.asyncio
async def test_auth_params_use_hashed_token():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(dict(request.url.params))
        return ping_ok(request)

    adapter = make_adapter(handler, password="secret")
    await adapter.test_connection()
    assert captured["u"] == "alice"
    assert captured["v"] == "1.16.1"
    assert captured["c"] == "PocketScore"
    assert captured["f"] == "json"
    assert captured["s"] and captured["t"]
    # md5(password + salt) is the documented Subsonic token scheme
    assert captured["t"] == hashlib.md5(("secret" + captured["s"]).encode()).hexdigest()
    assert "p" not in captured  # never send the plain password


@pytest.mark.asyncio
async def test_failed_status_raises_auth_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "subsonic-response": {
                    "status": "failed",
                    "error": {"code": 40, "message": "Wrong username or password"},
                }
            },
        )

    adapter = make_adapter(handler)
    result = await adapter.test_connection()
    assert result.ok is False
    assert result.status == "error"
    assert "password" in result.message.lower() or "rejected" in result.message.lower()


@pytest.mark.asyncio
async def test_http_401_raises_auth_error():
    adapter = make_adapter(lambda request: httpx.Response(401, json={}))
    with pytest.raises(ProviderAuthError):
        await adapter._call("ping.view")


@pytest.mark.asyncio
async def test_unreachable_server_raises_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    adapter = make_adapter(handler)
    with pytest.raises(ProviderUnavailableError):
        await adapter._call("ping.view")


@pytest.mark.asyncio
async def test_non_json_response_raises_provider_error():
    adapter = make_adapter(lambda request: httpx.Response(200, text="<html>not subsonic</html>"))
    with pytest.raises(ProviderError):
        await adapter._call("ping.view")


@pytest.mark.asyncio
async def test_list_albums_maps_fields():
    def handler(request: httpx.Request) -> httpx.Response:
        if "getAlbumList2" in request.url.path:
            return httpx.Response(
                200,
                json={
                    "subsonic-response": {
                        "status": "ok",
                        "albumList2": {
                            "album": [
                                {
                                    "id": "al-1",
                                    "name": "月光",
                                    "artist": "德彪西",
                                    "year": 1905,
                                    "songCount": 4,
                                    "coverArt": "al-1",
                                }
                            ]
                        },
                    }
                },
            )
        return ping_ok(request)

    adapter = make_adapter(handler)
    page = await adapter.list_albums(limit=10)
    assert page.total == 1
    album = page.items[0]
    assert album.external_id == "al-1"
    assert album.title == "月光"
    assert album.artist == "德彪西"
    assert album.year == 1905
    assert album.track_count == 4


@pytest.mark.asyncio
async def test_search_maps_tracks_albums_artists():
    def handler(request: httpx.Request) -> httpx.Response:
        if "search3" in request.url.path:
            return httpx.Response(
                200,
                json={
                    "subsonic-response": {
                        "status": "ok",
                        "searchResult3": {
                            "song": [
                                {
                                    "id": "s-1",
                                    "title": "Clair de Lune",
                                    "artist": "Debussy",
                                    "album": "Suite bergamasque",
                                    "duration": 300,
                                    "suffix": "flac",
                                    "coverArt": "al-1",
                                }
                            ],
                            "album": [{"id": "al-1", "name": "Suite bergamasque", "artist": "Debussy"}],
                            "artist": [{"id": "ar-1", "name": "Debussy", "albumCount": 3}],
                        },
                    }
                },
            )
        return ping_ok(request)

    adapter = make_adapter(handler)
    results = await adapter.search("debussy")
    assert len(results["tracks"]) == 1
    track = results["tracks"][0]
    assert track.title == "Clair de Lune"
    assert track.duration == 300.0
    assert track.availability == "streamable"
    assert track.stream_url.endswith("/api/v1/playback/proxy/src_test/s-1")
    assert len(results["albums"]) == 1
    assert results["artists"][0].album_count == 3


@pytest.mark.asyncio
async def test_playlist_tracks():
    def handler(request: httpx.Request) -> httpx.Response:
        if "getPlaylist.view" in request.url.path:
            return httpx.Response(
                200,
                json={
                    "subsonic-response": {
                        "status": "ok",
                        "playlist": {
                            "id": "pl-1",
                            "name": "夜间练习",
                            "entry": [
                                {"id": "s-1", "title": "A", "duration": 100},
                                {"id": "s-2", "title": "B", "duration": 120},
                            ],
                        },
                    }
                },
            )
        if "getPlaylists" in request.url.path:
            return httpx.Response(
                200,
                json={
                    "subsonic-response": {
                        "status": "ok",
                        "playlists": {"playlist": [{"id": "pl-1", "name": "夜间练习", "songCount": 2}]},
                    }
                },
            )
        return ping_ok(request)

    adapter = make_adapter(handler)
    playlists = await adapter.list_playlists()
    assert playlists[0].name == "夜间练习"
    page = await adapter.get_playlist_tracks("pl-1")
    assert page.total == 2
    assert [t.title for t in page.items] == ["A", "B"]


@pytest.mark.asyncio
async def test_stream_returns_proxy_info():
    adapter = make_adapter(ping_ok)
    info = await adapter.get_stream("s-1")
    assert info["mode"] == "proxy"
    assert "/api/v1/playback/proxy/src_test/s-1" in info["proxy_url"]
    assert "stream.view" in info["upstream"]


@pytest.mark.asyncio
async def test_capabilities_declare_audio_access_but_not_ai():
    adapter = make_subsonic_without_network()
    caps = adapter.capability_report()
    assert caps["metadata"] is True
    assert caps["playback"] is True
    assert caps["audio_read"] is True
    assert caps["ai_processing"] is False
    assert caps["model_training"] is False


def make_subsonic_without_network() -> SubsonicAdapter:
    return SubsonicAdapter("src_x", {"base_url": BASE, "username": "u", "password": "p"})

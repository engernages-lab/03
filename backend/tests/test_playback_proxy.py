"""Playback proxy tests: real Range relay and provider-safe behaviour."""

from __future__ import annotations

import uuid

import httpx
import pytest

from app.core.errors import ProviderAuthError
from app.services import library
from app.services.sources.subsonic import SubsonicAdapter

BASE = "http://music.example.lan:4533"


def make_adapter(handler) -> SubsonicAdapter:
    return SubsonicAdapter(
        "src_proxy",
        {"base_url": BASE, "username": "alice", "password": "secret"},
        transport=httpx.MockTransport(handler),
    )


@pytest.mark.asyncio
async def test_open_stream_forwards_range_and_reports_206():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["range"] = request.headers.get("range")
        captured["path"] = request.url.path
        return httpx.Response(
            206,
            content=b"a" * 100,
            headers={
                "content-type": "audio/flac",
                "content-range": "bytes 0-99/1000",
                "content-length": "100",
                "accept-ranges": "bytes",
            },
        )

    adapter = make_adapter(handler)
    meta, iterator = await adapter.open_stream("s-1", "bytes=0-99")
    body = b"".join([chunk async for chunk in iterator])

    assert captured["range"] == "bytes=0-99"
    assert captured["path"].endswith("/rest/stream.view")
    assert meta["status"] == 206
    assert meta["content_range"] == "bytes 0-99/1000"
    assert meta["content_type"] == "audio/flac"
    assert len(body) == 100


@pytest.mark.asyncio
async def test_open_stream_without_range_is_200():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("range") is None
        return httpx.Response(200, content=b"full", headers={"content-type": "audio/mpeg"})

    adapter = make_adapter(handler)
    meta, iterator = await adapter.open_stream("s-1")
    body = b"".join([chunk async for chunk in iterator])
    assert meta["status"] == 200
    assert body == b"full"


@pytest.mark.asyncio
async def test_open_stream_maps_auth_failure():
    adapter = make_adapter(lambda request: httpx.Response(401))
    with pytest.raises(ProviderAuthError):
        await adapter.open_stream("s-1")


def test_api_proxy_relays_partial_content(client, db_session, monkeypatch):
    source = library.create_source(
        db_session,
        provider="subsonic",
        display_name=f"sub-{uuid.uuid4().hex[:6]}",
        config={"base_url": BASE, "username": "alice", "token": "t", "salt": "s"},
    )
    adapter = make_adapter(
        lambda request: httpx.Response(
            206,
            content=b"b" * 64,
            headers={
                "content-type": "audio/flac",
                "content-range": "bytes 0-63/4096",
                "content-length": "64",
                "accept-ranges": "bytes",
            },
        )
    )
    monkeypatch.setattr(
        "app.services.sources.registry.build_adapter",
        lambda record, **kwargs: adapter,
    )

    response = client.get(
        f"/api/v1/playback/proxy/{source.id}/s-1", headers={"Range": "bytes=0-63"}
    )
    assert response.status_code == 206
    assert response.headers["content-range"] == "bytes 0-63/4096"
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["content-type"].startswith("audio/flac")
    assert len(response.content) == 64


def test_api_proxy_maps_upstream_auth_error(client, db_session, monkeypatch):
    source = library.create_source(
        db_session,
        provider="subsonic",
        display_name=f"sub-{uuid.uuid4().hex[:6]}",
        config={"base_url": BASE, "username": "alice", "token": "t", "salt": "s"},
    )
    adapter = make_adapter(lambda request: httpx.Response(401))
    monkeypatch.setattr(
        "app.services.sources.registry.build_adapter",
        lambda record, **kwargs: adapter,
    )
    response = client.get(f"/api/v1/playback/proxy/{source.id}/s-1")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "PROVIDER_AUTH_FAILED"

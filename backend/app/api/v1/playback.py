"""Playback: stream resolution, provider-safe proxying, history."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import AppError, ValidationAppError
from app.services import library
from app.services.sources import registry

router = APIRouter()


@router.get("/stream/{track_id}")
async def stream_info(track_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Resolve how a track may be played (never bypasses provider permissions)."""
    track = library.get_track(db, track_id)
    source = library.get_source(db, track.source_id)
    adapter = registry.build_adapter(source, session=db)
    info = await adapter.get_stream(track.external_track_id) if adapter.capabilities.playback else None

    if info is None:
        if track.stream_url:
            info = {"mode": "direct", "url": track.stream_url, "provider": source.provider}
        else:
            raise AppError(
                "该曲目没有可用的播放方式",
                code="PLAYBACK_UNAVAILABLE",
                status_code=409,
                details={"provider": source.provider, "track_id": track_id},
            )

    return {
        "track_id": track_id,
        "provider": source.provider,
        "mode": info.get("mode"),
        "url": info.get("url") or info.get("proxy_url"),
        "info": info,
        "title": track.title,
        "duration": track.duration,
    }


@router.get("/proxy/{source_id}/{external_id}")
async def proxy_stream(
    source_id: str,
    external_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """Server-side proxy for providers that require authenticated streaming.

    Only providers whose adapter exposes ``fetch_stream_bytes`` are proxied;
    providers with policy restrictions (Spotify) never reach this path.
    """
    source = library.get_source(db, source_id)
    adapter = registry.build_adapter(source, session=db)
    if source.provider == "spotify":
        raise AppError(
            "Spotify 音频不得通过本应用代理",
            code="PROVIDER_RESTRICTED",
            status_code=403,
        )
    if not hasattr(adapter, "fetch_stream_bytes"):
        raise ValidationAppError(
            "this provider cannot be proxied", code="PLAYBACK_UNAVAILABLE", status_code=409
        )

    range_header = request.headers.get("range")

    async def generator():
        async for chunk in adapter.fetch_stream_bytes(external_id):
            yield chunk

    headers = {"Accept-Ranges": "bytes"}
    if range_header:
        # Upstream range handling differs per server; we pass the request through
        # and let the client re-request if the server ignores it.
        headers["X-Proxy-Range-Passthrough"] = range_header
    return StreamingResponse(
        generator(), media_type="audio/mpeg", headers=headers
    )

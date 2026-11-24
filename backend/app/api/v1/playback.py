"""Playback: stream resolution, provider-safe proxying with Range relay.

The proxy never bypasses provider permissions: Spotify is rejected outright,
and providers without a byte-stream capability cannot be proxied at all.
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import AppError, ProviderError, ProviderUnavailableError, ValidationAppError
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
    """Authenticated byte proxy that relays upstream status and Range headers."""
    source = library.get_source(db, source_id)
    adapter = registry.build_adapter(source, session=db)
    if source.provider == "spotify":
        raise AppError(
            "Spotify 音频不得通过本应用代理",
            code="PROVIDER_RESTRICTED",
            status_code=403,
        )
    if not hasattr(adapter, "open_stream"):
        raise ValidationAppError(
            "this provider cannot be proxied", code="PLAYBACK_UNAVAILABLE", status_code=409
        )

    range_header = request.headers.get("range")
    try:
        meta, iterator = await adapter.open_stream(external_id, range_header)
    except ProviderError:
        raise
    except Exception as exc:  # pragma: no cover - defensive
        raise ProviderUnavailableError(f"upstream stream failed: {exc}") from exc

    headers = {"Accept-Ranges": meta.get("accept_ranges") or "bytes"}
    if meta.get("content_range"):
        headers["Content-Range"] = meta["content_range"]
    if meta.get("content_length"):
        headers["Content-Length"] = meta["content_length"]

    return StreamingResponse(
        iterator,
        status_code=int(meta.get("status") or 200),
        media_type=meta.get("content_type") or "audio/mpeg",
        headers=headers,
    )

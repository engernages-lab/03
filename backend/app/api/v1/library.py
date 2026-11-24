"""Unified music library endpoints: tracks, uploads, playlists, favourites."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.source import MusicSourceRecord, UnifiedTrackRecord
from app.schemas.common import Page
from app.services import library
from app.services.audio import assets as audio_assets

router = APIRouter()


class TrackOut(BaseModel):
    track_id: str
    source_id: str
    source_provider: str
    external_track_id: str
    title: str
    artist: str
    album: str
    duration: float
    artwork: Optional[str]
    source_url: Optional[str]
    availability: str
    metadata: Dict[str, Any]
    canonical_group_id: Optional[str]
    stream_url: Optional[str]
    is_local: bool
    play_count: int
    is_favorite: bool = False


class PlaylistCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=1000)


class HistoryCreate(BaseModel):
    track_id: str
    position: float = Field(default=0.0, ge=0.0)
    completed: bool = False


def _track_out(session: Session, record) -> TrackOut:
    source = session.get(MusicSourceRecord, record.source_id)
    return TrackOut(
        track_id=record.id,
        source_id=record.source_id,
        source_provider=source.provider if source else "unknown",
        external_track_id=record.external_track_id,
        title=record.title,
        artist=record.artist,
        album=record.album,
        duration=record.duration,
        artwork=record.artwork,
        source_url=record.source_url,
        availability=record.availability,
        metadata=json.loads(record.metadata_json) if record.metadata_json else {},
        canonical_group_id=record.canonical_group_id,
        stream_url=record.stream_url,
        is_local=record.is_local,
        play_count=record.play_count,
        is_favorite=library.is_favorite(session, record.id),
    )


@router.get("/tracks", response_model=Page[TrackOut])
def list_tracks(
    q: Optional[str] = Query(default=None, max_length=200),
    source_id: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> Page[TrackOut]:
    rows, total = library.list_tracks(db, query=q, source_id=source_id, limit=limit, offset=offset)
    return Page(items=[_track_out(db, r) for r in rows], total=total, limit=limit, offset=offset)


@router.get("/tracks/{track_id}", response_model=TrackOut)
def get_track(track_id: str, db: Session = Depends(get_db)) -> TrackOut:
    return _track_out(db, library.get_track(db, track_id))


@router.post("/import", response_model=TrackOut, status_code=status.HTTP_201_CREATED)
async def import_local_audio(
    file: UploadFile = File(...),
    title: Optional[str] = Form(default=None),
    artist: Optional[str] = Form(default=None),
    db: Session = Depends(get_db),
) -> TrackOut:
    """Upload an audio file into the local library (explicit user action only)."""
    data = await file.read()
    asset, _created = audio_assets.ingest_audio(
        db, data, file.filename or "upload.bin", title=title, artist=artist
    )
    track = library.register_local_asset(db, asset)
    return _track_out(db, track)


@router.get("/stats")
def stats(db: Session = Depends(get_db)) -> Dict[str, Any]:
    library.ensure_local_source(db)
    return library.library_stats(db)


@router.get("/albums")
def albums(limit: int = Query(default=100, ge=1, le=200), db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Album view derived from the unified track index."""
    rows = list(db.execute(select(UnifiedTrackRecord)).scalars())
    buckets: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        key = f"{row.artist}||{row.album}"
        bucket = buckets.setdefault(
            key,
            {
                "album": row.album or "未知专辑",
                "artist": row.artist or "未知艺人",
                "artwork": row.artwork,
                "track_count": 0,
                "duration": 0.0,
                "source_ids": set(),
            },
        )
        bucket["track_count"] += 1
        bucket["duration"] += row.duration or 0.0
        bucket["source_ids"].add(row.source_id)
        bucket["artwork"] = bucket["artwork"] or row.artwork
    items = [
        {**value, "source_ids": sorted(value["source_ids"])}
        for value in buckets.values()
    ]
    items.sort(key=lambda item: (-item["track_count"], item["album"]))
    return {"items": items[:limit], "total": len(items)}


@router.get("/artists")
def artists(limit: int = Query(default=100, ge=1, le=200), db: Session = Depends(get_db)) -> Dict[str, Any]:
    rows = list(db.execute(select(UnifiedTrackRecord)).scalars())
    buckets: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        name = row.artist or "未知艺人"
        bucket = buckets.setdefault(
            name, {"artist": name, "track_count": 0, "album_count": 0, "albums": set()}
        )
        bucket["track_count"] += 1
        if row.album:
            bucket["albums"].add(row.album)
    items = [
        {
            "artist": value["artist"],
            "track_count": value["track_count"],
            "album_count": len(value["albums"]),
        }
        for value in buckets.values()
    ]
    items.sort(key=lambda item: (-item["track_count"], item["artist"]))
    return {"items": items[:limit], "total": len(items)}


# -- favourites ------------------------------------------------------------

@router.get("/favorites", response_model=Page[TrackOut])
def favorites(
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> Page[TrackOut]:
    rows, total = library.list_favorites(db, limit=limit, offset=offset)
    return Page(items=[_track_out(db, r) for r in rows], total=total, limit=limit, offset=offset)


@router.post("/favorites/{track_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def add_favorite(track_id: str, db: Session = Depends(get_db)) -> Response:
    library.add_favorite(db, track_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/favorites/{track_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def remove_favorite(track_id: str, db: Session = Depends(get_db)) -> Response:
    library.remove_favorite(db, track_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# -- playlists -------------------------------------------------------------

@router.get("/playlists")
def playlists(db: Session = Depends(get_db)) -> Dict[str, Any]:
    rows = library.list_playlists(db)
    return {
        "items": [
            {
                "playlist_id": record.id,
                "name": record.name,
                "description": record.description,
                "artwork": record.artwork,
                "track_count": len(library.playlist_tracks(db, record.id)),
                "source_id": record.source_id,
                "is_user_owned": record.is_user_owned,
                "created_at": record.created_at,
            }
            for record in rows
        ],
        "total": len(rows),
    }


@router.post("/playlists", status_code=status.HTTP_201_CREATED)
def create_playlist(payload: PlaylistCreate, db: Session = Depends(get_db)) -> Dict[str, Any]:
    record = library.create_playlist(db, payload.name, payload.description)
    return {
        "playlist_id": record.id,
        "name": record.name,
        "description": record.description,
        "track_count": 0,
        "created_at": record.created_at,
    }


@router.get("/playlists/{playlist_id}/tracks", response_model=Page[TrackOut])
def playlist_tracks(
    playlist_id: str,
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> Page[TrackOut]:
    rows = library.playlist_tracks(db, playlist_id)
    window = rows[offset : offset + limit]
    return Page(
        items=[_track_out(db, r) for r in window], total=len(rows), limit=limit, offset=offset
    )


@router.post("/playlists/{playlist_id}/tracks/{track_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def add_playlist_track(playlist_id: str, track_id: str, db: Session = Depends(get_db)) -> Response:
    library.add_to_playlist(db, playlist_id, track_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/playlists/{playlist_id}/tracks/{track_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def remove_playlist_track(playlist_id: str, track_id: str, db: Session = Depends(get_db)) -> Response:
    library.remove_from_playlist(db, playlist_id, track_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/playlists/{playlist_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_playlist(playlist_id: str, db: Session = Depends(get_db)) -> Response:
    library.delete_playlist(db, playlist_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# -- history ---------------------------------------------------------------

@router.get("/history")
def history(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    rows = library.list_history(db, limit=limit, offset=offset)
    return {
        "items": [
            {
                "history_id": entry.id,
                "played_at": entry.played_at,
                "position": entry.position_seconds,
                "completed": entry.completed,
                "track": _track_out(db, track),
            }
            for entry, track in rows
        ],
        "total": len(rows),
    }


@router.post("/history", status_code=status.HTTP_201_CREATED)
def add_history(payload: HistoryCreate, db: Session = Depends(get_db)) -> Dict[str, Any]:
    entry = library.record_play(db, payload.track_id, payload.position, payload.completed)
    return {"history_id": entry.id, "played_at": entry.played_at}


@router.delete("/history", status_code=status.HTTP_200_OK)
def clear_history(db: Session = Depends(get_db)) -> Dict[str, Any]:
    removed = library.clear_history(db)
    return {"removed": removed}

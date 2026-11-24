"""Unified music library: sources, tracks, favourites, playlists, history.

Merging rule: tracks are **never** merged by title alone.  A canonical group is
only formed when two providers report the same ISRC (or, failing that, the same
normalised artist + title + a duration within 2 seconds) — and grouping is
metadata-only, never a shared audio or playback permission.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.core.logging import get_logger
from app.models.audio import AudioAssetRecord
from app.models.source import (
    FavoriteRecord,
    MusicSourcePermissionRecord,
    MusicSourceRecord,
    PlaybackHistoryRecord,
    PlaylistTrackRecord,
    TranscriptionJobRecord,
    UnifiedPlaylistRecord,
    UnifiedTrackRecord,
)
from app.schemas.music_document import new_id
from app.services.sources.base import TrackDTO

logger = get_logger("pocketscore.library")

LOCAL_SOURCE_ID = "local"

DEFAULT_PERMISSIONS = {
    "local": {
        "metadata_access": True, "playback_access": True, "audio_read_access": True,
        "ai_processing_permission": False, "model_training_permission": False,
    },
    "subsonic": {
        "metadata_access": True, "playback_access": True, "audio_read_access": True,
        "ai_processing_permission": False, "model_training_permission": False,
    },
    "apple_music": {
        "metadata_access": True, "playback_access": True, "audio_read_access": False,
        "ai_processing_permission": False, "model_training_permission": False,
    },
    "spotify": {
        "metadata_access": True, "playback_access": True, "audio_read_access": False,
        "ai_processing_permission": False, "model_training_permission": False,
    },
    "netease": {
        "metadata_access": False, "playback_access": False, "audio_read_access": False,
        "ai_processing_permission": False, "model_training_permission": False,
    },
    "qqmusic": {
        "metadata_access": False, "playback_access": False, "audio_read_access": False,
        "ai_processing_permission": False, "model_training_permission": False,
    },
}


# ---------------------------------------------------------------------------
# sources
# ---------------------------------------------------------------------------

def ensure_local_source(session: Session) -> MusicSourceRecord:
    record = session.get(MusicSourceRecord, LOCAL_SOURCE_ID)
    if record is None:
        record = MusicSourceRecord(
            id=LOCAL_SOURCE_ID,
            provider="local",
            display_name="本地音乐",
            status="connected",
            config_json="{}",
            capabilities_json=json.dumps(
                {
                    "metadata": True, "playback": True, "audio_read": True,
                    "ai_processing": False, "model_training": False,
                    "playlists": True, "search": True, "favorites": True,
                    "requires_auth": False,
                }
            ),
        )
        session.add(record)
        session.flush()
        session.add(
            MusicSourcePermissionRecord(
                id=new_id(), source_id=record.id, **DEFAULT_PERMISSIONS["local"]
            )
        )
        session.commit()
    return record


def list_sources(session: Session) -> List[MusicSourceRecord]:
    ensure_local_source(session)
    return list(session.execute(select(MusicSourceRecord).order_by(MusicSourceRecord.created_at)).scalars())


def get_source(session: Session, source_id: str) -> MusicSourceRecord:
    record = session.get(MusicSourceRecord, source_id)
    if record is None:
        raise NotFoundError(f"music source {source_id!r} not found", code="SOURCE_NOT_FOUND")
    return record


def create_source(
    session: Session,
    *,
    provider: str,
    display_name: str,
    config: Dict[str, Any],
    status: str = "disconnected",
) -> MusicSourceRecord:
    source_id = new_id("src_")
    record = MusicSourceRecord(
        id=source_id,
        provider=provider,
        display_name=display_name,
        status=status,
        config_json=json.dumps(config, ensure_ascii=False),
        capabilities_json="{}",
    )
    session.add(record)
    session.flush()
    session.add(
        MusicSourcePermissionRecord(
            id=new_id(), source_id=source_id, **DEFAULT_PERMISSIONS.get(provider, DEFAULT_PERMISSIONS["local"])
        )
    )
    session.commit()
    return record


def delete_source(session: Session, source_id: str) -> None:
    record = get_source(session, source_id)
    session.delete(record)
    session.commit()


def get_permissions(session: Session, source_id: str) -> MusicSourcePermissionRecord:
    record = session.execute(
        select(MusicSourcePermissionRecord).where(MusicSourcePermissionRecord.source_id == source_id)
    ).scalars().first()
    if record is None:
        record = MusicSourcePermissionRecord(
            id=new_id(), source_id=source_id,
            **DEFAULT_PERMISSIONS.get("local"),
        )
        session.add(record)
        session.commit()
    return record


def update_permissions(session: Session, source_id: str, **values: bool) -> MusicSourcePermissionRecord:
    record = get_permissions(session, source_id)
    for field, value in values.items():
        if value is not None and hasattr(record, field):
            setattr(record, field, bool(value))
    session.commit()
    return record


# ---------------------------------------------------------------------------
# tracks
# ---------------------------------------------------------------------------

def track_pk(source_id: str, external_id: str) -> str:
    """Stable internal track id derived from source + external id."""
    return hashlib.sha1(f"{source_id}:{external_id}".encode()).hexdigest()[:24]


def _normalise(text: str) -> str:
    return re.sub(r"[\s\-_·'\"!?.，,（）()]+", "", (text or "").lower())


def canonical_group_id(dto: TrackDTO) -> Optional[str]:
    """Metadata-only grouping key.

    **ISRC only.**  Title/artist/duration are deliberately not used: the spec
    forbids merging tracks by name, and two providers reporting the same title
    must never be treated as the same audio.
    """
    isrc = (dto.metadata or {}).get("isrc")
    if isrc:
        return f"isrc:{str(isrc).upper()}"
    return None


def upsert_tracks(session: Session, source_id: str, dtos: List[TrackDTO]) -> Tuple[int, int]:
    created = 0
    updated = 0
    for dto in dtos:
        if not dto.external_id:
            continue
        pk = track_pk(source_id, dto.external_id)
        record = session.get(UnifiedTrackRecord, pk)
        if record is None:
            record = UnifiedTrackRecord(
                id=pk,
                source_id=source_id,
                external_track_id=dto.external_id,
                title=dto.title or "(未命名)",
                artist=dto.artist or "",
                album=dto.album or "",
                duration=dto.duration,
                artwork=dto.artwork,
                source_url=dto.source_url,
                availability=dto.availability,
                metadata_json=json.dumps(dto.metadata, ensure_ascii=False),
                canonical_group_id=dto.canonical_group_id or canonical_group_id(dto),
                audio_asset_id=dto.audio_asset_id,
                stream_url=dto.stream_url,
                is_local=dto.is_local,
            )
            session.add(record)
            created += 1
        else:
            record.title = dto.title or record.title
            record.artist = dto.artist or record.artist
            record.album = dto.album or record.album
            record.duration = dto.duration or record.duration
            record.artwork = dto.artwork or record.artwork
            record.source_url = dto.source_url or record.source_url
            record.availability = dto.availability or record.availability
            record.metadata_json = json.dumps(dto.metadata, ensure_ascii=False)
            record.canonical_group_id = dto.canonical_group_id or record.canonical_group_id
            record.audio_asset_id = dto.audio_asset_id or record.audio_asset_id
            record.stream_url = dto.stream_url or record.stream_url
            updated += 1
    session.commit()
    return created, updated


def register_local_asset(session: Session, asset: AudioAssetRecord) -> UnifiedTrackRecord:
    """Expose an uploaded audio asset as a playable local track."""
    ensure_local_source(session)
    dto = TrackDTO(
        external_id=f"asset:{asset.id}",
        title=asset.title or asset.filename,
        artist=asset.artist or "未知艺人",
        album="本地导入",
        duration=asset.duration,
        artwork=asset.artwork_path,
        availability="streamable",
        metadata={"audio_asset_id": asset.id, "checksum": asset.checksum_sha256},
        is_local=True,
        audio_asset_id=asset.id,
        stream_url=f"/api/v1/audio/assets/{asset.id}/stream",
    )
    upsert_tracks(session, LOCAL_SOURCE_ID, [dto])
    pk = track_pk(LOCAL_SOURCE_ID, dto.external_id)
    record = session.get(UnifiedTrackRecord, pk)
    assert record is not None
    return record


def get_track(session: Session, track_id: str) -> UnifiedTrackRecord:
    record = session.get(UnifiedTrackRecord, track_id)
    if record is None:
        raise NotFoundError(f"track {track_id!r} not found", code="TRACK_NOT_FOUND")
    return record


def list_tracks(
    session: Session,
    *,
    query: Optional[str] = None,
    source_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Tuple[List[UnifiedTrackRecord], int]:
    stmt = select(UnifiedTrackRecord)
    count_stmt = select(func.count()).select_from(UnifiedTrackRecord)
    conditions = []
    if query:
        like = f"%{query.strip()}%"
        conditions.append(
            UnifiedTrackRecord.title.ilike(like)
            | UnifiedTrackRecord.artist.ilike(like)
            | UnifiedTrackRecord.album.ilike(like)
        )
    if source_id:
        conditions.append(UnifiedTrackRecord.source_id == source_id)
    for condition in conditions:
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)
    stmt = stmt.order_by(UnifiedTrackRecord.artist, UnifiedTrackRecord.title).limit(limit).offset(offset)
    rows = list(session.execute(stmt).scalars())
    total = int(session.execute(count_stmt).scalar_one())
    return rows, total


def track_to_dict(record: UnifiedTrackRecord) -> Dict[str, Any]:
    return {
        "track_id": record.id,
        "source_id": record.source_id,
        "external_track_id": record.external_track_id,
        "title": record.title,
        "artist": record.artist,
        "album": record.album,
        "duration": record.duration,
        "artwork": record.artwork,
        "source_url": record.source_url,
        "availability": record.availability,
        "metadata": json.loads(record.metadata_json or "{}"),
        "canonical_group_id": record.canonical_group_id,
        "stream_url": record.stream_url,
        "is_local": record.is_local,
        "play_count": record.play_count,
    }


# ---------------------------------------------------------------------------
# favourites
# ---------------------------------------------------------------------------

def add_favorite(session: Session, track_id: str, note: Optional[str] = None) -> None:
    get_track(session, track_id)
    existing = session.get(FavoriteRecord, track_id)
    if existing is None:
        session.add(FavoriteRecord(track_id=track_id, note=note))
        session.commit()


def remove_favorite(session: Session, track_id: str) -> None:
    existing = session.get(FavoriteRecord, track_id)
    if existing is not None:
        session.delete(existing)
        session.commit()


def list_favorites(session: Session, limit: int = 100, offset: int = 0) -> Tuple[List[UnifiedTrackRecord], int]:
    stmt = (
        select(UnifiedTrackRecord)
        .join(FavoriteRecord, FavoriteRecord.track_id == UnifiedTrackRecord.id)
        .order_by(FavoriteRecord.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = list(session.execute(stmt).scalars())
    total = int(
        session.execute(select(func.count()).select_from(FavoriteRecord)).scalar_one()
    )
    return rows, total


def is_favorite(session: Session, track_id: str) -> bool:
    return session.get(FavoriteRecord, track_id) is not None


# ---------------------------------------------------------------------------
# playlists
# ---------------------------------------------------------------------------

def create_playlist(session: Session, name: str, description: str = "") -> UnifiedPlaylistRecord:
    ensure_local_source(session)
    record = UnifiedPlaylistRecord(
        id=new_id("pl_"),
        source_id=LOCAL_SOURCE_ID,
        external_playlist_id=new_id("ext_"),
        name=name,
        description=description,
        is_user_owned=True,
    )
    session.add(record)
    session.commit()
    return record


def list_playlists(session: Session) -> List[UnifiedPlaylistRecord]:
    return list(
        session.execute(
            select(UnifiedPlaylistRecord).order_by(UnifiedPlaylistRecord.created_at)
        ).scalars()
    )


def get_playlist(session: Session, playlist_id: str) -> UnifiedPlaylistRecord:
    record = session.get(UnifiedPlaylistRecord, playlist_id)
    if record is None:
        raise NotFoundError(f"playlist {playlist_id!r} not found", code="PLAYLIST_NOT_FOUND")
    return record


def playlist_tracks(session: Session, playlist_id: str) -> List[UnifiedTrackRecord]:
    get_playlist(session, playlist_id)
    stmt = (
        select(UnifiedTrackRecord)
        .join(PlaylistTrackRecord, PlaylistTrackRecord.track_id == UnifiedTrackRecord.id)
        .where(PlaylistTrackRecord.playlist_id == playlist_id)
        .order_by(PlaylistTrackRecord.position)
    )
    return list(session.execute(stmt).scalars())


def add_to_playlist(session: Session, playlist_id: str, track_id: str) -> None:
    get_playlist(session, playlist_id)
    get_track(session, track_id)
    existing = session.execute(
        select(PlaylistTrackRecord).where(
            PlaylistTrackRecord.playlist_id == playlist_id,
            PlaylistTrackRecord.track_id == track_id,
        )
    ).scalars().first()
    if existing is not None:
        return
    count = int(
        session.execute(
            select(func.count()).select_from(PlaylistTrackRecord).where(
                PlaylistTrackRecord.playlist_id == playlist_id
            )
        ).scalar_one()
    )
    session.add(PlaylistTrackRecord(playlist_id=playlist_id, track_id=track_id, position=count))
    session.commit()


def remove_from_playlist(session: Session, playlist_id: str, track_id: str) -> None:
    record = session.execute(
        select(PlaylistTrackRecord).where(
            PlaylistTrackRecord.playlist_id == playlist_id,
            PlaylistTrackRecord.track_id == track_id,
        )
    ).scalars().first()
    if record is not None:
        session.delete(record)
        session.commit()


def delete_playlist(session: Session, playlist_id: str) -> None:
    record = get_playlist(session, playlist_id)
    session.delete(record)
    session.commit()


# ---------------------------------------------------------------------------
# history
# ---------------------------------------------------------------------------

def record_play(session: Session, track_id: str, position: float = 0.0, completed: bool = False) -> PlaybackHistoryRecord:
    record = get_track(session, track_id)
    entry = PlaybackHistoryRecord(track_id=track_id, position_seconds=position, completed=completed)
    session.add(entry)
    record.play_count = (record.play_count or 0) + 1
    session.commit()
    return entry


def list_history(session: Session, limit: int = 50, offset: int = 0) -> List[Tuple[PlaybackHistoryRecord, UnifiedTrackRecord]]:
    stmt = (
        select(PlaybackHistoryRecord, UnifiedTrackRecord)
        .join(UnifiedTrackRecord, UnifiedTrackRecord.id == PlaybackHistoryRecord.track_id)
        .order_by(PlaybackHistoryRecord.played_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return [(row[0], row[1]) for row in session.execute(stmt).all()]


def clear_history(session: Session) -> int:
    rows = list(session.execute(select(PlaybackHistoryRecord)).scalars())
    for row in rows:
        session.delete(row)
    session.commit()
    return len(rows)


# ---------------------------------------------------------------------------
# library statistics
# ---------------------------------------------------------------------------

def library_stats(session: Session) -> Dict[str, Any]:
    tracks = int(session.execute(select(func.count()).select_from(UnifiedTrackRecord)).scalar_one())
    sources = int(session.execute(select(func.count()).select_from(MusicSourceRecord)).scalar_one())
    playlists = int(session.execute(select(func.count()).select_from(UnifiedPlaylistRecord)).scalar_one())
    favorites = int(session.execute(select(func.count()).select_from(FavoriteRecord)).scalar_one())
    jobs = int(session.execute(select(func.count()).select_from(TranscriptionJobRecord)).scalar_one())
    total_duration = float(
        session.execute(select(func.coalesce(func.sum(UnifiedTrackRecord.duration), 0.0))).scalar_one()
    )
    return {
        "tracks": tracks,
        "sources": sources,
        "playlists": playlists,
        "favorites": favorites,
        "transcription_jobs": jobs,
        "total_duration": round(total_duration, 2),
    }


def sync_from_dtos(session: Session, source_id: str, dtos: List[TrackDTO]) -> Dict[str, int]:
    created, updated = upsert_tracks(session, source_id, dtos)
    return {"created": created, "updated": updated, "total": created + updated}

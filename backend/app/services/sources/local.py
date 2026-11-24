"""Local music adapter: files the user imported into PocketScore."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.audio import AudioAssetRecord
from app.models.source import UnifiedTrackRecord
from app.services.sources.base import (
    ConnectionResult,
    PageResult,
    SourceAdapter,
    SourceCapabilities,
    TrackDTO,
    provider_policy,
)

logger = get_logger("pocketscore.sources.local")


class LocalSourceAdapter(SourceAdapter):
    provider = "local"
    display_name = "本地音乐"
    capabilities = SourceCapabilities(
        metadata=True,
        playback=True,
        audio_read=True,
        # Local files are eligible only when the user owns / is allowed to
        # process them; the eligibility service asks for that permission.
        ai_processing=False,
        model_training=False,
        playlists=True,
        search=True,
        favorites=True,
        requires_auth=False,
        policy_note=provider_policy("local"),
    )

    def __init__(self, source_id: str, config: Optional[Dict[str, Any]] = None, *,
                 session: Optional[Session] = None) -> None:
        super().__init__(source_id, config)
        self.session = session

    async def test_connection(self) -> ConnectionResult:
        count = self._asset_count()
        return ConnectionResult(
            ok=True,
            status="connected",
            message=f"本地资料库已就绪（{count} 个音频文件）",
            account_name="本地",
            details={"assets": count},
        )

    def _asset_count(self) -> int:
        if self.session is None:
            return 0
        from sqlalchemy import func

        return int(self.session.execute(select(func.count()).select_from(AudioAssetRecord)).scalar_one())

    async def list_tracks(self, limit: int = 50, offset: int = 0, **_kwargs) -> PageResult:
        if self.session is None:
            return PageResult(items=[], total=0, offset=offset, limit=limit)
        stmt = (
            select(UnifiedTrackRecord)
            .where(UnifiedTrackRecord.is_local.is_(True))
            .order_by(UnifiedTrackRecord.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = list(self.session.execute(stmt).scalars())
        from sqlalchemy import func

        total = int(
            self.session.execute(
                select(func.count()).select_from(UnifiedTrackRecord).where(
                    UnifiedTrackRecord.is_local.is_(True)
                )
            ).scalar_one()
        )
        return PageResult(items=[self._to_dto(row) for row in rows], total=total, offset=offset, limit=limit)

    async def search(self, query: str, limit: int = 30) -> Dict[str, List[Any]]:
        if self.session is None:
            return {"tracks": [], "albums": [], "artists": [], "playlists": []}
        like = f"%{query.strip()}%"
        stmt = (
            select(UnifiedTrackRecord)
            .where(UnifiedTrackRecord.is_local.is_(True))
            .where(
                UnifiedTrackRecord.title.ilike(like) | UnifiedTrackRecord.artist.ilike(like)
            )
            .limit(limit)
        )
        rows = list(self.session.execute(stmt).scalars())
        return {"tracks": [self._to_dto(r) for r in rows], "albums": [], "artists": [], "playlists": []}

    async def get_stream(self, external_track_id: str) -> Optional[Dict[str, Any]]:
        if self.session is None:
            return None
        row = self.session.get(UnifiedTrackRecord, external_track_id)
        if row is None or not row.audio_asset_id:
            return None
        return {
            "mode": "direct",
            "provider": "local",
            "url": f"/api/v1/audio/assets/{row.audio_asset_id}/stream",
        }

    def _to_dto(self, row: UnifiedTrackRecord) -> TrackDTO:
        return TrackDTO(
            external_id=row.id,
            title=row.title,
            artist=row.artist,
            album=row.album,
            duration=row.duration,
            artwork=row.artwork,
            source_url=None,
            availability=row.availability,
            metadata={"audio_asset_id": row.audio_asset_id},
            is_local=True,
            audio_asset_id=row.audio_asset_id,
            stream_url=f"/api/v1/audio/assets/{row.audio_asset_id}/stream" if row.audio_asset_id else None,
        )


class FileLibraryAdapter(LocalSourceAdapter):
    """Alias used when the user points PocketScore at a folder (V1.0-A: same store)."""

    provider = "local"
    display_name = "本地文件夹"

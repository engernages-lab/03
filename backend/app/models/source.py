"""Multi-source music ecosystem tables.

Covers sources, external accounts, the unified library, favourites, playlists,
playback history, per-source permissions and transcription jobs.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.base import TimestampMixin, utcnow


class MusicSourceRecord(Base, TimestampMixin):
    __tablename__ = "music_sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="disconnected", nullable=False)
    config_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    capabilities_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    connected_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    permissions: Mapped[Optional["MusicSourcePermissionRecord"]] = relationship(
        back_populates="source", cascade="all, delete-orphan", uselist=False
    )
    account: Mapped[Optional["ExternalAccountRecord"]] = relationship(
        back_populates="source", cascade="all, delete-orphan", uselist=False
    )

    @property
    def config(self) -> dict:
        import json

        try:
            return json.loads(self.config_json or "{}")
        except ValueError:
            return {}

    @property
    def capabilities(self) -> dict:
        import json

        try:
            return json.loads(self.capabilities_json or "{}")
        except ValueError:
            return {}

    __table_args__ = (
        Index("ix_music_sources_provider", "provider"),
        UniqueConstraint("provider", "display_name", name="uq_music_sources_provider_name"),
    )


class ExternalAccountRecord(Base, TimestampMixin):
    __tablename__ = "external_accounts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("music_sources.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    account_name: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    access_token_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    refresh_token_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    token_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    scopes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    source: Mapped[MusicSourceRecord] = relationship(back_populates="account")


class MusicSourcePermissionRecord(Base, TimestampMixin):
    __tablename__ = "music_source_permissions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("music_sources.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    metadata_access: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    playback_access: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    audio_read_access: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ai_processing_permission: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    model_training_permission: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    source: Mapped[MusicSourceRecord] = relationship(back_populates="permissions")


class UnifiedTrackRecord(Base, TimestampMixin):
    __tablename__ = "unified_tracks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("music_sources.id", ondelete="CASCADE"), nullable=False
    )
    external_track_id: Mapped[str] = mapped_column(String(200), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    artist: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    album: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    duration: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    artwork: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    source_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    availability: Mapped[str] = mapped_column(String(24), default="metadata_only", nullable=False)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    canonical_group_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    audio_asset_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    stream_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    is_local: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    play_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (
        UniqueConstraint("source_id", "external_track_id", name="uq_tracks_source_external"),
        Index("ix_tracks_title", "title"),
        Index("ix_tracks_artist", "artist"),
        Index("ix_tracks_source", "source_id"),
        Index("ix_tracks_group", "canonical_group_id"),
    )


class UnifiedAlbumRecord(Base, TimestampMixin):
    __tablename__ = "unified_albums"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("music_sources.id", ondelete="CASCADE"), nullable=False
    )
    external_album_id: Mapped[str] = mapped_column(String(200), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    artist: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    artwork: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    track_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)

    __table_args__ = (
        UniqueConstraint("source_id", "external_album_id", name="uq_albums_source_external"),
    )


class UnifiedArtistRecord(Base, TimestampMixin):
    __tablename__ = "unified_artists"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("music_sources.id", ondelete="CASCADE"), nullable=False
    )
    external_artist_id: Mapped[str] = mapped_column(String(200), nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    artwork: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    album_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)

    __table_args__ = (
        UniqueConstraint("source_id", "external_artist_id", name="uq_artists_source_external"),
    )


class UnifiedPlaylistRecord(Base, TimestampMixin):
    __tablename__ = "unified_playlists"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("music_sources.id", ondelete="CASCADE"), nullable=False
    )
    external_playlist_id: Mapped[str] = mapped_column(String(200), nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    artwork: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    track_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_user_owned: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)

    __table_args__ = (
        UniqueConstraint("source_id", "external_playlist_id", name="uq_playlists_source_external"),
    )


class PlaylistTrackRecord(Base):
    __tablename__ = "playlist_tracks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    playlist_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("unified_playlists.id", ondelete="CASCADE"), nullable=False
    )
    track_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("unified_tracks.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (
        UniqueConstraint("playlist_id", "track_id", name="uq_playlist_track"),
        Index("ix_playlist_tracks_playlist", "playlist_id", "position"),
    )


class FavoriteRecord(Base):
    __tablename__ = "user_favorites"

    track_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("unified_tracks.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    note: Mapped[Optional[str]] = mapped_column(String(280), nullable=True)


class PlaybackHistoryRecord(Base):
    __tablename__ = "playback_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    track_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("unified_tracks.id", ondelete="CASCADE"), nullable=False
    )
    played_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    position_seconds: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    __table_args__ = (Index("ix_history_played_at", "played_at"),)


class TranscriptionJobRecord(Base, TimestampMixin):
    __tablename__ = "transcription_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    document_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    asset_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("audio_assets.id", ondelete="SET NULL"), nullable=True
    )
    track_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    source_kind: Mapped[str] = mapped_column(String(24), default="local_upload", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="queued", nullable=False)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    method: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    events_produced: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    analysis_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    warnings_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (Index("ix_jobs_status", "status"),)

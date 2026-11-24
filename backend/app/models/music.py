"""ORM models for music documents, tracks, events and keyboard layouts.

Documents are normalised: `music_documents` holds document-level fields and the
embedded layout/notation JSON, while tracks and events live in their own tables
with foreign keys and indexes.  There is exactly one stored copy of every note.
"""

from __future__ import annotations

import json
from typing import List, Optional

from sqlalchemy import (
    Boolean,
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
from app.models.base import TimestampMixin


class KeyboardLayoutRecord(Base, TimestampMixin):
    __tablename__ = "keyboard_layouts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(40), nullable=False)
    description: Mapped[str] = mapped_column(String(280), default="", nullable=False)
    root_note: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    key_count: Mapped[int] = mapped_column(Integer, nullable=False)
    octave_span: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    keys_json: Mapped[str] = mapped_column(Text, nullable=False)
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    def keys(self) -> List[dict]:
        return json.loads(self.keys_json or "[]")


class MusicDocumentRecord(Base, TimestampMixin):
    __tablename__ = "music_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    schema_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    artist: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    tempo: Mapped[float] = mapped_column(Float, default=120.0, nullable=False)
    ts_numerator: Mapped[int] = mapped_column(Integer, default=4, nullable=False)
    ts_denominator: Mapped[int] = mapped_column(Integer, default=4, nullable=False)
    key_signature: Mapped[str] = mapped_column(String(8), default="C", nullable=False)
    duration: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    keyboard_layout_id: Mapped[str] = mapped_column(String(64), nullable=False)
    keyboard_layout_json: Mapped[str] = mapped_column(Text, nullable=False)
    notation_settings_json: Mapped[str] = mapped_column(Text, nullable=False)
    source_metadata_json: Mapped[str] = mapped_column(Text, nullable=False)

    tracks: Mapped[List["MusicTrackRecord"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="MusicTrackRecord.position"
    )
    events: Mapped[List["MusicEventRecord"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="MusicEventRecord.start_time"
    )

    __table_args__ = (
        Index("ix_music_documents_title", "title"),
        Index("ix_music_documents_updated_at", "updated_at"),
    )


class MusicTrackRecord(Base):
    __tablename__ = "music_tracks"

    pk: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("music_documents.id", ondelete="CASCADE"), nullable=False
    )
    track_id: Mapped[str] = mapped_column(String(48), nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    instrument: Mapped[str] = mapped_column(String(64), default="piano", nullable=False)
    channel: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    color: Mapped[str] = mapped_column(String(9), default="#3ddc97", nullable=False)
    muted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    document: Mapped[MusicDocumentRecord] = relationship(back_populates="tracks")

    __table_args__ = (
        UniqueConstraint("document_id", "track_id", name="uq_music_tracks_document_track"),
        Index("ix_music_tracks_document", "document_id"),
    )


class MusicEventRecord(Base):
    __tablename__ = "music_events"

    pk: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("music_documents.id", ondelete="CASCADE"), nullable=False
    )
    event_id: Mapped[str] = mapped_column(String(48), nullable=False)
    track_id: Mapped[str] = mapped_column(String(48), nullable=False)
    pitch: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    start_time: Mapped[float] = mapped_column(Float, nullable=False)
    duration: Mapped[float] = mapped_column(Float, nullable=False)
    velocity: Mapped[int] = mapped_column(Integer, default=96, nullable=False)
    measure: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    beat: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    mapped_key: Mapped[Optional[str]] = mapped_column(String(48), nullable=True)
    kind: Mapped[str] = mapped_column(String(8), default="note", nullable=False)
    chord_id: Mapped[Optional[str]] = mapped_column(String(48), nullable=True)
    tie_group: Mapped[Optional[str]] = mapped_column(String(48), nullable=True)

    document: Mapped[MusicDocumentRecord] = relationship(back_populates="events")

    __table_args__ = (
        UniqueConstraint("document_id", "event_id", name="uq_music_events_document_event"),
        Index("ix_music_events_document_start", "document_id", "start_time"),
        Index("ix_music_events_document_pitch", "document_id", "pitch"),
        Index("ix_music_events_document_track", "document_id", "track_id"),
    )

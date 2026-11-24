"""Persistence for MusicDocument (normalised tables, single stored copy)."""

from __future__ import annotations

import json
from typing import List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationAppError
from app.models.music import MusicDocumentRecord, MusicEventRecord, MusicTrackRecord
from app.schemas.keyboard import KeyboardLayout
from app.schemas.music_document import (
    MusicDocument,
    MusicTrack,
    NoteEvent,
    NotationSettings,
    SourceMetadata,
    TimeSignature,
)


def _dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def save_document(session: Session, document: MusicDocument, *, create: bool = True) -> MusicDocument:
    record = session.get(MusicDocumentRecord, document.document_id)
    if record is None:
        if not create:
            raise NotFoundError(
                f"MusicDocument {document.document_id!r} not found",
                code="MUSIC_DOCUMENT_NOT_FOUND",
                details={"document_id": document.document_id},
            )
        record = MusicDocumentRecord(id=document.document_id)
        session.add(record)

    record.schema_version = document.schema_version
    record.title = document.title
    record.artist = document.artist
    record.tempo = document.tempo
    record.ts_numerator = document.time_signature.numerator
    record.ts_denominator = document.time_signature.denominator
    record.key_signature = document.key_signature
    record.duration = document.duration
    record.keyboard_layout_id = document.keyboard_layout.layout_id
    record.keyboard_layout_json = _dumps(document.keyboard_layout.model_dump(mode="json"))
    record.notation_settings_json = _dumps(document.notation_settings.model_dump(mode="json"))
    record.source_metadata_json = _dumps(document.source_metadata.model_dump(mode="json"))

    # Replace children in one transaction; the unique constraints are scoped per
    # document so the flush order matters.
    record.tracks.clear()
    record.events.clear()
    session.flush()

    for track in document.tracks:
        record.tracks.append(
            MusicTrackRecord(
                track_id=track.track_id,
                name=track.name,
                instrument=track.instrument,
                channel=track.channel,
                position=track.index,
                color=track.color,
                muted=track.muted,
            )
        )
    for event in document.events:
        record.events.append(
            MusicEventRecord(
                event_id=event.event_id,
                track_id=event.track_id,
                pitch=event.pitch,
                start_time=event.start_time,
                duration=event.duration,
                velocity=event.velocity,
                measure=event.measure,
                beat=event.beat,
                mapped_key=event.mapped_key,
                kind=event.kind,
                chord_id=event.chord_id,
                tie_group=event.tie_group,
            )
        )
    session.commit()
    return document


def load_document(session: Session, document_id: str) -> MusicDocument:
    record = session.get(MusicDocumentRecord, document_id)
    if record is None:
        raise NotFoundError(
            f"MusicDocument {document_id!r} not found",
            code="MUSIC_DOCUMENT_NOT_FOUND",
            details={"document_id": document_id},
        )
    try:
        layout = KeyboardLayout.model_validate(json.loads(record.keyboard_layout_json))
        notation = NotationSettings.model_validate(json.loads(record.notation_settings_json))
        source = SourceMetadata.model_validate(json.loads(record.source_metadata_json))
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValidationAppError(
            "stored document payload is corrupt",
            code="DOCUMENT_CORRUPT",
            status_code=500,
            details={"reason": str(exc)},
        ) from exc

    tracks = [
        MusicTrack(
            track_id=t.track_id,
            name=t.name,
            instrument=t.instrument,
            channel=t.channel,
            index=t.position,
            color=t.color,
            muted=t.muted,
        )
        for t in sorted(record.tracks, key=lambda t: t.position)
    ]
    events = [
        NoteEvent(
            event_id=e.event_id,
            pitch=e.pitch,
            start_time=e.start_time,
            duration=e.duration,
            velocity=e.velocity,
            track_id=e.track_id,
            measure=e.measure,
            beat=e.beat,
            mapped_key=e.mapped_key,
            kind=e.kind,
            chord_id=e.chord_id,
            tie_group=e.tie_group,
        )
        for e in sorted(record.events, key=lambda e: (e.start_time, e.pk))
    ]

    return MusicDocument(
        schema_version=record.schema_version,
        document_id=record.id,
        title=record.title,
        artist=record.artist,
        tempo=record.tempo,
        time_signature=TimeSignature(numerator=record.ts_numerator, denominator=record.ts_denominator),
        key_signature=record.key_signature,
        duration=record.duration,
        tracks=tracks,
        events=events,
        keyboard_layout=layout,
        notation_settings=notation,
        source_metadata=source,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def list_documents(
    session: Session, *, limit: int = 50, offset: int = 0, query: Optional[str] = None
) -> Tuple[List[MusicDocumentRecord], int]:
    stmt = select(MusicDocumentRecord)
    count_stmt = select(func.count()).select_from(MusicDocumentRecord)
    if query:
        like = f"%{query.strip()}%"
        stmt = stmt.where(MusicDocumentRecord.title.ilike(like) | MusicDocumentRecord.artist.ilike(like))
        count_stmt = count_stmt.where(
            MusicDocumentRecord.title.ilike(like) | MusicDocumentRecord.artist.ilike(like)
        )
    stmt = stmt.order_by(MusicDocumentRecord.updated_at.desc()).limit(limit).offset(offset)
    rows = list(session.execute(stmt).scalars())
    total = int(session.execute(count_stmt).scalar_one())
    return rows, total


def delete_document(session: Session, document_id: str) -> None:
    record = session.get(MusicDocumentRecord, document_id)
    if record is None:
        raise NotFoundError(
            f"MusicDocument {document_id!r} not found",
            code="MUSIC_DOCUMENT_NOT_FOUND",
            details={"document_id": document_id},
        )
    session.delete(record)
    session.commit()


def document_exists(session: Session, document_id: str) -> bool:
    return session.get(MusicDocumentRecord, document_id) is not None

"""MusicDocument REST endpoints.

Documents are the only writable music resource: grid and jianpu editors send
edit operations here, which keeps both notations derived from one source.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Body, Depends, File, Query, Response, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import PayloadTooLargeError, ValidationAppError
from app.schemas.common import Page
from app.schemas.keyboard import KeyboardLayout
from app.schemas.music_document import MusicDocument, TimeSignature, new_id
from app.services import music_document as core
from app.services.keyboard.mapping import apply_layout
from app.services.music_document import repository
from app.services.music_document.serialization import document_from_json, document_to_dict
from app.services.notation.sync import EditOperation, EditResult, apply_operations

router = APIRouter()


class DocumentSummary(BaseModel):
    document_id: str
    title: str
    artist: str
    tempo: float
    time_signature: str
    key_signature: str
    duration: float
    tracks: int
    events: int
    measures: int
    layout_id: str
    layout_name: str
    source_kind: str
    created_at: datetime
    updated_at: datetime


class CreateDocumentRequest(BaseModel):
    title: str = Field(default="未命名谱面", min_length=1, max_length=200)
    artist: str = Field(default="未知艺人", max_length=200)
    tempo: float = Field(default=120.0, ge=20.0, le=400.0)
    numerator: int = Field(default=4, ge=1, le=32)
    denominator: int = 4
    key_signature: str = "C"
    layout: Optional[KeyboardLayout] = None


class UpdateDocumentRequest(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    artist: Optional[str] = Field(default=None, max_length=200)
    tempo: Optional[float] = Field(default=None, ge=20.0, le=400.0)
    numerator: Optional[int] = Field(default=None, ge=1, le=32)
    denominator: Optional[int] = None
    key_signature: Optional[str] = None
    layout: Optional[KeyboardLayout] = None
    notation_settings: Optional[dict] = None


class EditBatchRequest(BaseModel):
    operations: List[EditOperation] = Field(min_length=1, max_length=500)


def _summary(document: MusicDocument) -> DocumentSummary:
    return DocumentSummary(
        document_id=document.document_id,
        title=document.title,
        artist=document.artist,
        tempo=document.tempo,
        time_signature=document.time_signature.as_label(),
        key_signature=document.key_signature,
        duration=document.duration,
        tracks=len(document.tracks),
        events=len(document.events),
        measures=document.total_measures(),
        layout_id=document.keyboard_layout.layout_id,
        layout_name=document.keyboard_layout.name,
        source_kind=document.source_metadata.kind,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


@router.get("", response_model=Page[DocumentSummary])
def list_documents(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    q: Optional[str] = Query(default=None, max_length=120),
    db: Session = Depends(get_db),
) -> Page[DocumentSummary]:
    records, total = repository.list_documents(db, limit=limit, offset=offset, query=q)
    items = [_summary(repository.load_document(db, record.id)) for record in records]
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.post("", response_model=MusicDocument, status_code=status.HTTP_201_CREATED)
def create_document(payload: CreateDocumentRequest, db: Session = Depends(get_db)) -> MusicDocument:
    from app.schemas.music_document import empty_document

    document = empty_document(
        title=payload.title,
        artist=payload.artist,
        tempo=payload.tempo,
        time_signature=TimeSignature(numerator=payload.numerator, denominator=payload.denominator),
        key_signature=payload.key_signature,
        keyboard_layout=payload.layout,
    )
    core.reindex(document)
    repository.save_document(db, document)
    return document


@router.post("/import", response_model=MusicDocument, status_code=status.HTTP_201_CREATED)
async def import_document(
    file: UploadFile = File(...), db: Session = Depends(get_db)
) -> MusicDocument:
    raw = await file.read()
    if len(raw) > 8 * 1024 * 1024:
        raise PayloadTooLargeError("document JSON must be smaller than 8MB")
    document = document_from_json(raw.decode("utf-8", errors="replace"))
    # Importing always allocates a fresh id so the original is never overwritten.
    document.document_id = new_id()
    core.reindex(document)
    repository.save_document(db, document)
    return document


@router.get("/{document_id}", response_model=MusicDocument)
def get_document(document_id: str, db: Session = Depends(get_db)) -> MusicDocument:
    return repository.load_document(db, document_id)


@router.put("/{document_id}", response_model=MusicDocument)
def replace_document(
    document_id: str, payload: dict = Body(...), db: Session = Depends(get_db)
) -> MusicDocument:
    document = MusicDocument.model_validate(payload)
    if document.document_id != document_id:
        raise ValidationAppError(
            "path document_id does not match payload document_id", code="DOCUMENT_ID_MISMATCH"
        )
    core.reindex(document)
    repository.save_document(db, document)
    return document


@router.patch("/{document_id}", response_model=MusicDocument)
def update_document(
    document_id: str, payload: UpdateDocumentRequest, db: Session = Depends(get_db)
) -> MusicDocument:
    document = repository.load_document(db, document_id)
    if payload.title is not None:
        document.title = payload.title
    if payload.artist is not None:
        document.artist = payload.artist
    if payload.tempo is not None:
        document.tempo = payload.tempo
    if payload.numerator is not None or payload.denominator is not None:
        document.time_signature = TimeSignature(
            numerator=payload.numerator or document.time_signature.numerator,
            denominator=payload.denominator or document.time_signature.denominator,
        )
    if payload.key_signature is not None:
        document.key_signature = payload.key_signature
    if payload.layout is not None:
        apply_layout(document, payload.layout)
    if payload.notation_settings is not None:
        document.notation_settings = type(document.notation_settings).model_validate(
            payload.notation_settings
        )
    core.reindex(document)
    repository.save_document(db, document)
    return document


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_document(document_id: str, db: Session = Depends(get_db)) -> Response:
    repository.delete_document(db, document_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{document_id}/duplicate", response_model=MusicDocument, status_code=status.HTTP_201_CREATED)
def duplicate_document(document_id: str, db: Session = Depends(get_db)) -> MusicDocument:
    document = repository.load_document(db, document_id)
    clone = document.model_copy(deep=True)
    clone.document_id = new_id()
    clone.title = f"{document.title} 副本"
    clone.created_at = clone.updated_at = datetime.now(timezone.utc)
    for event in clone.events:
        event.event_id = new_id()
    core.reindex(clone)
    repository.save_document(db, clone)
    return clone


@router.post("/{document_id}/edits", response_model=EditResult)
def apply_edits(
    document_id: str, payload: EditBatchRequest, db: Session = Depends(get_db)
) -> EditResult:
    document = repository.load_document(db, document_id)
    result = apply_operations(document, payload.operations)
    repository.save_document(db, result.document)
    return result


@router.get("/{document_id}/summary")
def document_summary(document_id: str, db: Session = Depends(get_db)) -> dict:
    document = repository.load_document(db, document_id)
    return {
        **_summary(document).model_dump(mode="json"),
        "findings": core.validate_document(document),
        "tracks": list(core.track_summary(document)),
    }


@router.get("/{document_id}/export")
def export_document(
    document_id: str,
    format: str = Query(default="json", pattern="^(json|pocket)$"),
    db: Session = Depends(get_db),
) -> Response:
    document = repository.load_document(db, document_id)
    payload = document_to_dict(document)
    if format == "pocket":
        payload = {"pocketscore": True, "version": document.schema_version, "document": payload}
    import json
    import re
    from urllib.parse import quote

    body = json.dumps(payload, ensure_ascii=False, indent=2)
    filename = f"{document.title or 'document'}.pocketscore.json"
    # Headers must be latin-1 safe; expose the UTF-8 name via RFC 5987.
    ascii_name = re.sub(r"[^A-Za-z0-9._-]+", "_", document.title or "document") or "document"
    disposition = (
        f'attachment; filename="{ascii_name}.pocketscore.json"; '
        f"filename*=UTF-8''{quote(filename)}"
    )
    return Response(
        content=body,
        media_type="application/json",
        headers={"Content-Disposition": disposition},
    )

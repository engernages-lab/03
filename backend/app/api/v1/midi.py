"""MIDI import / export endpoints."""

from __future__ import annotations

import re
from typing import Any, Dict, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.errors import PayloadTooLargeError, UnsupportedMediaError
from app.schemas.music_document import MusicDocument
from app.services import music_document as core
from app.services.keyboard.repository import get_layout
from app.services.midi.exporter import document_to_midi_bytes
from app.services.midi.importer import import_midi_bytes, inspect_midi
from app.services.music_document import repository

router = APIRouter()


def _validate_midi_upload(data: bytes, filename: str) -> None:
    settings = get_settings()
    ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
    if ext not in settings.allowed_midi_extensions:
        raise UnsupportedMediaError(
            f"unsupported MIDI extension {ext or '(none)'!r}",
            code="UNSUPPORTED_MEDIA_TYPE",
            details={"supported": settings.allowed_midi_extensions},
        )
    if len(data) == 0:
        raise UnsupportedMediaError("uploaded MIDI file is empty", code="MIDI_PARSE_ERROR")
    if len(data) > 16 * 1024 * 1024:
        raise PayloadTooLargeError("MIDI files must be smaller than 16MB")


@router.post("/inspect")
async def inspect(file: UploadFile = File(...)) -> Dict[str, Any]:
    data = await file.read()
    _validate_midi_upload(data, file.filename or "upload.mid")
    result = inspect_midi(data)
    result["filename"] = file.filename
    return result


@router.post("/import", response_model=MusicDocument, status_code=status.HTTP_201_CREATED)
async def import_file(
    file: UploadFile = File(...),
    title: Optional[str] = Query(default=None),
    artist: Optional[str] = Query(default=None),
    layout_id: Optional[str] = Query(default=None),
    save: bool = Query(default=True, description="persist the parsed document"),
    db: Session = Depends(get_db),
) -> MusicDocument:
    data = await file.read()
    filename = file.filename or "upload.mid"
    _validate_midi_upload(data, filename)

    layout = get_layout(db, layout_id) if layout_id else None
    document = import_midi_bytes(
        data,
        title=title or filename.rsplit(".", 1)[0],
        artist=artist or "未知艺人",
        filename=filename,
        keyboard_layout=layout,
    )
    core.reindex(document)
    if save:
        repository.save_document(db, document)
    return document


@router.get("/{document_id}/export")
def export_midi(document_id: str, db: Session = Depends(get_db)) -> Response:
    document = repository.load_document(db, document_id)
    payload = document_to_midi_bytes(document)
    # Header values must be latin-1 safe. Note that str.isalnum() is True for CJK,
    # so a character-class regex is required here - not isalnum().
    ascii_name = re.sub(r"[^A-Za-z0-9._-]+", "_", document.title or "score").strip("_")[:40] or "score"
    # Keep the f-string expressions simple: backslashes are not allowed inside
    # f-string expressions before Python 3.12.
    utf8_name = f"{document.title or 'score'}.mid"
    disposition = (
        f'attachment; filename="{ascii_name}.mid"; '
        f"filename*=UTF-8''{quote(utf8_name)}"
    )
    return Response(
        content=payload,
        media_type="audio/midi",
        headers={"Content-Disposition": disposition},
    )

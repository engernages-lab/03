"""Audio upload, probing, waveform and streaming endpoints."""

from __future__ import annotations

import json
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, File, Query, Request, Response, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.errors import PayloadTooLargeError, ValidationAppError
from app.models.audio import AudioAssetRecord
from app.schemas.common import Page
from app.services.audio import assets
from app.services.audio import probe as probe_service

router = APIRouter()

CHUNK_SIZE = 256 * 1024


class AudioAssetOut(BaseModel):
    asset_id: str
    filename: str
    title: Optional[str]
    artist: Optional[str]
    mime: str
    ext: str
    size_bytes: int
    duration: float
    sample_rate: int
    channels: int
    bitrate: Optional[int]
    codec: Optional[str]
    checksum_sha256: str
    artwork_url: Optional[str]
    stream_url: str
    source_id: Optional[str]
    created_at: datetime


def to_out(record: AudioAssetRecord) -> AudioAssetOut:
    return AudioAssetOut(
        asset_id=record.id,
        filename=record.filename,
        title=record.title,
        artist=record.artist,
        mime=record.mime,
        ext=record.ext,
        size_bytes=record.size_bytes,
        duration=record.duration,
        sample_rate=record.sample_rate,
        channels=record.channels,
        bitrate=record.bitrate,
        codec=record.codec,
        checksum_sha256=record.checksum_sha256,
        artwork_url=record.artwork_path,
        stream_url=f"/api/v1/audio/assets/{record.id}/stream",
        source_id=record.source_id,
        created_at=record.created_at,
    )


@router.post("/upload", response_model=AudioAssetOut, status_code=status.HTTP_201_CREATED)
async def upload_audio(
    request: Request,
    file: UploadFile = File(...),
    title: Optional[str] = Query(default=None),
    artist: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
) -> AudioAssetOut:
    """Stream the upload to disk with a running size cap (never a 200 MB buffer)."""
    settings = get_settings()
    limit = settings.max_upload_bytes

    # Reject early when the client announces an oversized body.
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit * 1.05:
        raise PayloadTooLargeError(
            f"file exceeds the {settings.max_upload_mb}MB limit",
            details={"limit_mb": settings.max_upload_mb, "declared_mb": round(int(declared) / 1048576, 2)},
        )

    filename = file.filename or "upload.bin"
    # Validate the extension before touching the body.
    probe_service.validate_extension(filename)

    tmp_dir = Path(tempfile.mkdtemp(prefix="pocketscore-upload-"))
    tmp_path = tmp_dir / f"upload{Path(filename).suffix.lower()}"
    written = 0
    try:
        with open(tmp_path, "wb") as handle:
            while True:
                chunk = await file.read(CHUNK_SIZE)
                if not chunk:
                    break
                written += len(chunk)
                if written > limit:
                    raise PayloadTooLargeError(
                        f"file exceeds the {settings.max_upload_mb}MB limit",
                        details={"limit_mb": settings.max_upload_mb},
                    )
                handle.write(chunk)
        if written == 0:
            raise ValidationAppError("uploaded file is empty", code="AUDIO_PROBE_FAILED")
        record, _created = assets.ingest_audio_from_path(
            db, tmp_path, filename, title=title, artist=artist
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return to_out(record)


@router.post("/probe")
async def probe_upload(file: UploadFile = File(...)) -> Dict[str, Any]:
    """Validate and probe a file without storing it."""
    import tempfile
    from pathlib import Path

    settings = get_settings()
    data = bytearray()
    while True:
        chunk = await file.read(CHUNK_SIZE)
        if not chunk:
            break
        data.extend(chunk)
        if len(data) > settings.max_upload_bytes:
            raise PayloadTooLargeError(
                f"file exceeds the {settings.max_upload_mb}MB limit",
                details={"limit_mb": settings.max_upload_mb},
            )
    filename = file.filename or "upload.bin"
    ext = probe_service.validate_extension(filename)
    with tempfile.TemporaryDirectory(prefix="pocketscore-probe-") as tmp:
        target = Path(tmp) / f"probe{ext}"
        target.write_bytes(bytes(data))
        result = probe_service.probe_audio(target)
    return {**result.as_dict(), "filename": filename, "size_bytes": len(data)}


@router.get("/assets", response_model=Page[AudioAssetOut])
def list_assets(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    q: Optional[str] = Query(default=None, max_length=120),
    db: Session = Depends(get_db),
) -> Page[AudioAssetOut]:
    rows, total = assets.list_assets(db, limit=limit, offset=offset, query=q)
    return Page(items=[to_out(r) for r in rows], total=total, limit=limit, offset=offset)


@router.get("/assets/{asset_id}", response_model=AudioAssetOut)
def get_asset(asset_id: str, db: Session = Depends(get_db)) -> AudioAssetOut:
    return to_out(assets.get_asset(db, asset_id))


@router.delete("/assets/{asset_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_asset(asset_id: str, db: Session = Depends(get_db)) -> Response:
    assets.delete_asset(db, asset_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/assets/{asset_id}/waveform")
def waveform(
    asset_id: str,
    buckets: int = Query(default=600, ge=50, le=4000),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    record = assets.get_asset(db, asset_id)
    peaks = assets.asset_waveform(record, buckets=buckets)
    return {
        "asset_id": asset_id,
        "buckets": len(peaks),
        "duration": record.duration,
        "peaks": peaks,
    }


@router.post("/assets/{asset_id}/analyze")
def analyze(asset_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    record = assets.get_asset(db, asset_id)
    result = assets.asset_analysis(record)
    record.analysis_json = json.dumps(result, ensure_ascii=False)
    db.add(record)
    db.commit()
    return {
        "asset_id": asset_id,
        "analysis": result,
        "note": "这是信号分析结果（节拍/起音/能量），不是扒谱音符输出。",
    }


@router.get("/assets/{asset_id}/stream")
def stream(asset_id: str, request: Request, db: Session = Depends(get_db)) -> Response:
    record = assets.get_asset(db, asset_id)
    path = assets.absolute_path(record)
    if not path.exists():
        raise ValidationAppError(
            "audio file is missing from storage", code="AUDIO_FILE_MISSING", status_code=410
        )
    file_size = path.stat().st_size
    range_header = request.headers.get("range")
    if not range_header:
        return FileResponse(path, media_type=record.mime or "application/octet-stream")

    try:
        units, _, spec = range_header.partition("=")
        start_raw, _, end_raw = spec.partition("-")
        start = int(start_raw) if start_raw else 0
        end = int(end_raw) if end_raw else file_size - 1
    except ValueError as exc:
        raise ValidationAppError("invalid Range header", code="INVALID_RANGE") from exc
    start = max(0, min(start, file_size - 1))
    end = max(start, min(end, file_size - 1))
    length = end - start + 1

    def iter_file():
        with path.open("rb") as handle:
            handle.seek(start)
            remaining = length
            while remaining > 0:
                chunk = handle.read(min(CHUNK_SIZE, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    from fastapi.responses import StreamingResponse

    return StreamingResponse(
        iter_file(),
        status_code=206,
        media_type=record.mime or "application/octet-stream",
        headers={
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(length),
        },
    )

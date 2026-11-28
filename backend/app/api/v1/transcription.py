"""Transcription job endpoints (real pipeline, no fabricated notes)."""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Query, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db, get_session_factory
from app.core.errors import AppError, InferenceTimeoutError, ServiceBusyError
from app.core.logging import get_logger
from app.services import transcription
from app.services.audio import assets, note_extraction
from app.services.audio.probe import SUPPORTED_EXTENSIONS
from app.services.music_document import repository
from app.services.music_document.serialization import document_to_dict

logger = get_logger("pocketscore.transcription")

router = APIRouter()


class JobCreateRequest(BaseModel):
    asset_id: Optional[str] = None
    track_id: Optional[str] = None
    document_id: Optional[str] = None
    confirm_rights: bool = Field(default=False)


@router.get("/models")
def models() -> Dict[str, Any]:
    """Report which transcription backends are actually available."""
    status = note_extraction.model_status()
    return {
        "note_extraction": {
            **status,
            "code": None if status["available"] else "REQUIRES_MODEL",
        },
        "signal_analysis": {
            "available": True,
            "method": "librosa.beat + onset detection",
            "produces_notes": False,
        },
        "midi_import": {"available": True, "produces_notes": True},
    }


@router.get("/capabilities")
def capabilities() -> Dict[str, Any]:
    """Everything the UI needs to configure its upload form (single source)."""
    settings = get_settings()
    status = note_extraction.model_status()
    return {
        "audio_formats": sorted(SUPPORTED_EXTENSIONS),
        "midi_formats": [".mid", ".midi"],
        "max_upload_mb": settings.max_upload_mb,
        "max_duration_seconds": settings.max_audio_duration_seconds,
        "note_extraction": status,
        "stages": ["queued", "validating", "preprocessing", "transcribing", "postprocessing"],
        "terminal_states": ["completed", "failed", "cancelled", "analysis_only"],
        "produces_notes": status["available"],
        "pipeline": {
            "audio": "upload → FFmpeg decode → Basic Pitch → MusicDocument",
            "midi": "upload → mido parse → MusicDocument",
        },
    }


@router.post("/upload", status_code=status.HTTP_202_ACCEPTED)
async def upload_and_transcribe(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    title: Optional[str] = Query(default=None),
    artist: Optional[str] = Query(default=None),
    confirm_rights: bool = Query(default=True),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Upload audio and start a transcription job in one call."""
    data = await file.read()
    record, _created = assets.ingest_audio(
        db, data, file.filename or "upload.bin", title=title, artist=artist
    )
    job = transcription.create_job(
        db,
        asset_id=record.id,
        user_confirmed_rights=confirm_rights,
    )
    job_id = job.id
    background.add_task(
        _run_async_wrapper, job_id
    )
    payload = transcription.job_to_dict(job)
    payload["asset"] = {
        "asset_id": record.id,
        "filename": record.filename,
        "duration": record.duration,
        "sample_rate": record.sample_rate,
        "channels": record.channels,
        "codec": record.codec,
        "size_bytes": record.size_bytes,
    }
    return payload


async def _run_async_wrapper(job_id: str) -> None:
    try:
        await run_in_threadpool(_run_sync_job, job_id)
    except Exception:  # pragma: no cover - defensive
        logger.exception("background transcription failed for job %s", job_id)


@router.get("/jobs/{job_id}/result")
def job_result(job_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Return the MusicDocument produced by a finished job."""
    job = transcription.get_job(db, job_id)
    if job.status != "completed":
        raise AppError(
            "该作业尚未完成，没有可返回的谱面",
            code="TRANSCRIPTION_NOT_READY",
            status_code=409,
            details={"status": job.status, "error": job.error},
        )
    if not job.document_id:
        raise AppError(
            "作业已完成但没有关联谱面",
            code="TRANSCRIPTION_NO_DOCUMENT",
            status_code=409,
        )
    document = repository.load_document(db, job.document_id)
    return {
        "job_id": job.id,
        "document": document_to_dict(document),
        "events_produced": job.events_produced,
        "method": job.method,
        "confidence": job.confidence,
    }


def _run_sync_job(job_id: str) -> None:
    session = get_session_factory()()
    try:
        transcription.run_job(session, job_id)
    finally:
        session.close()


@router.post("/jobs", status_code=status.HTTP_201_CREATED)
def create_job(
    payload: JobCreateRequest,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    job = transcription.create_job(
        db,
        asset_id=payload.asset_id,
        track_id=payload.track_id,
        document_id=payload.document_id,
        user_confirmed_rights=payload.confirm_rights,
    )
    job_id = job.id

    async def _run() -> None:
        # The analysis is CPU-bound (decode + librosa + numba JIT). Running it on
        # the event loop would freeze every other request for its whole duration,
        # which is exactly what made the UI look stuck at "preprocessing".
        #
        # Background work runs after the response has started, so an exception here
        # cannot be turned into an HTTP error: it would surface to the client as a
        # reset connection with no access-log line. Log it and move on instead.
        try:
            await run_in_threadpool(_run_sync_job, job_id)
        except Exception:  # pragma: no cover - defensive
            logger.exception("background transcription failed for job %s", job_id)

    background.add_task(_run)
    return transcription.job_to_dict(job)


@router.get("/jobs")
def list_jobs(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    jobs = transcription.list_jobs(db, limit=limit, offset=offset)
    return {"items": [transcription.job_to_dict(job) for job in jobs], "total": len(jobs)}


@router.get("/jobs/{job_id}")
def get_job(job_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    return transcription.job_to_dict(transcription.get_job(db, job_id))


@router.post("/jobs/{job_id}/run")
def run_job(job_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Run synchronously - useful for tests and for retrying a failed job."""
    transcription.get_job(db, job_id)
    job = transcription.run_job(db, job_id)
    _raise_if_capacity_error(job)
    return transcription.job_to_dict(job)


def _raise_if_capacity_error(job) -> None:
    """Turn capacity problems into honest HTTP statuses instead of a 200 shell.

    A job that failed because the inference pool was full or the budget was
    exceeded is not a server error on the job - it is the service telling the
    caller to retry later / shorten the input.
    """
    error = job.error or ""
    if error.startswith("INFERENCE_BUSY"):
        raise ServiceBusyError(details={"job_id": job.id})
    if error.startswith("INFERENCE_TIMEOUT"):
        raise InferenceTimeoutError(details={"job_id": job.id})


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    return transcription.job_to_dict(transcription.cancel_job(db, job_id))

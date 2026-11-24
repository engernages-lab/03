"""Transcription job endpoints (real pipeline, no fabricated notes)."""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.db import get_db, get_session_factory
from app.services import transcription

router = APIRouter()


class JobCreateRequest(BaseModel):
    asset_id: Optional[str] = None
    track_id: Optional[str] = None
    document_id: Optional[str] = None
    confirm_rights: bool = Field(default=False)


@router.get("/models")
def models() -> Dict[str, Any]:
    """Report which transcription backends are actually available."""
    return {
        "note_extraction": {
            "available": False,
            "reason": "V1.0-A 未内置音高/节奏识别模型",
            "code": "REQUIRES_MODEL",
        },
        "signal_analysis": {
            "available": True,
            "method": "librosa.beat + onset detection",
            "produces_notes": False,
        },
        "midi_import": {"available": True, "produces_notes": True},
    }


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

    def _run() -> None:
        session = get_session_factory()()
        try:
            transcription.run_job(session, job_id)
        finally:
            session.close()

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
    return transcription.job_to_dict(job)


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    return transcription.job_to_dict(transcription.cancel_job(db, job_id))

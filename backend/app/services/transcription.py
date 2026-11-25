"""Transcription jobs: validation -> preprocessing -> analysis.

V1.0-A ships the pipeline and *real* signal analysis (tempo, onsets, energy).
It never emits score notes: no model is bundled, so a job completes in the
``analysis_only`` state with ``events_produced = 0`` and an explicit warning.
Fabricating notes would violate the project's acceptance rules.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.errors import AppError, NotFoundError, ValidationAppError
from app.core.logging import get_logger
from app.core.timeutils import utc_iso
from app.models.audio import AudioAssetRecord
from app.models.source import TranscriptionJobRecord
from app.schemas.music_document import new_id
from app.services import eligibility, library
from app.services.audio import assets as audio_assets
from app.services.audio import note_extraction
from app.services.music_document import repository

logger = get_logger("pocketscore.transcription")

ACTIVE_STATUSES = {"queued", "validating", "preprocessing", "analyzing"}


def create_job(
    session: Session,
    *,
    asset_id: Optional[str] = None,
    track_id: Optional[str] = None,
    document_id: Optional[str] = None,
    user_confirmed_rights: bool = False,
) -> TranscriptionJobRecord:
    if asset_id is None and track_id is None:
        raise ValidationAppError(
            "either asset_id or track_id is required", code="TRANSCRIPTION_TARGET_REQUIRED"
        )

    source_kind = "local_upload"
    if track_id:
        track = library.get_track(session, track_id)
        result = eligibility.evaluate(session, track, user_confirmed_rights=user_confirmed_rights)
        if result.status is not eligibility.EligibilityStatus.ELIGIBLE:
            raise AppError(
                "该曲目不允许进行 AI 扒谱",
                code=result.status.value,
                status_code=403 if result.status is eligibility.EligibilityStatus.PROVIDER_RESTRICTED else 409,
                details={"reasons": result.reasons, "permissions": result.permissions.as_dict()},
            )
        asset_id = track.audio_asset_id
        source_kind = "music_source"
        if asset_id is None:
            raise AppError(
                "该曲目没有可读取的音频资产", code="REQUIRES_USER_UPLOAD", status_code=409
            )

    asset = session.get(AudioAssetRecord, asset_id)
    if asset is None:
        raise NotFoundError(
            f"audio asset {asset_id!r} not found", code="AUDIO_ASSET_NOT_FOUND"
        )

    job = TranscriptionJobRecord(
        id=new_id("job_"),
        document_id=document_id,
        asset_id=asset.id,
        track_id=track_id,
        source_kind=source_kind,
        status="queued",
        progress=0,
    )
    session.add(job)
    session.commit()
    return job


def get_job(session: Session, job_id: str) -> TranscriptionJobRecord:
    job = session.get(TranscriptionJobRecord, job_id)
    if job is None:
        raise NotFoundError(
            f"transcription job {job_id!r} not found", code="TRANSCRIPTION_JOB_NOT_FOUND"
        )
    return job


def list_jobs(session: Session, limit: int = 50, offset: int = 0) -> List[TranscriptionJobRecord]:
    from sqlalchemy import select

    return list(
        session.execute(
            select(TranscriptionJobRecord)
            .order_by(TranscriptionJobRecord.created_at.desc())
            .limit(limit)
            .offset(offset)
        ).scalars()
    )


def run_job(session: Session, job_id: str) -> TranscriptionJobRecord:
    """Execute the pipeline synchronously (call from a worker thread)."""
    job = get_job(session, job_id)
    warnings: List[str] = []
    try:
        job.status = "validating"
        job.progress = 10
        session.commit()

        asset = session.get(AudioAssetRecord, job.asset_id) if job.asset_id else None
        if asset is None:
            raise ValidationAppError("audio asset is missing", code="AUDIO_ASSET_NOT_FOUND")
        path = audio_assets.absolute_path(asset)
        if not path.exists():
            raise ValidationAppError(
                "audio file is missing from storage", code="AUDIO_FILE_MISSING"
            )

        job.status = "preprocessing"
        job.progress = 35
        session.commit()

        analysis = audio_assets.asset_analysis(asset, normalise=True)
        warnings.extend(analysis.get("warnings") or [])
        job.analysis_json = json.dumps(analysis, ensure_ascii=False)

        job.status = "transcribing"
        job.progress = 60
        session.commit()

        status = note_extraction.model_status()
        if not status["available"]:
            job.method = "none"
            job.confidence = 0.0
            job.events_produced = 0
            warnings.append(
                "未检测到可用的扒谱模型（basic-pitch）。已完成信号分析（节拍/起音/能量），"
                "但没有生成任何音符，也不会以分析结果冒充扒谱。"
            )
            job.status = "analysis_only"
            job.progress = 100
            job.warnings_json = json.dumps(warnings, ensure_ascii=False)
            session.commit()
            return job

        notes = note_extraction.transcribe_file(path)

        job.status = "postprocessing"
        job.progress = 85
        session.commit()

        if not notes:
            job.method = note_extraction.MODEL_ID
            job.events_produced = 0
            job.status = "failed"
            job.progress = 100
            job.error = (
                "TRANSCRIPTION_EMPTY: 模型未从该音频中检测到任何音符"
                "（可能过于安静、噪声过多或并非乐器演奏）"
            )
            job.warnings_json = json.dumps(warnings, ensure_ascii=False)
            session.commit()
            return job

        tempo = float(analysis.get("bpm") or 120.0)
        document = note_extraction.build_document(
            notes,
            tempo=tempo,
            title=asset.title or (path.stem if path.stem else "AI 扒谱"),
            artist=asset.artist or "AI 扒谱",
            source_audio_id=asset.id,
            filename=asset.filename,
            extra_notes=f"由 {note_extraction.MODEL_NAME} {note_extraction.MODEL_VERSION} 识别",
        )
        repository.save_document(session, document)

        job.document_id = document.document_id
        job.events_produced = len(notes)
        job.method = note_extraction.MODEL_ID
        job.confidence = round(
            sum(note.amplitude for note in notes) / len(notes), 4
        )
        job.status = "completed"
        job.progress = 100
        warnings.append(
            f"{note_extraction.MODEL_NAME} {note_extraction.MODEL_VERSION} 识别出 {len(notes)} 个音符，"
            "已写入 MusicDocument；复音与多乐器精度有限，请在谱面中人工校对。"
        )
        job.warnings_json = json.dumps(warnings, ensure_ascii=False)
        session.commit()
        return job
    except AppError as exc:
        job.status = "failed"
        job.error = f"{exc.code}: {exc.message}"
        job.progress = 100
        job.warnings_json = json.dumps(warnings, ensure_ascii=False)
        session.commit()
        logger.warning("transcription job %s failed: %s", job.id, exc.message)
        return job
    except Exception as exc:  # pragma: no cover - unexpected
        session.rollback()
        job = get_job(session, job_id)
        job.status = "failed"
        job.error = f"INTERNAL_ERROR: {exc}"
        job.progress = 100
        session.commit()
        logger.exception("transcription job %s crashed", job_id)
        return job


def cancel_job(session: Session, job_id: str) -> TranscriptionJobRecord:
    job = get_job(session, job_id)
    if job.status in ACTIVE_STATUSES:
        job.status = "cancelled"
        job.progress = 100
        session.commit()
    return job


def job_to_dict(job: TranscriptionJobRecord) -> Dict[str, Any]:
    return {
        "job_id": job.id,
        "document_id": job.document_id,
        "asset_id": job.asset_id,
        "track_id": job.track_id,
        "source_kind": job.source_kind,
        "status": job.status,
        "progress": job.progress,
        "method": job.method,
        "confidence": job.confidence,
        "events_produced": job.events_produced,
        "analysis": json.loads(job.analysis_json) if job.analysis_json else None,
        "warnings": json.loads(job.warnings_json) if job.warnings_json else [],
        "error": job.error,
        "created_at": utc_iso(job.created_at),
        "updated_at": utc_iso(job.updated_at),
    }


def requires_model_response() -> Dict[str, Any]:
    """Explicit 501 payload for endpoints that would need a real model."""
    return {
        "code": "REQUIRES_MODEL",
        "message": "V1.0-A 未内置扒谱模型，无法生成音符；请使用 MIDI 导入或等待后续版本。",
        "available_now": ["midi_import", "signal_analysis"],
    }

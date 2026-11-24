"""Transcription job pipeline tests: real analysis, zero fabricated notes."""

from __future__ import annotations

import io
import math
import struct
import uuid
import wave

import pytest

from app.services import library
from app.services.sources.base import TrackDTO


def make_wav(duration: float = 1.0, sample_rate: int = 22050) -> bytes:
    frames = int(duration * sample_rate)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        payload = bytearray()
        for index in range(frames):
            value = int(0.5 * 32767 * math.sin(2 * math.pi * 440 * index / sample_rate))
            payload.extend(struct.pack("<h", value))
        handle.writeframes(bytes(payload))
    return buffer.getvalue()


@pytest.fixture()
def asset(client):
    response = client.post(
        "/api/v1/audio/upload",
        files={"file": ("tone.wav", make_wav(), "audio/wav")},
        params={"title": "分析音", "artist": "QA"},
    )
    assert response.status_code == 201
    return response.json()


def test_models_endpoint_is_honest(client):
    body = client.get("/api/v1/transcription/models").json()
    assert body["note_extraction"]["available"] is False
    assert body["note_extraction"]["code"] == "REQUIRES_MODEL"
    assert body["signal_analysis"]["available"] is True
    assert body["signal_analysis"]["produces_notes"] is False
    assert body["midi_import"]["produces_notes"] is True


def test_job_runs_and_produces_analysis_not_notes(client, asset):
    created = client.post("/api/v1/transcription/jobs", json={"asset_id": asset["asset_id"]})
    assert created.status_code == 201, created.text
    job = created.json()
    assert job["status"] in {"queued", "validating", "preprocessing", "analyzing", "analysis_only"}

    run = client.post(f"/api/v1/transcription/jobs/{job['job_id']}/run")
    assert run.status_code == 200
    result = run.json()
    assert result["status"] == "analysis_only"
    assert result["progress"] == 100
    assert result["events_produced"] == 0
    assert result["analysis"]["duration"] == pytest.approx(1.0, abs=0.1)
    assert result["analysis"]["sample_rate"] == 22050
    assert result["method"]
    assert any("未内置扒谱模型" in warning for warning in result["warnings"])


def test_job_requires_a_target(client):
    response = client.post("/api/v1/transcription/jobs", json={})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "TRANSCRIPTION_TARGET_REQUIRED"


def test_spotify_track_is_rejected_for_transcription(client, db_session):
    source = library.create_source(
        db_session, provider="spotify", display_name=f"sp-{uuid.uuid4().hex[:6]}", config={}
    )
    dto = TrackDTO(external_id="sp-track", title="Song", artist="Artist", duration=180.0)
    library.upsert_tracks(db_session, source.id, [dto])
    track = library.get_track(db_session, library.track_pk(source.id, "sp-track"))

    response = client.post(
        "/api/v1/transcription/jobs", json={"track_id": track.id, "confirm_rights": True}
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PROVIDER_RESTRICTED"


def test_local_track_requires_permission_before_job(client, db_session, asset):
    source = library.create_source(
        db_session, provider="local", display_name=f"local-{uuid.uuid4().hex[:6]}", config={}
    )
    dto = TrackDTO(
        external_id="local-track", title="本地曲", artist="QA", duration=60.0,
        audio_asset_id=asset["asset_id"], is_local=True,
    )
    library.upsert_tracks(db_session, source.id, [dto])
    track = library.get_track(db_session, library.track_pk(source.id, "local-track"))

    blocked = client.post("/api/v1/transcription/jobs", json={"track_id": track.id})
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "REQUIRES_PERMISSION"

    # grant the source-wide AI permission, then the job is accepted
    library.update_permissions(db_session, source.id, ai_processing_permission=True)
    allowed = client.post(
        "/api/v1/transcription/jobs", json={"track_id": track.id, "document_id": None}
    )
    assert allowed.status_code == 201, allowed.text
    job = allowed.json()
    assert job["asset_id"] == asset["asset_id"]
    assert job["source_kind"] == "music_source"


def test_job_listing_and_missing_job(client, asset):
    client.post("/api/v1/transcription/jobs", json={"asset_id": asset["asset_id"]})
    listing = client.get("/api/v1/transcription/jobs")
    assert listing.status_code == 200
    assert listing.json()["total"] >= 1

    missing = client.get("/api/v1/transcription/jobs/job-missing")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "TRANSCRIPTION_JOB_NOT_FOUND"


def test_cancel_active_job(client, db_session, asset):
    from app.models.source import TranscriptionJobRecord
    from app.schemas.music_document import new_id

    job = TranscriptionJobRecord(
        id=new_id("job_"), asset_id=asset["asset_id"], status="analyzing", progress=50
    )
    db_session.add(job)
    db_session.commit()

    cancelled = client.post(f"/api/v1/transcription/jobs/{job.id}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"


def test_cancel_completed_job_is_a_noop(client, asset):
    created = client.post("/api/v1/transcription/jobs", json={"asset_id": asset["asset_id"]}).json()
    client.post(f"/api/v1/transcription/jobs/{created['job_id']}/run")
    cancelled = client.post(f"/api/v1/transcription/jobs/{created['job_id']}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "analysis_only"

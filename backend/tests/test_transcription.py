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


def make_wav(duration: float = 1.0, sample_rate: int = 22050, amplitude: float = 0.5) -> bytes:
    frames = int(duration * sample_rate)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        payload = bytearray()
        for index in range(frames):
            value = int(amplitude * 32767 * math.sin(2 * math.pi * 440 * index / sample_rate))
            payload.extend(struct.pack("<h", value))
        handle.writeframes(bytes(payload))
    return buffer.getvalue()


def make_melody_wav(
    notes=((60, 0.0), (64, 0.4), (67, 0.8), (72, 1.2)),
    note_seconds: float = 0.4,
    sample_rate: int = 22050,
) -> bytes:
    """A real 4-note melody with harmonics so the model has something to hear."""
    duration = max(start for _pitch, start in notes) + note_seconds + 0.2
    samples = [0.0] * int(duration * sample_rate)
    for pitch, start in notes:
        frequency = 440.0 * 2 ** ((pitch - 69) / 12)
        offset = int(start * sample_rate)
        length = int(note_seconds * sample_rate)
        for index in range(length):
            t = index / sample_rate
            envelope = min(1.0, t / 0.02, (note_seconds - t) / 0.05)
            value = (
                0.6 * math.sin(2 * math.pi * frequency * t)
                + 0.25 * math.sin(2 * math.pi * 2 * frequency * t)
                + 0.1 * math.sin(2 * math.pi * 3 * frequency * t)
            )
            samples[offset + index] += value * max(0.0, envelope)
    peak = max(1e-9, max(abs(value) for value in samples))
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(
            b"".join(
                struct.pack("<h", int(max(-1.0, min(1.0, value / peak * 0.9)) * 32767))
                for value in samples
            )
        )
    return buffer.getvalue()


@pytest.fixture()
def melody_asset(client):
    response = client.post(
        "/api/v1/audio/upload",
        files={"file": ("melody.wav", make_melody_wav(), "audio/wav")},
        params={"title": "四音旋律", "artist": "QA"},
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture()
def asset(client):
    response = client.post(
        "/api/v1/audio/upload",
        files={"file": ("tone.wav", make_wav(), "audio/wav")},
        params={"title": "分析音", "artist": "QA"},
    )
    assert response.status_code == 201
    return response.json()


def test_models_endpoint_reports_the_real_model(client):
    body = client.get("/api/v1/transcription/models").json()
    model = body["note_extraction"]
    # The capability must reflect the actual install state, not a hard-coded flag.
    from app.services.audio import note_extraction

    expected = note_extraction.model_status()["available"]
    assert model["available"] is expected
    assert model["code"] == (None if expected else "REQUIRES_MODEL")
    assert model["model_id"] == "basic_pitch"
    assert model["polyphonic"] is True
    assert body["signal_analysis"]["produces_notes"] is False
    assert body["midi_import"]["produces_notes"] is True


def test_capabilities_endpoint_describes_upload_contract(client):
    body = client.get("/api/v1/transcription/capabilities").json()
    assert ".mp3" in body["audio_formats"]
    assert ".wav" in body["audio_formats"]
    assert ".flac" in body["audio_formats"]
    assert ".mid" in body["midi_formats"]
    assert body["max_upload_mb"] > 0
    assert body["max_duration_seconds"] > 0
    assert "transcribing" in body["stages"]
    assert body["pipeline"]["audio"].startswith("upload")
    assert body["note_extraction"]["model_id"] == "basic_pitch"


def test_job_produces_real_notes(client, melody_asset):
    """The pipeline must turn audio into MusicDocument events, not analysis only."""
    pytest.importorskip("basic_pitch", reason="audio transcription model not installed")
    created = client.post(
        "/api/v1/transcription/jobs", json={"asset_id": melody_asset["asset_id"]}
    )
    assert created.status_code == 201, created.text
    job = created.json()

    run = client.post(f"/api/v1/transcription/jobs/{job['job_id']}/run")
    assert run.status_code == 200
    result = run.json()
    assert result["status"] == "completed", result
    assert result["events_produced"] > 0
    assert result["method"] == "basic_pitch"
    assert result["document_id"]

    # the produced document is a real MusicDocument with the detected pitches
    document = client.get(f"/api/v1/documents/{result['document_id']}").json()
    pitches = sorted({event["pitch"] for event in document["events"] if event["pitch"] is not None})
    assert 60 in pitches and 67 in pitches
    assert document["source_metadata"]["kind"] == "transcription"
    assert document["source_metadata"]["recognition_model"] == "basic_pitch"

    payload = client.get(f"/api/v1/transcription/jobs/{job['job_id']}/result").json()
    assert payload["document"]["document_id"] == result["document_id"]
    assert payload["events_produced"] == result["events_produced"]


def test_silent_audio_fails_with_a_clear_reason(client):
    silent = make_wav(duration=0.5, amplitude=0.0)
    asset = client.post(
        "/api/v1/audio/upload",
        files={"file": ("silence.wav", silent, "audio/wav")},
    )
    assert asset.status_code == 201, asset.text
    job = client.post(
        "/api/v1/transcription/jobs", json={"asset_id": asset.json()["asset_id"]}
    ).json()
    result = client.post(f"/api/v1/transcription/jobs/{job['job_id']}/run").json()
    assert result["status"] in {"failed", "analysis_only"}
    assert result["events_produced"] == 0
    assert result["error"] or result["warnings"]


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
    # a finished job keeps its terminal state; cancel is a no-op
    assert cancelled.json()["status"] == "completed"

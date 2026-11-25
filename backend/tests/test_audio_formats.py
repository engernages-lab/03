"""Real-format upload tests.

Every fixture is a genuine encoded stream produced by FFmpeg (see
``scripts/make_audio_fixtures.py``), so a passing test means the backend really
decoded that codec instead of trusting the file extension.
"""

from __future__ import annotations

import io
import wave
from pathlib import Path

import pytest

pytest.importorskip("basic_pitch", reason="audio transcription model not installed")  # noqa: E402

from app.services.audio import note_extraction
from app.services.audio.assets import ingest_audio
from app.services.audio.probe import probe_audio

FIXTURES = Path(__file__).resolve().parents[2] / "tests" / "fixtures"

CODEC_CASES = [
    ("melody.mp3", "mp3"),
    ("melody.wav", "pcm"),
    ("melody.flac", "flac"),
    ("melody.m4a", "aac"),
    ("melody.ogg", "vorbis"),
    ("melody.opus", "opus"),
]


def _read(name: str) -> bytes:
    path = FIXTURES / name
    assert path.exists(), f"missing fixture {name}; run scripts/make_audio_fixtures.py"
    return path.read_bytes()


@pytest.mark.parametrize("filename,codec_hint", CODEC_CASES)
def test_upload_decodes_every_supported_format(client, filename, codec_hint):
    response = client.post(
        "/api/v1/audio/upload",
        files={"file": (filename, _read(filename), "application/octet-stream")},
        params={"title": f"format-{codec_hint}"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["duration"] == pytest.approx(1.8, abs=0.25), filename
    assert body["sample_rate"] > 0
    assert body["channels"] >= 1
    assert body["size_bytes"] > 0


@pytest.mark.parametrize("filename,_codec", CODEC_CASES)
def test_probe_reports_real_codec(filename, _codec):
    probe = probe_audio(FIXTURES / filename)
    assert probe.duration == pytest.approx(1.8, abs=0.25)
    assert probe.codec, f"{filename} should report a codec"
    assert probe.sample_rate > 0


def test_mp3_transcribes_to_notes(client):
    """A compressed file must survive decode -> model -> MusicDocument."""
    asset = client.post(
        "/api/v1/audio/upload",
        files={"file": ("melody.mp3", _read("melody.mp3"), "audio/mpeg")},
    ).json()
    job = client.post(
        "/api/v1/transcription/jobs", json={"asset_id": asset["asset_id"]}
    ).json()
    result = client.post(f"/api/v1/transcription/jobs/{job['job_id']}/run").json()
    assert result["status"] == "completed", result
    assert result["events_produced"] >= 3

    document = client.get(f"/api/v1/documents/{result['document_id']}").json()
    pitches = {event["pitch"] for event in document["events"]}
    assert {60, 64, 67}.issubset(pitches), sorted(pitches)


def test_fake_extension_is_rejected(client):
    """Text renamed to .mp3 must not be accepted as audio."""
    payload = b"this is definitely not audio" * 100
    response = client.post(
        "/api/v1/audio/upload",
        files={"file": ("fake.mp3", payload, "audio/mpeg")},
    )
    assert response.status_code in (415, 422), response.text
    assert response.json()["error"]["code"] in {
        "UNSUPPORTED_MEDIA_TYPE",
        "AUDIO_PROBE_FAILED",
    }


def test_unsupported_extension_is_rejected(client):
    response = client.post(
        "/api/v1/audio/upload",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "UNSUPPORTED_MEDIA_TYPE"


def test_empty_file_is_rejected(client):
    response = client.post(
        "/api/v1/audio/upload", files={"file": ("empty.wav", b"", "audio/wav")}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "AUDIO_PROBE_FAILED"


def test_truncated_wav_is_rejected(client):
    data = _read("melody.wav")[:200]
    response = client.post(
        "/api/v1/audio/upload", files={"file": ("broken.wav", data, "audio/wav")}
    )
    assert response.status_code in (415, 422)


def test_duration_limit_is_enforced(db_session, monkeypatch):
    from app.services.audio import assets as audio_assets

    # unique bytes so the checksum cache does not short-circuit validation
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        handle.writeframes(b"\x10\x00" * 8000 * 2)  # 2 s at 8 kHz
    settings = audio_assets.get_settings()
    monkeypatch.setattr(
        audio_assets,
        "get_settings",
        lambda: settings.model_copy(update={"max_audio_duration_seconds": 0.5}),
    )
    with pytest.raises(Exception) as exc:
        ingest_audio(db_session, buffer.getvalue(), "long.wav")
    assert getattr(exc.value, "code", "") == "AUDIO_TOO_LONG"


def test_upload_and_transcribe_endpoint(client):
    """POST /transcription/upload performs upload + job creation in one call."""
    response = client.post(
        "/api/v1/transcription/upload",
        files={"file": ("melody.wav", _read("melody.wav"), "audio/wav")},
        params={"title": "一体化上传"},
    )
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["asset"]["duration"] == pytest.approx(1.8, abs=0.25)
    assert body["job_id"].startswith("job_")

    # run it synchronously to assert the end-to-end result
    result = client.post(f"/api/v1/transcription/jobs/{body['job_id']}/run").json()
    assert result["status"] == "completed"
    assert result["events_produced"] > 0


def test_result_endpoint_requires_completion(client, db_session):
    from app.services import transcription

    asset = client.post(
        "/api/v1/audio/upload",
        files={"file": ("pending.wav", _read("melody.wav"), "audio/wav")},
    ).json()
    # create the job directly so no background task runs it
    job = transcription.create_job(db_session, asset_id=asset["asset_id"])
    response = client.get(f"/api/v1/transcription/jobs/{job.id}/result")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "TRANSCRIPTION_NOT_READY"


def test_model_output_is_not_random(melody_fixture_path):
    """Two runs on the same audio must agree (a random generator would not)."""
    first = note_extraction.transcribe_file(melody_fixture_path)
    second = note_extraction.transcribe_file(melody_fixture_path)
    assert [(n.pitch, round(n.start, 3)) for n in first] == [
        (n.pitch, round(n.start, 3)) for n in second
    ]


@pytest.fixture(scope="module")
def melody_fixture_path() -> Path:
    return FIXTURES / "melody.wav"

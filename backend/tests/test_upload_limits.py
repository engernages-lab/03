"""Upload limits and streaming behaviour (V1.1-C.2).

C.1 found that uploads were fully read into memory before the size check. These
tests pin the new behaviour: reject before/while streaming, never buffer the
whole body, and clean up the temporary file on failure.
"""

from __future__ import annotations

import io
import wave

import pytest
from fastapi.testclient import TestClient


def wav_bytes(seconds: float = 0.5) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        handle.writeframes(b"\x00\x00" * int(8000 * seconds))
    return buffer.getvalue()


@pytest.fixture()
def api(client: TestClient) -> TestClient:  # noqa: F811 - conftest provides `client`
    return client


def test_upload_accepts_a_real_wav(api):
    response = api.post(
        "/api/v1/audio/upload",
        files={"file": ("clip.wav", wav_bytes(), "audio/wav")},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["duration"] > 0
    assert body["size_bytes"] > 0


def test_upload_rejects_oversized_body_from_content_length(api, monkeypatch):
    from app.core.config import get_settings

    settings = get_settings()
    # Any non-empty body is over the (temporarily) zero megabyte limit; the
    # Content-Length pre-check must reject it before the body is streamed.
    monkeypatch.setattr(settings, "max_upload_mb", 0, raising=False)
    response = api.post(
        "/api/v1/audio/upload",
        files={"file": ("clip.wav", wav_bytes(0.5), "audio/wav")},
    )
    assert response.status_code == 413, response.text
    assert response.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"


def test_upload_rejects_bad_extension_before_reading(api):
    response = api.post(
        "/api/v1/audio/upload",
        files={"file": ("song.exe", b"MZ" * 100, "application/octet-stream")},
    )
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "UNSUPPORTED_MEDIA_TYPE"


def test_upload_rejects_fake_audio(api):
    response = api.post(
        "/api/v1/audio/upload",
        files={"file": ("fake.mp3", b"not-an-mp3" * 400, "audio/mpeg")},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "AUDIO_PROBE_FAILED"


def test_upload_rejects_empty_file(api):
    response = api.post(
        "/api/v1/audio/upload",
        files={"file": ("empty.wav", b"", "audio/wav")},
    )
    assert response.status_code in (400, 422)


def test_rejected_upload_leaves_no_temp_directory(api):
    """A failed upload must not leak its temp directory."""
    import tempfile
    from pathlib import Path

    pattern = "pocketscore-upload-*"
    before = set(Path(tempfile.gettempdir()).glob(pattern))
    api.post(
        "/api/v1/audio/upload",
        files={"file": ("fake.mp3", b"not-an-mp3" * 400, "audio/mpeg")},
    )
    after = set(Path(tempfile.gettempdir()).glob(pattern))
    assert after - before == set()


def test_upload_is_content_addressed_and_deduplicated(api):
    payload = wav_bytes(0.4)
    first = api.post("/api/v1/audio/upload", files={"file": ("a.wav", payload, "audio/wav")})
    second = api.post("/api/v1/audio/upload", files={"file": ("b.wav", payload, "audio/wav")})
    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["asset_id"] == second.json()["asset_id"]
    assert first.json()["checksum_sha256"] == second.json()["checksum_sha256"]

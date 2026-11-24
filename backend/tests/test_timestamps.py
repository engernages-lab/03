"""API timestamps must be UTC-aware.

SQLite returns naive datetimes even for ``DateTime(timezone=True)`` columns, so
a naive value leaks through as "2026-11-24T14:33:00" and browsers read it as
local time (an 8 hour error in UTC+8). Every timestamp the API emits must carry
an explicit UTC designator.
"""

from __future__ import annotations

import io
import math
import struct
import wave
from datetime import datetime, timedelta, timezone

import pytest

from app.core.timeutils import as_utc, utc_iso


def make_wav(duration: float = 0.5, sample_rate: int = 22050) -> bytes:
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
        files={"file": ("tz.wav", make_wav(), "audio/wav")},
        params={"title": "时区测试音"},
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture()
def track(client):
    response = client.post(
        "/api/v1/library/import",
        files={"file": ("tz.wav", make_wav(), "audio/wav")},
        data={"title": "时区测试曲"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_utc_iso_marks_naive_values_as_utc():
    assert utc_iso(datetime(2026, 11, 24, 14, 33, 0)) == "2026-11-24T14:33:00Z"


def test_utc_iso_converts_aware_values():
    shanghai = timezone(timedelta(hours=8))
    assert utc_iso(datetime(2026, 11, 24, 22, 33, 0, tzinfo=shanghai)) == "2026-11-24T14:33:00Z"


def test_utc_iso_handles_none():
    assert utc_iso(None) is None
    assert as_utc(None) is None


def test_transcription_job_timestamps_are_utc(client, asset):
    response = client.post(
        "/api/v1/transcription/jobs",
        json={"asset_id": asset["asset_id"], "confirm_rights": True},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    for key in ("created_at", "updated_at"):
        assert body[key].endswith("Z"), f"{key}={body[key]}"
        datetime.fromisoformat(body[key].replace("Z", "+00:00"))


def test_playlist_timestamp_is_utc(client):
    created = client.post("/api/v1/library/playlists", json={"name": "时区测试歌单"})
    assert created.status_code == 201, created.text
    assert created.json()["created_at"].endswith("Z")

    listed = client.get("/api/v1/library/playlists").json()["items"]
    assert listed and listed[0]["created_at"].endswith("Z")


def test_history_timestamp_is_utc(client, track):
    recorded = client.post("/api/v1/library/history", json={"track_id": track["track_id"]})
    assert recorded.status_code in (200, 201), recorded.text
    assert recorded.json()["played_at"].endswith("Z")

    history = client.get("/api/v1/library/history").json()["items"]
    assert history and history[0]["played_at"].endswith("Z")

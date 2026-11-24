"""Audio pipeline tests: synthetic WAV files, real probing and real DSP."""

from __future__ import annotations

import io
import math
import struct
import wave

import pytest

from app.core.errors import ValidationAppError
from app.services.audio.probe import (
    analyse,
    decode_mono,
    normalize_peak,
    probe_audio,
    validate_extension,
    waveform_buckets,
)


def make_wav(
    *,
    duration: float = 2.0,
    sample_rate: int = 44100,
    channels: int = 2,
    frequency: float = 440.0,
    amplitude: float = 0.5,
) -> bytes:
    frames = int(duration * sample_rate)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        payload = bytearray()
        for index in range(frames):
            value = int(amplitude * 32767 * math.sin(2 * math.pi * frequency * index / sample_rate))
            for _ in range(channels):
                payload.extend(struct.pack("<h", value))
        handle.writeframes(bytes(payload))
    return buffer.getvalue()


def write_wav(tmp_path, name: str = "tone.wav", **kwargs):
    path = tmp_path / name
    path.write_bytes(make_wav(**kwargs))
    return path


# ---------------------------------------------------------------------------
# probing
# ---------------------------------------------------------------------------

def test_probe_reports_real_properties(tmp_path):
    path = write_wav(tmp_path, duration=2.0, sample_rate=44100, channels=2)
    result = probe_audio(path)
    assert result.duration == pytest.approx(2.0, abs=0.02)
    assert result.sample_rate == 44100
    assert result.channels == 2
    assert result.method in {"soundfile", "wave", "ffmpeg"}


def test_probe_mono_44k(tmp_path):
    path = write_wav(tmp_path, duration=0.5, sample_rate=44100, channels=1)
    result = probe_audio(path)
    assert result.channels == 1
    assert result.duration == pytest.approx(0.5, abs=0.02)


def test_probe_rejects_empty_file(tmp_path):
    path = tmp_path / "empty.wav"
    path.write_bytes(b"")
    with pytest.raises(ValidationAppError):
        probe_audio(path)


def test_probe_rejects_corrupt_file(tmp_path):
    path = tmp_path / "broken.wav"
    path.write_bytes(b"not a wav file at all")
    with pytest.raises(ValidationAppError) as exc:
        probe_audio(path)
    assert exc.value.code == "AUDIO_PROBE_FAILED"


def test_validate_extension_accepts_all_supported():
    for ext in (".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".opus"):
        assert validate_extension(f"song{ext}") == ext


def test_validate_extension_rejects_unknown():
    with pytest.raises(Exception) as exc:
        validate_extension("song.txt")
    assert getattr(exc.value, "status_code", None) == 415


# ---------------------------------------------------------------------------
# decoding / normalisation / features
# ---------------------------------------------------------------------------

def test_decode_mono_downmixes_and_resamples(tmp_path):
    path = write_wav(tmp_path, duration=1.0, sample_rate=44100, channels=2)
    audio, sr = decode_mono(path, sample_rate=22050)
    assert sr == 22050
    assert audio.ndim == 1
    assert abs(len(audio) / sr - 1.0) < 0.05


def test_normalize_peak_scales_to_target(tmp_path):
    import numpy as np

    path = write_wav(tmp_path, duration=0.2, amplitude=0.1)
    audio, _sr = decode_mono(path)
    normalized = normalize_peak(audio, target_dbfs=-1.0)
    peak = float(np.max(np.abs(normalized)))
    assert peak == pytest.approx(10 ** (-1.0 / 20.0), rel=1e-4)
    assert peak <= 1.0


def test_normalize_peak_rejects_silence():
    import numpy as np

    with pytest.raises(ValidationAppError) as exc:
        normalize_peak(np.zeros(1024, dtype="float32"))
    assert exc.value.code == "AUDIO_SILENT"


def test_waveform_buckets_are_real_peaks(tmp_path):
    path = write_wav(tmp_path, duration=0.5)
    audio, _sr = decode_mono(path)
    peaks = waveform_buckets(audio, buckets=64)
    assert len(peaks) == 64
    assert all(0.0 <= value <= 1.0 for value in peaks)
    assert max(peaks) > 0.1  # a 440Hz tone at 0.5 amplitude is clearly non-silent


def test_analyse_returns_signal_statistics(tmp_path):
    path = write_wav(tmp_path, duration=2.0)
    audio, sr = decode_mono(path)
    result = analyse(audio, sr)
    assert result["duration"] == pytest.approx(2.0, abs=0.05)
    assert result["rms"] > 0
    assert result["peak"] > 0
    assert result["onsets"] >= 0
    if result["bpm"] is not None:
        assert 20 <= result["bpm"] <= 400
    assert "warnings" in result


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

def test_api_upload_probe_waveform_stream_delete(client, tmp_path):
    payload = make_wav(duration=1.0)
    response = client.post(
        "/api/v1/audio/upload",
        files={"file": ("tone.wav", payload, "audio/wav")},
        params={"title": "测试音", "artist": "QA"},
    )
    assert response.status_code == 201, response.text
    asset = response.json()
    assert asset["duration"] == pytest.approx(1.0, abs=0.05)
    assert asset["sample_rate"] == 44100
    assert asset["channels"] == 2
    assert asset["title"] == "测试音"
    assert asset["stream_url"].endswith("/stream")

    # identical bytes must deduplicate to the same asset
    again = client.post(
        "/api/v1/audio/upload", files={"file": ("tone.wav", payload, "audio/wav")}
    )
    assert again.status_code == 201
    assert again.json()["asset_id"] == asset["asset_id"]

    probe = client.post(
        "/api/v1/audio/probe", files={"file": ("probe.wav", payload, "audio/wav")}
    )
    assert probe.status_code == 200
    assert probe.json()["sample_rate"] == 44100

    waveform = client.get(f"/api/v1/audio/assets/{asset['asset_id']}/waveform")
    assert waveform.status_code == 200
    body = waveform.json()
    assert body["buckets"] == len(body["peaks"]) == 600

    full = client.get(f"/api/v1/audio/assets/{asset['asset_id']}/stream")
    assert full.status_code == 200

    ranged = client.get(
        f"/api/v1/audio/assets/{asset['asset_id']}/stream", headers={"Range": "bytes=0-1023"}
    )
    assert ranged.status_code == 206
    assert len(ranged.content) == 1024
    assert ranged.headers["content-range"].startswith("bytes 0-1023/")

    listed = client.get("/api/v1/audio/assets")
    assert listed.status_code == 200
    assert any(item["asset_id"] == asset["asset_id"] for item in listed.json()["items"])

    deleted = client.delete(f"/api/v1/audio/assets/{asset['asset_id']}")
    assert deleted.status_code == 204
    assert client.get(f"/api/v1/audio/assets/{asset['asset_id']}").status_code == 404


def test_api_upload_rejects_unsupported_extension(client):
    response = client.post(
        "/api/v1/audio/upload", files={"file": ("notes.txt", b"hello", "text/plain")}
    )
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "UNSUPPORTED_MEDIA_TYPE"


def test_api_analyze_endpoint(client):
    payload = make_wav(duration=0.6)
    asset = client.post(
        "/api/v1/audio/upload", files={"file": ("tone.wav", payload, "audio/wav")}
    ).json()
    response = client.post(f"/api/v1/audio/assets/{asset['asset_id']}/analyze")
    assert response.status_code == 200
    body = response.json()
    assert "analysis" in body
    assert body["note"].startswith("这是信号分析结果")
    assert body["analysis"]["duration"] > 0


def test_api_missing_asset_returns_404(client):
    response = client.get("/api/v1/audio/assets/nope")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "AUDIO_ASSET_NOT_FOUND"

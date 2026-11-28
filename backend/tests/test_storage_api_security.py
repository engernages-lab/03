"""API-level storage security tests (V1.1-C.2.3.4.2).

The database is tampered on purpose (inside a temp DB) so we can prove that a
malicious ``stored_path`` can no longer read, stream or delete anything outside
the storage root, and that error bodies never leak absolute locations.
"""

from __future__ import annotations

import io
import json
import struct
import wave

import pytest


def _wav(seconds: float = 0.3, rate: int = 8000) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b"".join(struct.pack("<h", 1200) for _ in range(int(seconds * rate))))
    return buffer.getvalue()


@pytest.fixture()
def secured(tmp_path, monkeypatch):
    """Isolated app whose storage root can be probed from the outside."""
    from app.core import config as config_module
    from app.core import db as db_module

    root = tmp_path / "app-data"
    storage = root / "storage"
    (storage / "audio").mkdir(parents=True)
    monkeypatch.setenv("POCKETSCORE_ENVIRONMENT", "test")
    monkeypatch.setenv("POCKETSCORE_DATABASE_URL", f"sqlite:///{(root / 'pocketscore.db').as_posix()}")
    monkeypatch.setenv("POCKETSCORE_STORAGE_DIR", str(storage))
    monkeypatch.setenv("POCKETSCORE_ACCESS_GATE_MODE", "off")
    monkeypatch.setenv("POCKETSCORE_MODEL_PRELOAD", "false")
    config_module.get_settings.cache_clear()
    db_module.dispose_engine()

    from app.core.db import get_session_factory, init_db

    init_db()

    from fastapi.testclient import TestClient

    from app.main import app

    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret.wav"
    secret.write_bytes(_wav(0.1))
    plain_secret = outside / "plain.txt"
    plain_secret.write_text("TOP-SECRET-CONTENT", encoding="utf-8")

    client = TestClient(app)
    yield {
        "client": client,
        "storage": storage,
        "outside": outside,
        "secret": secret,
        "plain_secret": plain_secret,
        "session_factory": lambda: get_session_factory()(),
    }
    client.close()
    config_module.get_settings.cache_clear()
    db_module.dispose_engine()


def _tamper(store: dict, asset_id: str, stored_path: str) -> None:
    from app.models.audio import AudioAssetRecord

    session = store["session_factory"]()
    record = session.get(AudioAssetRecord, asset_id)
    record.stored_path = stored_path
    session.commit()
    session.close()


def _upload(store: dict, name: str = "song.wav", payload: bytes | None = None) -> dict:
    response = store["client"].post(
        "/api/v1/audio/upload",
        files={"file": (name, payload if payload is not None else _wav(), "audio/wav")},
    )
    assert response.status_code == 201, response.text
    return response.json()


# --------------------------------------------------------------- baseline


def test_valid_upload_and_playback_still_work(secured):
    payload = _upload(secured)
    stored = payload["asset_id"]

    stream = secured["client"].get(f"/api/v1/audio/assets/{stored}/stream")
    assert stream.status_code == 200
    assert stream.content[:4] == b"RIFF"

    waveform = secured["client"].get(f"/api/v1/audio/assets/{stored}/waveform")
    assert waveform.status_code == 200

    from app.models.audio import AudioAssetRecord

    session = secured["session_factory"]()
    record = session.get(AudioAssetRecord, stored)
    assert record.stored_path.startswith("audio/")
    assert (secured["storage"] / record.stored_path).is_file()
    session.close()


def test_upload_filename_is_sanitised_end_to_end(secured):
    payload = _upload(secured, name="../../escape.wav")
    assert payload["filename"] == "escape.wav"
    assert "/" not in payload["filename"] and "\\" not in payload["filename"]
    # nothing was written outside the store
    assert not list(secured["outside"].glob("escape.wav"))


# --------------------------------------------------------------- traversal


@pytest.mark.parametrize(
    "stored_path",
    [
        "../outside/secret.wav",
        "../../outside/secret.wav",
        r"..\..\outside\secret.wav",
        "audio/../../outside/secret.wav",
        "audio/./../../outside/secret.wav",
    ],
)
def test_tampered_relative_path_cannot_be_streamed(secured, stored_path):
    asset = _upload(secured)
    _tamper(secured, asset["asset_id"], stored_path)

    stream = secured["client"].get(f"/api/v1/audio/assets/{asset['asset_id']}/stream")
    assert stream.status_code == 400
    assert stream.json()["error"]["code"] == "STORAGE_PATH_INVALID"
    assert b"RIFF" not in stream.content

    waveform = secured["client"].get(f"/api/v1/audio/assets/{asset['asset_id']}/waveform")
    assert waveform.status_code == 400


def test_tampered_absolute_path_is_rejected(secured):
    asset = _upload(secured)
    _tamper(secured, asset["asset_id"], str(secured["secret"]))
    response = secured["client"].get(f"/api/v1/audio/assets/{asset['asset_id']}/stream")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "STORAGE_PATH_INVALID"


def test_tampered_path_with_nul_byte_is_rejected(secured):
    asset = _upload(secured)
    _tamper(secured, asset["asset_id"], "audio/ab/x.wav\x00.png")
    response = secured["client"].get(f"/api/v1/audio/assets/{asset['asset_id']}/stream")
    assert response.status_code == 400


def test_tampered_path_cannot_delete_outside_file(secured):
    asset = _upload(secured)
    target = secured["plain_secret"]
    _tamper(secured, asset["asset_id"], "../../outside/plain.txt")

    response = secured["client"].delete(f"/api/v1/audio/assets/{asset['asset_id']}")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "STORAGE_PATH_INVALID"
    assert target.is_file(), "the file outside the storage root must survive"
    assert target.read_text(encoding="utf-8") == "TOP-SECRET-CONTENT"


def test_missing_file_still_reports_a_business_error(secured):
    asset = _upload(secured)
    from app.models.audio import AudioAssetRecord

    session = secured["session_factory"]()
    record = session.get(AudioAssetRecord, asset["asset_id"])
    (secured["storage"] / record.stored_path).unlink()
    session.close()

    response = secured["client"].get(f"/api/v1/audio/assets/{asset['asset_id']}/stream")
    assert response.status_code == 410
    assert response.json()["error"]["code"] == "AUDIO_FILE_MISSING"


# --------------------------------------------------------------- leakage


FORBIDDEN = ("/data/", "backend/", "Traceback", "FileNotFoundError", "PermissionError", "storage/audio")


@pytest.mark.parametrize(
    "stored_path",
    ["../outside/secret.wav", "audio/ab/x.wav\x00.png", "audio/../..", "/etc/passwd"],
)
def test_error_bodies_never_leak_paths(secured, stored_path):
    asset = _upload(secured)
    _tamper(secured, asset["asset_id"], stored_path)
    token = "".join(chr(alpha) for alpha in (115, 116, 111, 114, 97, 103, 101))  # "storage"
    for path in (
        f"/api/v1/audio/assets/{asset['asset_id']}/stream",
        f"/api/v1/audio/assets/{asset['asset_id']}/waveform",
    ):
        body = secured["client"].get(path).text
        for token_text in FORBIDDEN:
            assert token_text not in body, (path, token_text, body[:200])
        # the storage root must not be echoed in any shape
        assert str(secured["storage"]) not in body
        assert token not in json.loads(body)["error"].get("details", {}).get("reason", "")


def test_corrupt_audio_decode_error_is_scrubbed(secured):
    asset = _upload(secured)
    from app.models.audio import AudioAssetRecord

    session = secured["session_factory"]()
    record = session.get(AudioAssetRecord, asset["asset_id"])
    (secured["storage"] / record.stored_path).write_bytes(b"RIFFnot-really-a-wave" * 40)
    session.close()

    response = secured["client"].get(f"/api/v1/audio/assets/{asset['asset_id']}/waveform")
    assert response.status_code >= 400
    body = response.text
    assert str(secured["storage"]) not in body
    assert "D:\\" not in body and "/data/" not in body


def test_probe_rejects_disguised_file_without_leaking(secured):
    response = secured["client"].post(
        "/api/v1/audio/probe",
        files={"file": ("fake.wav", b"definitely not audio" * 30, "audio/wav")},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "AUDIO_PROBE_FAILED"
    assert str(secured["storage"]) not in response.text


# --------------------------------------------------------------- delete flow


def test_normal_delete_removes_only_the_asset_file(secured):
    asset = _upload(secured)
    from app.models.audio import AudioAssetRecord

    session = secured["session_factory"]()
    record = session.get(AudioAssetRecord, asset["asset_id"])
    file_path = secured["storage"] / record.stored_path
    session.close()
    assert file_path.is_file()

    keeper = secured["storage"] / "audio" / "keeper.wav"
    keeper.write_bytes(_wav())

    response = secured["client"].delete(f"/api/v1/audio/assets/{asset['asset_id']}")
    assert response.status_code == 204
    assert not file_path.exists()
    assert keeper.is_file()
    assert secured["plain_secret"].is_file()

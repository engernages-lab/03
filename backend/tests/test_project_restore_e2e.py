"""End-to-end joint recovery proof (V1.1-C.2.3.3).

The whole business journey runs through the real API against a throwaway
database and storage directory:

    upload synthetic WAV → real Basic Pitch inference → music document
    → joint snapshot → delete the audio from disk → joint restore
    → reopen the project through the API and re-read the score

Nothing here can reach /data or a Railway volume: every path is created under
tmp_path and the environment is forced to ``test``.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve()


def _candidates() -> tuple[Path, ...]:
    """Fixture locations, safe for shallow paths such as /tests/x.py in the image.

    ``parents[2]`` raises IndexError when the test file lives two levels below the
    filesystem root, which is exactly the mounted layout (/tests/test_*.py), so the
    repo-checkout candidate is only added when there are enough parents.
    """
    found = [_HERE.parent / "fixtures" / "melody.wav"]
    if len(_HERE.parents) > 2:
        found.append(_HERE.parents[2] / "tests" / "fixtures" / "melody.wav")
    found.extend([Path("/tests/fixtures/melody.wav"), Path("/fixtures/melody.wav")])
    return tuple(found)


def _fixture() -> Path:
    for candidate in _candidates():
        if candidate.is_file():
            return candidate
    raise AssertionError(f"melody.wav not found; looked in {[str(c) for c in _candidates()]}")


def _reset_runtime() -> None:
    from app.core import config as config_module
    from app.core import db as db_module

    config_module.get_settings.cache_clear()
    db_module.get_engine.cache_clear() if hasattr(db_module.get_engine, "cache_clear") else None
    db_module.dispose_engine()


@pytest.fixture()
def isolated(tmp_path, monkeypatch):
    """Point the whole application at a temporary data root."""
    root = tmp_path / "e2e"
    data = root / "data"
    (data / "storage").mkdir(parents=True)
    monkeypatch.setenv("POCKETSCORE_ENVIRONMENT", "test")
    monkeypatch.setenv("POCKETSCORE_DATABASE_URL", f"sqlite:///{(data / 'pocketscore.db').as_posix()}")
    monkeypatch.setenv("POCKETSCORE_STORAGE_DIR", str(data / "storage"))
    monkeypatch.setenv("POCKETSCORE_ACCESS_GATE_MODE", "off")
    monkeypatch.setenv("POCKETSCORE_MODEL_PRELOAD", "false")
    monkeypatch.setenv("POCKETSCORE_MAX_CONCURRENT_INFERENCES", "1")
    _reset_runtime()
    yield {"root": root, "data": data, "database": data / "pocketscore.db", "storage": data / "storage"}
    _reset_runtime()


def _client():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


def _notes_of(result: dict) -> list:
    """Flatten every note event out of a MusicDocument payload."""
    document = result.get("document") or {}
    notes = list(document.get("events") or [])
    for track in document.get("tracks") or []:
        notes.extend(track.get("events") or [])
    return notes


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def test_project_survives_joint_backup_and_file_loss(isolated):
    from app.ops import project_backup as pb
    from app.ops import storage_audit as audit

    fixture = _fixture()

    # ---------------------------------------------------------------- step 1-3
    with _client() as client:
        with fixture.open("rb") as handle:
            response = client.post(
                "/api/v1/transcription/upload",
                files={"file": ("melody.wav", handle, "audio/wav")},
                params={"title": "e2e melody"},
            )
        assert response.status_code == 202, response.text
        payload = response.json()
        job_id = payload["job_id"]
        asset_id = payload["asset"]["asset_id"]

        job = client.get(f"/api/v1/transcription/jobs/{job_id}").json()
        assert job["status"] == "completed", job
        assert job["events_produced"] == 4, job
        document_id = job["document_id"]
        assert document_id

        result = client.get(f"/api/v1/transcription/jobs/{job_id}/result").json()
        notes = _notes_of(result)
        assert len(notes) == 4, result
        baseline_pitches = sorted(int(round(note["pitch"])) for note in notes)

        asset = client.get(f"/api/v1/audio/assets/{asset_id}").json()
        document = client.get(f"/api/v1/documents/{document_id}").json()

    audio_rel = asset["stored_path"] if "stored_path" in asset else asset.get("path")
    if not audio_rel:
        # the API exposes a URL; derive the stored path from the asset row
        from app.core.db import session_scope
        from app.models.audio import AudioAssetRecord

        with session_scope() as session:
            record = session.get(AudioAssetRecord, asset_id)
            audio_rel = record.stored_path
    audio_file = isolated["storage"] / audio_rel

    baseline = {
        "job_id": job_id,
        "asset_id": asset_id,
        "document_id": document_id,
        "audio_rel": audio_rel,
        "audio_size": audio_file.stat().st_size,
        "audio_sha256": _sha256(audio_file),
        "pitches": baseline_pitches,
        "events": job["events_produced"],
        "document_title": document.get("title"),
        "tracks": len(document.get("tracks") or []),
    }
    assert baseline["audio_size"] > 0

    # ------------------------------------------------------------------ step 5
    snapshot = pb.create_snapshot(
        database_path=isolated["database"],
        storage_root=isolated["storage"],
        backup_root=isolated["root"] / "backups",
    )
    assert snapshot.status == "SUCCESS", snapshot.problems
    assert snapshot.file_count == 1
    manifest = json.loads((snapshot.directory / pb.JOINT_MANIFEST).read_text(encoding="utf-8"))
    assert manifest["consistency"]["missing_files"] == 0
    assert manifest["database"]["integrity_check"] == "ok"

    # pre-loss audit: the live store is consistent
    from app.core.db import session_scope

    with session_scope() as session:
        before_audit = audit.audit_storage(isolated["storage"], session=session)
    assert before_audit.ok, before_audit.as_dict()

    # ------------------------------------------------------------------ step 6
    assert audio_file.is_file()
    audio_file.unlink()
    assert not audio_file.exists()
    # the project can no longer read its audio
    with _client() as client:
        broken = client.get(f"/api/v1/audio/assets/{asset_id}/waveform")
    assert broken.status_code >= 400, broken.status_code

    # ------------------------------------------------------------------ step 7
    target = isolated["root"] / "restored"
    preview = pb.restore_snapshot(snapshot.directory, target, dry_run=True)
    assert preview.ok and not target.exists()

    outcome = pb.restore_snapshot(snapshot.directory, target, dry_run=False)
    assert outcome.ok, outcome.steps

    restored_storage = target / "storage"
    restored_audio = restored_storage / baseline["audio_rel"]
    assert restored_audio.is_file()
    assert _sha256(restored_audio) == baseline["audio_sha256"]
    assert restored_audio.stat().st_size == baseline["audio_size"]

    # -------------------------------------------------------------- step 8-10
    # point the application at the restored tree and reopen the project
    os.environ["POCKETSCORE_DATABASE_URL"] = f"sqlite:///{(target / 'database' / 'pocketscore.db').as_posix()}"
    os.environ["POCKETSCORE_STORAGE_DIR"] = str(restored_storage)
    _reset_runtime()

    with _client() as client:
        reopened = client.get(f"/api/v1/documents/{baseline['document_id']}")
        assert reopened.status_code == 200, reopened.text
        reopened_doc = reopened.json()

        reopened_asset = client.get(f"/api/v1/audio/assets/{baseline['asset_id']}")
        assert reopened_asset.status_code == 200, reopened_asset.text

        reopened_job = client.get(f"/api/v1/transcription/jobs/{baseline['job_id']}")
        assert reopened_job.status_code == 200
        assert reopened_job.json()["status"] == "completed"
        assert reopened_job.json()["events_produced"] == baseline["events"]

        reopened_result = client.get(f"/api/v1/transcription/jobs/{baseline['job_id']}/result").json()
        restored_notes = _notes_of(reopened_result)
        restored_pitches = sorted(int(round(note["pitch"])) for note in restored_notes)

        waveform = client.get(f"/api/v1/audio/assets/{baseline['asset_id']}/waveform")
        assert waveform.status_code == 200, waveform.text

        notation = client.get(f"/api/v1/notation/{baseline['document_id']}/both")
        assert notation.status_code == 200, notation.text

    # identities are stable, nothing was duplicated
    assert reopened_doc["document_id"] == baseline["document_id"]
    assert reopened_job.json()["job_id"] == baseline["job_id"]
    assert reopened_asset.json()["asset_id"] == baseline["asset_id"]
    assert restored_pitches == baseline["pitches"] == [60, 64, 67, 72]
    assert len(restored_notes) == baseline["events"]

    # ------------------------------------------------------------- step 11-12
    with session_scope() as session:
        after_audit = audit.audit_storage(restored_storage, session=session)
    assert after_audit.ok, after_audit.as_dict()
    assert after_audit.summary()["missing_files"] == 0
    assert after_audit.summary()["hash_mismatches"] == 0

    verification = pb.verify_snapshot(snapshot.directory)
    assert verification.ok, verification.problems

    # no duplicate documents were created by the restore
    from app.core.db import session_scope as scope2
    from app.models.music import MusicDocumentRecord

    with scope2() as session:
        documents = session.query(MusicDocumentRecord).count()
    assert documents == 1

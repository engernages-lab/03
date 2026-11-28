"""Joint snapshot / restore tests (V1.1-C.2.3.3).

Every test builds a synthetic store in tmp_path; nothing here can reach /data or
a Railway volume.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from app.ops import project_backup as pb

AUDIO_PAYLOAD = b"RIFF" + b"\x00" * 4 + b"WAVEfmt " + b"\x01" * 64
ARTWORK_PAYLOAD = b"\xff\xd8\xff\xe0" + b"jpeg" * 8

DDL = """
CREATE TABLE audio_assets (
    id TEXT PRIMARY KEY,
    filename TEXT,
    stored_path TEXT,
    artwork_path TEXT,
    checksum_sha256 TEXT,
    size_bytes INTEGER
);
"""


def build_store(tmp_path: Path, *, with_artwork: bool = False) -> dict:
    """A database plus the files it references, all under tmp_path."""
    storage = tmp_path / "storage"
    audio_sha = hashlib.sha256(AUDIO_PAYLOAD).hexdigest()
    audio_rel = f"audio/{audio_sha[:2]}/{audio_sha}.wav"
    audio_path = storage / audio_rel
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    audio_path.write_bytes(AUDIO_PAYLOAD)

    artwork_rel = None
    artwork_url = None
    if with_artwork:
        artwork_sha = hashlib.sha256(ARTWORK_PAYLOAD).hexdigest()
        artwork_rel = f"artwork/{artwork_sha}.jpg"
        artwork_path = storage / artwork_rel
        artwork_path.parent.mkdir(parents=True, exist_ok=True)
        artwork_path.write_bytes(ARTWORK_PAYLOAD)
        artwork_url = f"/static/artwork/{artwork_sha}.jpg"

    db_path = tmp_path / "pocketscore.db"
    with sqlite3.connect(db_path) as connection:
        connection.executescript(DDL)
        connection.execute(
            "INSERT INTO audio_assets VALUES ('asset-1','melody.wav',?,?,?,?)",
            (audio_rel, artwork_url, audio_sha, len(AUDIO_PAYLOAD)),
        )
        connection.commit()

    return {
        "database": db_path,
        "storage": storage,
        "backups": tmp_path / "backups",
        "audio_rel": audio_rel,
        "audio_sha": audio_sha,
        "artwork_rel": artwork_rel,
    }


def test_snapshot_success_captures_database_and_files(tmp_path):
    store = build_store(tmp_path, with_artwork=True)
    result = pb.create_snapshot(
        database_path=store["database"], storage_root=store["storage"],
        backup_root=store["backups"],
    )
    assert result.status == "SUCCESS"
    assert result.file_count == 2
    manifest = json.loads((result.directory / pb.JOINT_MANIFEST).read_text(encoding="utf-8"))
    assert manifest["backup_status"] == "SUCCESS"
    assert manifest["consistency"]["missing_files"] == 0
    assert manifest["consistency"]["database_references_verified"] is True
    assert manifest["database"]["integrity_check"] == "ok"
    assert (result.directory / pb.SNAPSHOT_HASH).is_file()
    assert (result.directory / pb.STORAGE_DIR / store["audio_rel"]).is_file()
    assert (result.directory / pb.STORAGE_DIR / store["artwork_rel"]).is_file()


def test_snapshot_is_verified_by_verify_snapshot(tmp_path):
    store = build_store(tmp_path)
    result = pb.create_snapshot(database_path=store["database"], storage_root=store["storage"],
                                backup_root=store["backups"])
    verification = pb.verify_snapshot(result.directory)
    assert verification.ok, verification.problems
    assert verification.file_count == 1


def test_snapshot_fails_when_referenced_file_is_missing(tmp_path):
    store = build_store(tmp_path)
    (store["storage"] / store["audio_rel"]).unlink()
    with pytest.raises(pb.SnapshotError) as error:
        pb.create_snapshot(database_path=store["database"], storage_root=store["storage"],
                           backup_root=store["backups"])
    assert "missing" in str(error.value)
    # no published snapshot, and the staging directory was cleaned up
    assert [p for p in store["backups"].iterdir() if p.is_dir() and not p.name.startswith(".")] == []
    assert [p for p in store["backups"].iterdir() if p.name.startswith(".inprogress")] == []


def test_snapshot_fails_when_content_does_not_match_its_name(tmp_path):
    store = build_store(tmp_path)
    (store["storage"] / store["audio_rel"]).write_bytes(b"tampered payload")
    with pytest.raises(pb.SnapshotError) as error:
        pb.create_snapshot(database_path=store["database"], storage_root=store["storage"],
                           backup_root=store["backups"])
    assert "content-addressed" in str(error.value) or "hash" in str(error.value)


def test_snapshot_with_no_assets_still_works(tmp_path):
    storage = tmp_path / "storage"
    storage.mkdir()
    db_path = tmp_path / "empty.db"
    with sqlite3.connect(db_path) as connection:
        connection.executescript(DDL)
        connection.commit()
    result = pb.create_snapshot(database_path=db_path, storage_root=storage, backup_root=tmp_path / "backups")
    assert result.status == "SUCCESS"
    assert result.file_count == 0


def test_concurrent_snapshot_is_blocked_by_the_lock(tmp_path):
    store = build_store(tmp_path)
    store["backups"].mkdir(parents=True, exist_ok=True)
    with pb.snapshot_lock(store["backups"], timeout=0.1), pytest.raises(pb.LockBusyError):
        pb.create_snapshot(database_path=store["database"], storage_root=store["storage"],
                           backup_root=store["backups"])
    # after the lock is released another snapshot succeeds
    result = pb.create_snapshot(database_path=store["database"], storage_root=store["storage"],
                                backup_root=store["backups"])
    assert result.status == "SUCCESS"


def test_stale_lock_is_taken_over(tmp_path):
    root = tmp_path / "backups"
    root.mkdir()
    lock = root / pb.LOCK_NAME
    lock.write_text("{}", encoding="utf-8")
    import os
    import time

    old = time.time() - (pb.LOCK_TIMEOUT_SECONDS + 60)
    os.utime(lock, (old, old))
    with pb.snapshot_lock(root, timeout=1.0):
        assert lock.exists()
    assert not lock.exists()


def test_verify_detects_tampered_file(tmp_path):
    store = build_store(tmp_path)
    result = pb.create_snapshot(database_path=store["database"], storage_root=store["storage"],
                                backup_root=store["backups"])
    target = result.directory / pb.STORAGE_DIR / store["audio_rel"]
    target.write_bytes(b"changed")
    verification = pb.verify_snapshot(result.directory)
    assert not verification.ok
    assert any("sha256" in problem or "size" in problem for problem in verification.problems)


def test_verify_detects_tampered_manifest(tmp_path):
    store = build_store(tmp_path)
    result = pb.create_snapshot(database_path=store["database"], storage_root=store["storage"],
                                backup_root=store["backups"])
    manifest_path = result.directory / pb.JOINT_MANIFEST
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["database"]["sha256"] = "0" * 64          # pretend a different database
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    verification = pb.verify_snapshot(result.directory)
    assert not verification.ok
    assert any("manifest hash" in problem for problem in verification.problems)


def test_verify_detects_missing_file(tmp_path):
    store = build_store(tmp_path)
    result = pb.create_snapshot(database_path=store["database"], storage_root=store["storage"],
                                backup_root=store["backups"])
    (result.directory / pb.STORAGE_DIR / store["audio_rel"]).unlink()
    verification = pb.verify_snapshot(result.directory)
    assert not verification.ok
    assert any("missing" in problem for problem in verification.problems)


def test_restore_dry_run_creates_nothing(tmp_path):
    store = build_store(tmp_path)
    result = pb.create_snapshot(database_path=store["database"], storage_root=store["storage"],
                                backup_root=store["backups"])
    target = tmp_path / "restored"
    outcome = pb.restore_snapshot(result.directory, target, dry_run=True)
    assert outcome.ok and outcome.dry_run
    assert not target.exists()


def test_restore_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("POCKETSCORE_ENVIRONMENT", "test")
    store = build_store(tmp_path, with_artwork=True)
    result = pb.create_snapshot(database_path=store["database"], storage_root=store["storage"],
                                backup_root=store["backups"])
    target = tmp_path / "restored"
    outcome = pb.restore_snapshot(result.directory, target, dry_run=False)
    assert outcome.ok, outcome.steps

    restored_db = target / "database" / "pocketscore.db"
    restored_storage = target / "storage"
    assert restored_db.is_file()
    assert (restored_storage / store["audio_rel"]).read_bytes() == AUDIO_PAYLOAD
    assert (restored_storage / store["artwork_rel"]).read_bytes() == ARTWORK_PAYLOAD

    with sqlite3.connect(restored_db) as connection:
        row = connection.execute("SELECT id, stored_path, artwork_path FROM audio_assets").fetchone()
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    assert row == ("asset-1", store["audio_rel"], f"/static/artwork/{Path(store['artwork_rel']).name}")
    assert integrity == "ok"
    # the database still resolves its files inside the restored tree
    assert (restored_storage / row[1]).is_file()


def test_restore_refuses_non_empty_target_without_force(tmp_path, monkeypatch):
    monkeypatch.setenv("POCKETSCORE_ENVIRONMENT", "test")
    store = build_store(tmp_path)
    result = pb.create_snapshot(database_path=store["database"], storage_root=store["storage"],
                                backup_root=store["backups"])
    target = tmp_path / "restored"
    target.mkdir()
    (target / "keep-me.txt").write_text("do not delete", encoding="utf-8")
    outcome = pb.restore_snapshot(result.directory, target, dry_run=False)
    assert outcome.ok is False
    assert (target / "keep-me.txt").exists()


def test_restore_force_keeps_a_safety_copy(tmp_path, monkeypatch):
    monkeypatch.setenv("POCKETSCORE_ENVIRONMENT", "test")
    store = build_store(tmp_path)
    result = pb.create_snapshot(database_path=store["database"], storage_root=store["storage"],
                                backup_root=store["backups"])
    target = tmp_path / "restored"
    target.mkdir()
    (target / "old.txt").write_text("old", encoding="utf-8")
    outcome = pb.restore_snapshot(result.directory, target, dry_run=False, force=True)
    assert outcome.ok, outcome.steps
    assert outcome.safety_copy is not None and outcome.safety_copy.is_dir()
    assert (outcome.safety_copy / "old.txt").exists()


def test_restore_refuses_data_volume(tmp_path, monkeypatch):
    monkeypatch.setenv("POCKETSCORE_ENVIRONMENT", "test")
    store = build_store(tmp_path)
    result = pb.create_snapshot(database_path=store["database"], storage_root=store["storage"],
                                backup_root=store["backups"])
    with pytest.raises(pb.dbb.UnsafeTargetError):
        pb.restore_snapshot(result.directory, Path("/data/restore-test"), dry_run=True)


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_restore_refuses_live_environments(tmp_path, monkeypatch, environment):
    store = build_store(tmp_path)
    result = pb.create_snapshot(database_path=store["database"], storage_root=store["storage"],
                                backup_root=store["backups"])
    monkeypatch.setenv("POCKETSCORE_ENVIRONMENT", environment)
    with pytest.raises(pb.dbb.UnsafeTargetError):
        pb.restore_snapshot(result.directory, tmp_path / "restored", dry_run=False, force=True)


def test_restore_rejects_corrupt_snapshot(tmp_path, monkeypatch):
    monkeypatch.setenv("POCKETSCORE_ENVIRONMENT", "test")
    store = build_store(tmp_path)
    result = pb.create_snapshot(database_path=store["database"], storage_root=store["storage"],
                                backup_root=store["backups"])
    (result.directory / pb.DATABASE_DIR / "pocketscore.db").write_bytes(b"garbage")
    # find the actual database file name
    db_files = list((result.directory / pb.DATABASE_DIR).glob("*.sqlite3"))
    if db_files:
        db_files[0].write_bytes(b"garbage")
    outcome = pb.restore_snapshot(result.directory, tmp_path / "restored", dry_run=False)
    assert outcome.ok is False


def test_list_and_prune_keep_database_with_files(tmp_path, monkeypatch):
    monkeypatch.setenv("POCKETSCORE_ENVIRONMENT", "test")
    store = build_store(tmp_path)
    snapshots = []
    from datetime import datetime, timedelta, timezone

    base = datetime(2026, 11, 28, 12, 0, tzinfo=timezone.utc)
    for offset in range(6):
        result = pb.create_snapshot(database_path=store["database"], storage_root=store["storage"],
                                    backup_root=store["backups"], moment=base - timedelta(days=offset))
        snapshots.append(result)

    rows = pb.list_snapshots(store["backups"], verify=True)
    assert len(rows) == 6
    assert all(status == "SUCCESS" for _n, _p, status in rows)

    plan = pb.plan_prune(rows, daily=2, weekly=2, monthly=1)
    assert plan["remove"]
    removed = pb.apply_prune(store["backups"], plan, allow_delete=False)
    assert removed == []

    removed = pb.apply_prune(store["backups"], plan, allow_delete=True)
    assert removed
    for name in plan["keep"]:
        directory = store["backups"] / name
        assert (directory / pb.JOINT_MANIFEST).is_file()
        assert (directory / pb.STORAGE_DIR / store["audio_rel"]).is_file()


def test_prune_never_removes_the_newest(tmp_path):

    root = tmp_path / "backups"
    root.mkdir()
    names = []
    for day in range(3):
        name = f"pocketscore-snapshot-2026112{day}-120000Z-abcdef"
        directory = root / name
        directory.mkdir()
        (directory / pb.JOINT_MANIFEST).write_text("{}", encoding="utf-8")
        names.append((name, directory, "SUCCESS"))
    plan = pb.plan_prune(names, daily=1, weekly=1, monthly=1)
    assert names[-1][0] in plan["keep"]

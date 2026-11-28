"""Tests for the SQLite backup/restore tooling (V1.1-C.2.3.2).

Every test runs against a synthetic database in ``tmp_path``. No test touches
``/data``, a Railway volume or any real user data.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.ops import database_backup as db_backup

CORE_DDL = """
CREATE TABLE audio_assets (
    id TEXT PRIMARY KEY,
    filename TEXT,
    stored_path TEXT,
    checksum_sha256 TEXT,
    size_bytes INTEGER
);
CREATE TABLE music_documents (
    id TEXT PRIMARY KEY,
    schema_version INTEGER,
    title TEXT
);
CREATE TABLE music_events (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES music_documents(id) ON DELETE CASCADE,
    pitch INTEGER,
    start_time REAL,
    duration REAL
);
CREATE TABLE music_tracks (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES music_documents(id) ON DELETE CASCADE,
    name TEXT
);
CREATE TABLE transcription_jobs (
    id TEXT PRIMARY KEY,
    document_id TEXT,
    asset_id TEXT REFERENCES audio_assets(id) ON DELETE SET NULL,
    status TEXT
);
CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY);
"""


def make_db(path: Path, *, rows: bool = True, user_version: int = 0) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.executescript(CORE_DDL)
        connection.execute("PRAGMA user_version=%d" % user_version)
        connection.execute("INSERT INTO alembic_version VALUES ('0002_event_confidence')")
        if rows:
            connection.execute(
                "INSERT INTO audio_assets VALUES ('a1','melody.wav','storage/audio/f4/aa.wav','aa',79424)"
            )
            connection.execute("INSERT INTO music_documents VALUES ('d1',1,'melody')")
            connection.execute("INSERT INTO music_events VALUES ('e1','d1',60,0.0,0.75)")
            connection.execute("INSERT INTO music_events VALUES ('e2','d1',64,0.75,0.75)")
            connection.execute("INSERT INTO music_tracks VALUES ('t1','d1','piano')")
            connection.execute("INSERT INTO transcription_jobs VALUES ('j1','d1','a1','completed')")
        connection.commit()
    return path


def counts(path: Path) -> dict:
    with sqlite3.connect(path) as connection:
        return {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("audio_assets", "music_documents", "music_events", "music_tracks", "transcription_jobs")
        }


# --------------------------------------------------------------------------- #
# backup
# --------------------------------------------------------------------------- #


def test_backup_empty_database(tmp_path):
    db = make_db(tmp_path / "empty.db", rows=False)
    result = db_backup.create_backup(db, tmp_path / "backups")
    assert result.status == "SUCCESS"
    assert result.backup_file.is_file() and result.size_bytes > 0
    assert db_backup.verify_backup(result.backup_file).ok


def test_backup_with_rows_and_manifest(tmp_path):
    db = make_db(tmp_path / "data.db")
    before = counts(db)
    result = db_backup.create_backup(db, tmp_path / "backups", moment=datetime(2026, 11, 28, 9, 30, tzinfo=timezone.utc))
    manifest = json.loads(result.manifest_file.read_text(encoding="utf-8"))

    assert result.backup_file.name == "pocketscore-20261128-093000Z.sqlite3"
    assert manifest["backup_method"] == db_backup.BACKUP_METHOD
    assert manifest["integrity_check"] == "ok"
    assert manifest["foreign_key_check"] == "ok"
    assert manifest["sha256"] == result.sha256
    assert manifest["backup_status"] == "SUCCESS"
    assert manifest["database_engine"] == "sqlite"
    assert manifest["core_tables_present"] is True
    assert manifest["backup_size_bytes"] == result.backup_file.stat().st_size
    assert counts(result.backup_file) == before
    assert (result.manifest_file.parent / (result.backup_id + ".sha256")).is_file()


def test_manifest_contains_no_row_data(tmp_path):
    db = make_db(tmp_path / "data.db")
    result = db_backup.create_backup(db, tmp_path / "backups")
    manifest_text = result.manifest_file.read_text(encoding="utf-8")
    for leak in ("melody.wav", "storage/audio", "pitch", "INSERT"):
        assert leak not in manifest_text


def test_wal_backup_includes_committed_pages(tmp_path):
    db = make_db(tmp_path / "wal.db")
    reader = sqlite3.connect(db)
    reader.execute("PRAGMA journal_mode=WAL")
    reader.execute("INSERT INTO music_documents VALUES ('d2',1,'from-wal')")
    reader.commit()  # committed but possibly still only in -wal
    try:
        result = db_backup.create_backup(db, tmp_path / "backups")
    finally:
        reader.close()
    with sqlite3.connect(result.backup_file) as connection:
        titles = {row[0] for row in connection.execute("SELECT title FROM music_documents")}
    assert "from-wal" in titles


def test_backup_excludes_uncommitted_transaction(tmp_path):
    db = make_db(tmp_path / "open-tx.db")
    writer = sqlite3.connect(db)
    writer.execute("BEGIN")
    writer.execute("INSERT INTO music_documents VALUES ('d3',1,'uncommitted')")
    try:
        result = db_backup.create_backup(db, tmp_path / "backups")
    finally:
        writer.rollback()
        writer.close()
    with sqlite3.connect(result.backup_file) as connection:
        titles = {row[0] for row in connection.execute("SELECT title FROM music_documents")}
    assert "uncommitted" not in titles


def test_backup_while_connection_is_open(tmp_path):
    db = make_db(tmp_path / "busy.db")
    holder = sqlite3.connect(db)
    holder.execute("SELECT COUNT(*) FROM music_documents").fetchone()
    try:
        result = db_backup.create_backup(db, tmp_path / "backups")
    finally:
        holder.close()
    assert db_backup.verify_backup(result.backup_file).ok


def test_backup_creates_missing_directory(tmp_path):
    db = make_db(tmp_path / "data.db")
    target = tmp_path / "nested" / "backups"
    result = db_backup.create_backup(db, target)
    assert target.is_dir() and result.backup_file.is_file()


def test_backup_rejects_unwritable_directory(tmp_path):
    db = make_db(tmp_path / "data.db")
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x", encoding="utf-8")
    with pytest.raises(OSError):
        db_backup.create_backup(db, blocker)


def test_backup_missing_database_raises(tmp_path):
    with pytest.raises(db_backup.BackupError):
        db_backup.create_backup(tmp_path / "missing.db", tmp_path / "backups")


def test_backup_refuses_to_overwrite_same_timestamp(tmp_path):
    db = make_db(tmp_path / "data.db")
    moment = datetime(2026, 11, 28, 10, 0, tzinfo=timezone.utc)
    db_backup.create_backup(db, tmp_path / "backups", moment=moment)
    with pytest.raises(db_backup.BackupError):
        db_backup.create_backup(db, tmp_path / "backups", moment=moment)


def test_backup_cleans_partial_file_when_api_fails(tmp_path, monkeypatch):
    db = make_db(tmp_path / "data.db")
    target = tmp_path / "backups"

    def boom(_source, destination):
        Path(destination).write_bytes(b"half-written")
        raise sqlite3.OperationalError("database or disk is full")

    monkeypatch.setattr(db_backup, "_copy_via_backup_api", boom, raising=True)
    with pytest.raises(db_backup.BackupError):
        db_backup.create_backup(db, target)
    leftovers = [p.name for p in target.iterdir() if p.name.endswith(".partial")]
    assert leftovers == []


def test_backup_reports_manifest_write_failure(tmp_path, monkeypatch):
    db = make_db(tmp_path / "data.db")
    original = Path.write_text

    def fail(self, *args, **kwargs):
        if self.name.endswith(".manifest.json"):
            raise OSError("disk full")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fail, raising=True)
    with pytest.raises(db_backup.BackupError):
        db_backup.create_backup(db, tmp_path / "backups")


def test_corrupt_database_is_not_marked_success(tmp_path):
    broken = tmp_path / "broken.db"
    broken.write_bytes(b"this is definitely not a sqlite database" * 50)
    with pytest.raises(db_backup.BackupError):
        db_backup.create_backup(broken, tmp_path / "backups")


# --------------------------------------------------------------------------- #
# verify
# --------------------------------------------------------------------------- #


def test_verify_detects_hash_mismatch(tmp_path):
    db = make_db(tmp_path / "data.db")
    result = db_backup.create_backup(db, tmp_path / "backups")
    with result.backup_file.open("ab") as handle:
        handle.write(b"\x00")
    verification = db_backup.verify_backup(result.backup_file)
    assert verification.ok is False
    assert any("sha256" in problem for problem in verification.problems)


def test_verify_detects_missing_manifest(tmp_path):
    db = make_db(tmp_path / "data.db")
    result = db_backup.create_backup(db, tmp_path / "backups")
    result.manifest_file.unlink()
    verification = db_backup.verify_backup(result.backup_file)
    assert verification.ok is False
    assert any("manifest missing" in problem for problem in verification.problems)
    assert db_backup.verify_backup(result.backup_file, require_manifest=False).ok is True


def test_verify_detects_schema_version_mismatch(tmp_path):
    db = make_db(tmp_path / "data.db")
    result = db_backup.create_backup(db, tmp_path / "backups")
    manifest = json.loads(result.manifest_file.read_text(encoding="utf-8"))
    manifest["database_schema_version"] = 99
    result.manifest_file.write_text(json.dumps(manifest), encoding="utf-8")
    verification = db_backup.verify_backup(result.backup_file)
    assert verification.ok is False
    assert any("schema version mismatch" in problem for problem in verification.problems)


def test_verify_detects_foreign_key_violation(tmp_path):
    db = make_db(tmp_path / "fk.db")
    with sqlite3.connect(db) as connection:
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute("INSERT INTO music_events VALUES ('bad','missing-doc',60,0,1)")
        connection.commit()
    result = db_backup.create_backup(db, tmp_path / "backups") if False else None
    # create_backup refuses a source with violations, so build the file by hand
    manual = tmp_path / "backups" / "manual-20261128-120000Z.sqlite3"
    manual.parent.mkdir(parents=True, exist_ok=True)
    manual.write_bytes(db.read_bytes())
    verification = db_backup.verify_backup(manual, require_manifest=False)
    assert verification.ok is False
    assert any("foreign_key_check" in problem for problem in verification.problems)
    assert result is None


def test_backup_refuses_source_with_fk_violation(tmp_path):
    db = make_db(tmp_path / "fk2.db")
    with sqlite3.connect(db) as connection:
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute("INSERT INTO music_events VALUES ('bad','missing-doc',60,0,1)")
        connection.commit()
    with pytest.raises(db_backup.BackupError):
        db_backup.create_backup(db, tmp_path / "backups")


def test_verify_detects_core_table_missing(tmp_path):
    db = make_db(tmp_path / "partial.db")
    with sqlite3.connect(db) as connection:
        connection.execute("DROP TABLE transcription_jobs")
        connection.commit()
    manual = tmp_path / "backups" / "partial-20261128-130000Z.sqlite3"
    manual.parent.mkdir(parents=True, exist_ok=True)
    manual.write_bytes(db.read_bytes())
    verification = db_backup.verify_backup(manual, require_manifest=False)
    assert verification.ok is False
    assert any("core tables missing" in problem for problem in verification.problems)


# --------------------------------------------------------------------------- #
# restore
# --------------------------------------------------------------------------- #


def test_restore_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("POCKETSCORE_ENVIRONMENT", "test")
    db = make_db(tmp_path / "data.db")
    before = counts(db)
    result = db_backup.create_backup(db, tmp_path / "backups")

    target = tmp_path / "restore" / "restored.db"
    outcome = db_backup.restore_backup(result.backup_file, target, dry_run=False)
    assert outcome.ok is True, outcome.steps
    assert counts(target) == before
    assert db_backup.verify_backup(target, require_manifest=False).ok


def test_restore_empty_database(tmp_path, monkeypatch):
    monkeypatch.setenv("POCKETSCORE_ENVIRONMENT", "test")
    db = make_db(tmp_path / "empty.db", rows=False)
    result = db_backup.create_backup(db, tmp_path / "backups")
    target = tmp_path / "restore" / "empty.db"
    outcome = db_backup.restore_backup(result.backup_file, target, dry_run=False)
    assert outcome.ok and counts(target)["music_documents"] == 0


def test_restore_dry_run_does_not_touch_target(tmp_path, monkeypatch):
    monkeypatch.setenv("POCKETSCORE_ENVIRONMENT", "test")
    db = make_db(tmp_path / "data.db")
    result = db_backup.create_backup(db, tmp_path / "backups")
    target = tmp_path / "restore" / "restored.db"
    outcome = db_backup.restore_backup(result.backup_file, target, dry_run=True)
    assert outcome.ok and outcome.dry_run
    assert not target.exists()


def test_restore_refuses_existing_target_without_force(tmp_path, monkeypatch):
    monkeypatch.setenv("POCKETSCORE_ENVIRONMENT", "test")
    db = make_db(tmp_path / "data.db")
    result = db_backup.create_backup(db, tmp_path / "backups")
    target = tmp_path / "restore" / "restored.db"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"existing")
    outcome = db_backup.restore_backup(result.backup_file, target, dry_run=False)
    assert outcome.ok is False
    assert any("--force" in step for step in outcome.steps)
    assert target.read_bytes() == b"existing"


def test_restore_force_makes_safety_copy(tmp_path, monkeypatch):
    monkeypatch.setenv("POCKETSCORE_ENVIRONMENT", "test")
    db = make_db(tmp_path / "data.db")
    result = db_backup.create_backup(db, tmp_path / "backups")
    target = tmp_path / "restore" / "restored.db"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"old-content")
    outcome = db_backup.restore_backup(result.backup_file, target, dry_run=False, force=True)
    assert outcome.ok
    assert outcome.pre_existing_safety_copy is not None
    assert outcome.pre_existing_safety_copy.read_bytes() == b"old-content"


def test_restore_missing_backup_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("POCKETSCORE_ENVIRONMENT", "test")
    outcome = db_backup.restore_backup(tmp_path / "nope.sqlite3", tmp_path / "t.db", dry_run=True)
    assert outcome.ok is False


def test_restore_rejects_corrupt_backup(tmp_path, monkeypatch):
    monkeypatch.setenv("POCKETSCORE_ENVIRONMENT", "test")
    broken = tmp_path / "broken.sqlite3"
    broken.write_bytes(b"garbage" * 200)
    outcome = db_backup.restore_backup(broken, tmp_path / "t.db", dry_run=True, allow_manifest_missing=True)
    assert outcome.ok is False


def test_restore_refuses_production_environment(tmp_path, monkeypatch):
    db = make_db(tmp_path / "data.db")
    result = db_backup.create_backup(db, tmp_path / "backups")
    monkeypatch.setenv("POCKETSCORE_ENVIRONMENT", "production")
    with pytest.raises(db_backup.UnsafeTargetError):
        db_backup.restore_backup(result.backup_file, tmp_path / "t.db", dry_run=False)


def test_restore_refuses_staging_environment(tmp_path, monkeypatch):
    db = make_db(tmp_path / "data.db")
    result = db_backup.create_backup(db, tmp_path / "backups")
    monkeypatch.setenv("POCKETSCORE_ENVIRONMENT", "staging")
    with pytest.raises(db_backup.UnsafeTargetError):
        db_backup.restore_backup(result.backup_file, tmp_path / "t.db", dry_run=False, force=True)


def test_restore_refuses_data_volume_target(tmp_path, monkeypatch):
    monkeypatch.setenv("POCKETSCORE_ENVIRONMENT", "test")
    db = make_db(tmp_path / "data.db")
    result = db_backup.create_backup(db, tmp_path / "backups")
    with pytest.raises(db_backup.UnsafeTargetError):
        db_backup.restore_backup(result.backup_file, Path("/data/pocketscore.db"), dry_run=True)


# --------------------------------------------------------------------------- #
# listing and retention
# --------------------------------------------------------------------------- #


def _seed_backups(tmp_path, monkeypatch, days: list[int]) -> Path:
    monkeypatch.setenv("POCKETSCORE_ENVIRONMENT", "test")
    db = make_db(tmp_path / "data.db")
    backup_dir = tmp_path / "backups"
    base = datetime(2026, 11, 28, 12, 0, tzinfo=timezone.utc)
    for offset in days:
        db_backup.create_backup(db, backup_dir, moment=base - timedelta(days=offset))
    return backup_dir


def test_list_only_returns_managed_backups(tmp_path, monkeypatch):
    backup_dir = _seed_backups(tmp_path, monkeypatch, [0, 1])
    (backup_dir / "unrelated.sqlite3").write_bytes(b"not ours")
    (backup_dir / "notes.txt").write_text("hello", encoding="utf-8")
    entries = db_backup.list_backups(backup_dir)
    assert len(entries) == 2
    assert all(e.file.name.startswith("pocketscore-") for e in entries)


def test_prune_dry_run_deletes_nothing(tmp_path, monkeypatch):
    backup_dir = _seed_backups(tmp_path, monkeypatch, list(range(12)))
    entries = db_backup.list_backups(backup_dir, verify=True)
    plan = db_backup.plan_prune(entries, daily=7, weekly=4, monthly=3)
    assert plan.remove, "expected some candidates over the retention window"
    removed = db_backup.apply_prune(plan, allow_delete=False)
    assert removed == []
    assert len(list(backup_dir.glob("*.sqlite3"))) == 12


def test_prune_keeps_newest_and_never_deletes_everything(tmp_path, monkeypatch):
    backup_dir = _seed_backups(tmp_path, monkeypatch, list(range(5)))
    entries = db_backup.list_backups(backup_dir, verify=True)
    plan = db_backup.plan_prune(entries, daily=1, weekly=1, monthly=1)
    newest = max(entries, key=lambda e: e.key)
    assert any(e.file == newest.file for e in plan.keep)


def test_prune_apply_removes_only_planned_files(tmp_path, monkeypatch):
    backup_dir = _seed_backups(tmp_path, monkeypatch, list(range(10)))
    stray = backup_dir / "someone-elses.sqlite3"
    stray.write_bytes(b"x")
    entries = db_backup.list_backups(backup_dir, verify=True)
    plan = db_backup.plan_prune(entries, daily=3, weekly=2, monthly=1)
    removed = db_backup.apply_prune(plan, allow_delete=True)
    assert removed
    assert stray.exists(), "a non-managed file must never be removed"
    for backup_id in removed:
        assert not (backup_dir / f"{backup_id}.sqlite3").exists()
        assert not (backup_dir / f"{backup_id}.manifest.json").exists()


def test_prune_skips_failed_backups(tmp_path, monkeypatch):
    backup_dir = _seed_backups(tmp_path, monkeypatch, [0])
    entries = db_backup.list_backups(backup_dir, verify=True)
    entries[0].verified = False
    plan = db_backup.plan_prune(entries, daily=0, weekly=0, monthly=0)
    assert plan.remove == []
    assert plan.skipped


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def test_cli_backup_and_verify(tmp_path, capsys):
    db = make_db(tmp_path / "data.db")
    code = db_backup.main(["backup", "--database", str(db), "--backup-dir", str(tmp_path / "backups")])
    assert code == db_backup.EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    backup_path = payload["backup_file"]

    assert db_backup.main(["verify", "--backup", backup_path]) == db_backup.EXIT_OK


def test_cli_verify_missing_file_returns_failure(tmp_path):
    assert db_backup.main(["verify", "--backup", str(tmp_path / "nope.sqlite3")]) == db_backup.EXIT_FAILED


def test_cli_restore_refusal_exit_code(tmp_path, monkeypatch):
    monkeypatch.setenv("POCKETSCORE_ENVIRONMENT", "production")
    db = make_db(tmp_path / "data.db")
    result = db_backup.create_backup(db, tmp_path / "backups")
    code = db_backup.main([
        "restore", "--backup", str(result.backup_file), "--target", str(tmp_path / "t.db"), "--force",
    ])
    assert code == db_backup.EXIT_REFUSED


def test_cli_prune_defaults_to_dry_run(tmp_path, monkeypatch):
    backup_dir = _seed_backups(tmp_path, monkeypatch, list(range(8)))
    before = len(list(backup_dir.glob("*.sqlite3")))
    code = db_backup.main(["prune", "--backup-dir", str(backup_dir), "--daily", "2", "--weekly", "1", "--monthly", "1"])
    assert code == db_backup.EXIT_OK
    assert len(list(backup_dir.glob("*.sqlite3"))) == before


# --------------------------------------------------------------------------- #
# end-to-end
# --------------------------------------------------------------------------- #


def test_end_to_end_backup_modify_restore(tmp_path, monkeypatch):
    monkeypatch.setenv("POCKETSCORE_ENVIRONMENT", "test")
    live = make_db(tmp_path / "live.db")
    before = counts(live)
    before_rows = None
    with sqlite3.connect(live) as connection:
        before_rows = connection.execute(
            "SELECT id, pitch, start_time, duration FROM music_events ORDER BY id"
        ).fetchall()

    result = db_backup.create_backup(live, tmp_path / "backups")
    backup_sha = db_backup.sha256_file(result.backup_file)

    # damage the live database after the backup
    with sqlite3.connect(live) as connection:
        connection.execute("DELETE FROM music_events")
        connection.execute("DELETE FROM music_documents")
        connection.commit()
    assert counts(live)["music_events"] == 0

    target = tmp_path / "restored" / "restored.db"
    outcome = db_backup.restore_backup(result.backup_file, target, dry_run=False)
    assert outcome.ok is True

    assert counts(target) == before
    with sqlite3.connect(target) as connection:
        restored_rows = connection.execute(
            "SELECT id, pitch, start_time, duration FROM music_events ORDER BY id"
        ).fetchall()
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        violations = connection.execute("PRAGMA foreign_key_check").fetchall()
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]

    assert restored_rows == before_rows
    assert integrity == "ok"
    assert violations == []
    assert version == 0
    assert revision == "0002_event_confidence"
    # the restored file keeps the backup's bytes
    assert db_backup.sha256_file(target) == backup_sha

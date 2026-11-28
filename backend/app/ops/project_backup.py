"""Joint database + file snapshots and restores (V1.1-C.2.3.3).

A snapshot is one directory holding a consistent SQLite backup **and** every file
that backup references. The two halves are published together or not at all:

    <root>/<snapshot_id>/
        joint-manifest.json        # the authority: status, hashes, counts
        snapshot.sha256            # sha256 of joint-manifest.json
        database/<id>.sqlite3      # sqlite3 backup API output (+ manifest, .sha256)
        storage/manifest.json      # per-file inventory
        storage/audio/<xx>/<sha>.wav
        storage/artwork/<sha>.jpg

Consistency rule: the file list is derived from **the snapshot database**, never
from the live store. A file that appears after the database snapshot is therefore
irrelevant, and a file the snapshot references must be copied or the snapshot
fails. That closes the "database says it exists but we copied a later state" gap
without needing a filesystem-wide freeze.

CLI (run from ``backend/``):

    python -m app.ops.project_backup snapshot
    python -m app.ops.project_backup list
    python -m app.ops.project_backup verify --snapshot <dir>
    python -m app.ops.project_backup restore --snapshot <dir> --target <dir> [--dry-run]
    python -m app.ops.project_backup prune [--apply]
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import shutil
import sqlite3
import sys
import time
import uuid
from contextlib import closing, contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple

from app.ops import database_backup as dbb
from app.ops.storage_audit import (
    CATEGORY_ARTWORK,
    artwork_relative_path,
    expected_hash_for,
    is_within,
    sha256_file,
)

SNAPSHOT_PREFIX = "pocketscore-snapshot-"
JOINT_MANIFEST = "joint-manifest.json"
SNAPSHOT_HASH = "snapshot.sha256"
STORAGE_MANIFEST = "storage/manifest.json"
DATABASE_DIR = "database"
STORAGE_DIR = "storage"
LOCK_NAME = ".snapshot.lock"
LOCK_TIMEOUT_SECONDS = 900
MANIFEST_VERSION = 1

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2
EXIT_REFUSED = 3


class SnapshotError(RuntimeError):
    """A snapshot could not be produced or is not usable."""


class LockBusyError(SnapshotError):
    """Another snapshot/restore/prune holds the lock."""


# --------------------------------------------------------------------------- #
# locking
# --------------------------------------------------------------------------- #


@contextmanager
def snapshot_lock(root: Path, *, timeout: float = 30.0, stale_after: float = LOCK_TIMEOUT_SECONDS) -> Iterator[Path]:
    """Cross-platform exclusive lock with staleness takeover.

    ``O_CREAT | O_EXCL`` is atomic on both POSIX and Windows, so two processes
    cannot both create the lock file. A crashed process leaves the file behind;
    a lock older than ``stale_after`` is taken over after recording it.
    """
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    lock_path = root / LOCK_NAME
    deadline = time.monotonic() + timeout
    while True:
        try:
            handle = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(handle, json.dumps({"pid": os.getpid(), "at": datetime.now(timezone.utc).isoformat()}).encode())
            os.close(handle)
            break
        except FileExistsError:
            try:
                age = time.time() - lock_path.stat().st_mtime
            except OSError:
                age = 0.0
            if age > stale_after:
                with contextlib.suppress(OSError):
                    lock_path.unlink()
                continue
            if time.monotonic() >= deadline:
                raise LockBusyError(
                    f"another snapshot operation holds {lock_path} (age {age:.0f}s); "
                    "wait for it to finish or remove the lock if the process is gone"
                ) from None
            time.sleep(0.2)
    try:
        yield lock_path
    finally:
        with contextlib.suppress(OSError):
            lock_path.unlink()


# --------------------------------------------------------------------------- #
# reference extraction from a snapshot database
# --------------------------------------------------------------------------- #


def references_from_database(database: Path, storage_root: Path) -> List[Dict[str, Any]]:
    """Every file the *snapshot* database points at, as storage-relative paths."""
    with closing(sqlite3.connect(f"file:{Path(database).as_posix()}?mode=ro", uri=True)) as connection:
        rows = connection.execute(
            "SELECT id, stored_path, artwork_path FROM audio_assets"
        ).fetchall()

    refs: List[Dict[str, Any]] = []
    for record_id, stored_path, artwork_path in rows:
        if stored_path:
            relative = str(stored_path).replace("\\", "/").lstrip("/")
            refs.append({
                "record_id": record_id,
                "column": "stored_path",
                "category": "audio",
                "relative_path": relative,
                "expected_sha256": expected_hash_for(relative),
            })
        if artwork_path:
            relative = artwork_relative_path(str(artwork_path))
            if relative:
                refs.append({
                    "record_id": record_id,
                    "column": "artwork_path",
                    "category": CATEGORY_ARTWORK,
                    "relative_path": relative,
                    "expected_sha256": expected_hash_for(relative),
                })
    return refs


# --------------------------------------------------------------------------- #
# snapshot creation
# --------------------------------------------------------------------------- #


@dataclass
class SnapshotResult:
    snapshot_id: str
    directory: Path
    status: str
    database_sha256: str = ""
    database_size_bytes: int = 0
    file_count: int = 0
    total_size_bytes: int = 0
    missing_files: List[str] = field(default_factory=list)
    problems: List[str] = field(default_factory=list)
    manifest: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "directory": str(self.directory),
            "status": self.status,
            "database_sha256": self.database_sha256,
            "database_size_bytes": self.database_size_bytes,
            "file_count": self.file_count,
            "total_size_bytes": self.total_size_bytes,
            "missing_files": self.missing_files,
            "problems": self.problems,
        }


def _resolve_storage_root(storage_root: Optional[Path]) -> Path:
    if storage_root is not None:
        return Path(storage_root).resolve()
    from app.core.config import get_settings

    return get_settings().storage_path.resolve()


def _copy_streaming(source: Path, destination: Path) -> str:
    """Copy while hashing; never load the whole file into memory."""
    import hashlib

    digest = hashlib.sha256()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as src, destination.open("wb") as dst:
        for block in iter(lambda: src.read(1024 * 1024), b""):
            digest.update(block)
            dst.write(block)
        dst.flush()
        os.fsync(dst.fileno())
    return digest.hexdigest()


def create_snapshot(
    *,
    database_path: Optional[Path] = None,
    storage_root: Optional[Path] = None,
    backup_root: Optional[Path] = None,
    label: str = "pocketscore",
    moment: Optional[datetime] = None,
) -> SnapshotResult:
    """Create one joint snapshot (database + referenced files) atomically."""
    db_path = Path(database_path) if database_path else dbb.settings_database_path()
    if db_path is None or not db_path.is_file():
        raise SnapshotError(f"database file not found: {db_path}")
    storage = _resolve_storage_root(storage_root)
    root = Path(backup_root) if backup_root else dbb.default_backup_dir(db_path)
    root.mkdir(parents=True, exist_ok=True)

    moment = moment or datetime.now(timezone.utc)
    snapshot_id = f"{label}-snapshot-{moment.strftime('%Y%m%d-%H%M%SZ')}-{uuid.uuid4().hex[:6]}"
    final_dir = root / snapshot_id
    if final_dir.exists():
        raise SnapshotError(f"snapshot already exists: {final_dir}")

    with snapshot_lock(root):
        staging = root / f".inprogress-{snapshot_id}"
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir(parents=True)

        try:
            # 1. database first: it defines which files are part of this snapshot
            db_dir = staging / DATABASE_DIR
            db_result = dbb.create_backup(db_path, db_dir, label=label, moment=moment)
            database_copy = db_result.backup_file

            # 2. references come from the snapshot, not from the live database
            refs = references_from_database(database_copy, storage)
            storage_dir = staging / STORAGE_DIR
            storage_dir.mkdir(parents=True, exist_ok=True)

            file_entries: List[Dict[str, Any]] = []
            missing: List[str] = []
            problems: List[str] = []
            total = 0

            for ref in refs:
                relative = ref["relative_path"]
                source = (storage / relative)
                if not is_within(storage, source):
                    problems.append(f"{relative}: path escapes the storage root")
                    continue
                if not source.is_file():
                    missing.append(relative)
                    continue
                destination = storage_dir / relative
                digest = _copy_streaming(source, destination)
                written = sha256_file(destination)
                if digest != written:
                    problems.append(f"{relative}: copy hash mismatch")
                    continue
                if ref["expected_sha256"] and digest != ref["expected_sha256"]:
                    problems.append(f"{relative}: content does not match its content-addressed name")
                    continue
                if sha256_file(source) != digest:
                    problems.append(f"{relative}: source changed while it was being copied")
                    continue
                size = destination.stat().st_size
                total += size
                file_entries.append({
                    "relative_path": relative,
                    "file_size_bytes": size,
                    "sha256": digest,
                    "media_category": ref["category"],
                    "record_id": ref["record_id"],
                    "column": ref["column"],
                    "backup_status": "SUCCESS",
                })

            # 3. what exists on disk but nothing references (informational)
            referenced = {entry["relative_path"] for entry in file_entries}
            unreferenced = []
            if storage.is_dir():
                for path in sorted(storage.rglob("*")):
                    if not path.is_file():
                        continue
                    relative = path.relative_to(storage).as_posix()
                    if relative.split("/", 1)[0] in {"uploads", "tmp", "temp", "cache"}:
                        continue
                    if relative not in referenced and not any(m == relative for m in missing):
                        unreferenced.append(relative)

            storage_manifest = {
                "manifest_version": MANIFEST_VERSION,
                "backup_id": snapshot_id,
                "created_at_utc": moment.astimezone(timezone.utc).isoformat(),
                "storage_root_identifier": storage.name or "pocketscore-storage",
                "file_count": len(file_entries),
                "total_size_bytes": total,
                "files": file_entries,
                "backup_status": "SUCCESS" if not (missing or problems) else "FAILED",
            }
            (storage_dir / "manifest.json").write_text(json.dumps(storage_manifest, indent=2), encoding="utf-8")

            # The joint manifest is the authority here, so verify the database
            # directly (hash + integrity + foreign keys) rather than through the
            # database-only tool, which also demands every application core table.
            integrity = dbb.integrity_of(database_copy)
            fk_violations = dbb.foreign_key_violations(database_copy)
            schema = dbb.schema_version_of(database_copy)

            database_ok = (
                integrity == 'ok'
                and not fk_violations
                and sha256_file(database_copy) == db_result.sha256
            )
            # Unreferenced files are reported, not fatal: a leftover from a failed
            # upload must not block backups.
            consistency_ok = not missing and not problems
            joint = {
                "manifest_version": MANIFEST_VERSION,
                "backup_id": snapshot_id,
                "created_at_utc": moment.astimezone(timezone.utc).isoformat(),
                "database": {
                    "file": f"{DATABASE_DIR}/{database_copy.name}",
                    "sha256": db_result.sha256,
                    "schema_version": schema["user_version"],
                    "alembic_revision": schema["alembic_revision"],
                    "integrity_check": integrity,
                    "foreign_key_check": "ok" if not fk_violations else f"{len(fk_violations)} violation(s)",
                },
                "storage": {
                    "root_identifier": storage.name or "pocketscore-storage",
                    "file_count": len(file_entries),
                    "total_size_bytes": total,
                    "manifest": STORAGE_MANIFEST,
                    "verification_status": "ok" if consistency_ok else "failed",
                },
                "consistency": {
                    "database_references_verified": not missing and not problems,
                    "missing_files": len(missing),
                    "unreferenced_files": len(unreferenced),
                    "hash_mismatches": len(problems),
                },
                "backup_status": "SUCCESS" if (consistency_ok and database_ok) else "FAILED",
                "source": {"database_name": db_path.name, "storage_root": str(storage)},
            }
            manifest_path = staging / JOINT_MANIFEST
            manifest_path.write_text(json.dumps(joint, indent=2), encoding="utf-8")
            (staging / SNAPSHOT_HASH).write_text(f"{sha256_file(manifest_path)}  {JOINT_MANIFEST}\n", encoding="utf-8")

            if joint["backup_status"] != "SUCCESS":
                raise SnapshotError(
                    "snapshot is inconsistent: "
                    f"missing={len(missing)} problems={len(problems)} unreferenced={len(unreferenced)}"
                    + (f" first problem: {problems[0]}" if problems else "")
                    + (f" first missing: {missing[0]}" if missing else "")
                )

            os.replace(staging, final_dir)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise

    return SnapshotResult(
        snapshot_id=snapshot_id,
        directory=final_dir,
        status="SUCCESS",
        database_sha256=db_result.sha256,
        database_size_bytes=db_result.size_bytes,
        file_count=len(file_entries),
        total_size_bytes=total,
        missing_files=missing,
        problems=problems,
        manifest=joint,
    )


# --------------------------------------------------------------------------- #
# verification
# --------------------------------------------------------------------------- #


@dataclass
class SnapshotVerification:
    directory: Path
    ok: bool
    problems: List[str] = field(default_factory=list)
    manifest: Dict[str, Any] = field(default_factory=dict)
    file_count: int = 0
    total_size_bytes: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "directory": str(self.directory),
            "ok": self.ok,
            "problems": self.problems,
            "file_count": self.file_count,
            "total_size_bytes": self.total_size_bytes,
            "backup_id": self.manifest.get("backup_id"),
            "backup_status": self.manifest.get("backup_status"),
        }


def verify_snapshot(directory: Path, *, deep: bool = True) -> SnapshotVerification:
    directory = Path(directory)
    problems: List[str] = []
    manifest: Dict[str, Any] = {}

    manifest_path = directory / JOINT_MANIFEST
    if not manifest_path.is_file():
        return SnapshotVerification(directory, False, [f"missing {JOINT_MANIFEST}"])
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return SnapshotVerification(directory, False, [f"{JOINT_MANIFEST} is not valid JSON: {exc}"])

    if manifest.get("backup_status") != "SUCCESS":
        problems.append(f"backup_status is {manifest.get('backup_status')!r}")

    hash_file = directory / SNAPSHOT_HASH
    if hash_file.is_file():
        recorded = hash_file.read_text(encoding="utf-8").split()[0]
        if sha256_file(manifest_path) != recorded:
            problems.append("joint manifest hash does not match snapshot.sha256")
    else:
        problems.append(f"missing {SNAPSHOT_HASH}")

    # database half
    db_info = manifest.get("database") or {}
    db_file = directory / str(db_info.get("file", ""))
    if not db_file.is_file():
        problems.append("database backup file is missing")
    else:
        if sha256_file(db_file) != db_info.get("sha256"):
            problems.append("database sha256 does not match the manifest")
        try:
            if dbb.integrity_of(db_file) != "ok":
                problems.append("database integrity_check failed")
            if dbb.foreign_key_violations(db_file):
                problems.append("database foreign_key_check failed")
        except sqlite3.DatabaseError as exc:
            problems.append(f"database is not readable as sqlite: {exc}")

    # files half
    storage_info = manifest.get("storage") or {}
    storage_manifest_path = directory / str(storage_info.get("manifest") or STORAGE_MANIFEST)
    storage_manifest: Dict[str, Any] = {}
    if not storage_manifest_path.is_file():
        problems.append("storage manifest is missing")
    else:
        try:
            storage_manifest = json.loads(storage_manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            problems.append(f"storage manifest is not valid JSON: {exc}")
    entries = storage_manifest.get("files") or []
    if storage_manifest and storage_manifest.get("file_count") != len(entries):
        problems.append("storage manifest file_count does not match its file list")
    if storage_info.get("file_count") is not None and storage_info["file_count"] != len(entries):
        problems.append("joint manifest file_count does not match the storage manifest")

    storage_root = directory / STORAGE_DIR
    total = 0
    for entry in entries:
        relative = entry.get("relative_path", "")
        target = storage_root / relative
        if not is_within(storage_root, target):
            problems.append(f"{relative}: path escapes the snapshot storage root")
            continue
        if not target.is_file():
            problems.append(f"{relative}: file missing from the snapshot")
            continue
        size = target.stat().st_size
        total += size
        if size != entry.get("file_size_bytes"):
            problems.append(f"{relative}: size mismatch")
        if deep and sha256_file(target) != entry.get("sha256"):
            problems.append(f"{relative}: sha256 mismatch")

    # cross-check: every database reference must be present in the snapshot
    if db_file.is_file() and entries:
        declared = {entry["relative_path"] for entry in entries}
        try:
            refs = references_from_database(db_file, directory / STORAGE_DIR)
        except sqlite3.DatabaseError:
            refs = []
        for ref in refs:
            if ref["relative_path"] not in declared:
                problems.append(f"database references {ref['relative_path']} but the snapshot does not contain it")

    return SnapshotVerification(directory, not problems, problems, manifest, len(entries), total)


# --------------------------------------------------------------------------- #
# restore
# --------------------------------------------------------------------------- #


@dataclass
class RestoreOutcome:
    snapshot: Path
    target: Path
    dry_run: bool
    ok: bool
    steps: List[str] = field(default_factory=list)
    safety_copy: Optional[Path] = None
    database_sha256: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "snapshot": str(self.snapshot),
            "target": str(self.target),
            "dry_run": self.dry_run,
            "ok": self.ok,
            "steps": self.steps,
            "safety_copy": str(self.safety_copy) if self.safety_copy else None,
            "database_sha256": self.database_sha256,
        }


def _guard_target(target: Path) -> None:
    """Reuse the database guard: no /data, no staging/production."""
    dbb.assert_safe_target(target)
    dbb.assert_safe_target(target / "database" / "pocketscore.db")


def restore_snapshot(
    snapshot: Path,
    target: Path,
    *,
    dry_run: bool = True,
    force: bool = False,
) -> RestoreOutcome:
    snapshot = Path(snapshot)
    target = Path(target)
    steps: List[str] = []

    _guard_target(target)
    steps.append("target passed the live-data guard")

    verification = verify_snapshot(snapshot)
    if not verification.ok:
        return RestoreOutcome(snapshot, target, dry_run, False,
                              steps + ["snapshot verification failed"] + verification.problems)
    steps.append("snapshot verified (manifest hash, database hash, file hashes, references)")

    manifest = verification.manifest
    db_entry = manifest["database"]
    storage_manifest = json.loads((snapshot / manifest["storage"]["manifest"]).read_text(encoding="utf-8"))

    if target.exists() and any(target.iterdir()):
        if not force:
            return RestoreOutcome(snapshot, target, dry_run, False,
                                  steps + ["target directory is not empty; pass --force in an isolated location"])
        steps.append("--force given: existing target will be replaced")
    else:
        steps.append("target is empty or absent")

    if dry_run:
        steps.append(
            f"dry-run: would restore 1 database ({db_entry['sha256'][:12]}…) and "
            f"{len(storage_manifest['files'])} files ({verification.total_size_bytes} bytes)"
        )
        return RestoreOutcome(snapshot, target, True, True, steps, None, db_entry["sha256"])

    parent = target.parent
    parent.mkdir(parents=True, exist_ok=True)
    staging = parent / f".restore-{target.name}-{uuid.uuid4().hex[:8]}"
    staging.mkdir()

    safety: Optional[Path] = None
    try:
        # 1. database
        (staging / "database").mkdir()
        restored_db = staging / "database" / "pocketscore.db"
        digest = _copy_streaming(snapshot / db_entry["file"], restored_db)
        if digest != db_entry["sha256"]:
            raise SnapshotError("restored database hash does not match the snapshot")
        steps.append("database restored and hash-verified")

        # 2. files
        restored_storage = staging / "storage"
        restored_storage.mkdir()
        for entry in storage_manifest["files"]:
            relative = entry["relative_path"]
            destination = restored_storage / relative
            if not is_within(restored_storage, destination):
                raise SnapshotError(f"{relative}: path escapes the restore target")
            restored_digest = _copy_streaming(snapshot / STORAGE_DIR / relative, destination)
            if restored_digest != entry["sha256"]:
                raise SnapshotError(f"{relative}: restored file hash mismatch")
        steps.append(f"{len(storage_manifest['files'])} files restored and hash-verified")

        # 3. post-restore consistency against the restored halves
        try:
            restored_integrity = dbb.integrity_of(restored_db)
        except sqlite3.DatabaseError as exc:
            raise SnapshotError(f"restored database is not readable as sqlite: {exc}") from exc
        if restored_integrity != "ok":
            raise SnapshotError("restored database integrity_check failed")
        if dbb.foreign_key_violations(restored_db):
            raise SnapshotError("restored database foreign_key_check failed")
        for ref in references_from_database(restored_db, restored_storage):
            if not (restored_storage / ref["relative_path"]).is_file():
                raise SnapshotError(f"restored database references a missing file: {ref['relative_path']}")
        steps.append("restored database references all resolve to restored files")

        # 4. publish
        if target.exists():
            if any(target.iterdir()):
                safety = target.with_name(f"{target.name}.pre-restore-{dbb.stamp()}")
                os.replace(target, safety)
                steps.append(f"previous target moved to {safety.name}")
            else:
                target.rmdir()
        os.replace(staging, target)
        steps.append("atomic directory publish completed")
    except Exception as exc:
        shutil.rmtree(staging, ignore_errors=True)
        if safety is not None and not target.exists():
            os.replace(safety, target)
        return RestoreOutcome(snapshot, target, False, False, steps + [f"restore failed: {exc}"], safety)

    return RestoreOutcome(snapshot, target, False, True, steps, safety, db_entry["sha256"])


# --------------------------------------------------------------------------- #
# listing / retention
# --------------------------------------------------------------------------- #


def list_snapshots(root: Path, *, verify: bool = False) -> List[Tuple[str, Path, str]]:
    root = Path(root)
    if not root.is_dir():
        return []
    found: List[Tuple[str, Path, str]] = []
    for path in sorted(root.iterdir()):
        if not path.is_dir() or path.name.startswith("."):
            continue
        if not (path / JOINT_MANIFEST).is_file():
            continue
        status = "UNKNOWN"
        try:
            status = json.loads((path / JOINT_MANIFEST).read_text(encoding="utf-8")).get("backup_status", "UNKNOWN")
        except json.JSONDecodeError:
            status = "CORRUPT"
        if verify:
            status = "SUCCESS" if verify_snapshot(path, deep=False).ok else "FAILED"
        found.append((path.name, path, status))
    return found


def plan_prune(snapshots: List[Tuple[str, Path, str]], *, daily: int = 7, weekly: int = 4,
               monthly: int = 3) -> Dict[str, Any]:
    """GFS retention over whole snapshots (database and files always travel together)."""

    def when(name: str) -> Optional[datetime]:
        token = name.replace(SNAPSHOT_PREFIX, '')
        parts = token.split('-')
        for index in range(len(parts) - 1):
            try:
                return datetime.strptime(f'{parts[index]}-{parts[index + 1]}',
                                         '%Y%m%d-%H%M%SZ').replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        return None

    usable = [(name, path, status) for name, path, status in snapshots if status == 'SUCCESS']
    skipped = [(name, status) for name, _p, status in snapshots if status != 'SUCCESS']
    ordered = sorted(usable,
                     key=lambda item: when(item[0]) or datetime.min.replace(tzinfo=timezone.utc),
                     reverse=True)
    if not ordered:
        return {'keep': [], 'remove': [], 'skipped': skipped}

    keep: set = set()

    # 1. newest daily snapshots
    for name, _path, _status in ordered[:daily]:
        keep.add(name)

    # 2. newest weekly distinct ISO weeks
    weeks: Dict[Tuple[int, int], str] = {}
    for name, _path, _status in ordered:
        moment = when(name)
        if moment is None:
            continue
        iso = moment.isocalendar()
        weeks.setdefault((iso[0], iso[1]), name)
        if len(weeks) >= weekly:
            break
    keep.update(weeks.values())

    # 3. newest monthly distinct months
    months: Dict[Tuple[int, int], str] = {}
    for name, _path, _status in ordered:
        moment = when(name)
        if moment is None:
            continue
        months.setdefault((moment.year, moment.month), name)
        if len(months) >= monthly:
            break
    keep.update(months.values())

    # 4. never drop the newest overall
    keep.add(ordered[0][0])

    keep_names = [name for name, _p, _s in ordered if name in keep]
    remove = [name for name, _p, _s in ordered if name not in keep]
    return {'keep': keep_names, 'remove': remove, 'skipped': skipped}


def apply_prune(root: Path, plan: Dict[str, Any], *, allow_delete: bool = False) -> List[str]:
    if not allow_delete or not plan.get("keep"):
        return []
    removed: List[str] = []
    root = Path(root)
    for name in plan["remove"]:
        directory = root / name
        try:
            shutil.rmtree(directory)
            removed.append(name)
        except OSError:
            continue
    return removed


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def _print(payload: Dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, default=str))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.ops.project_backup",
        description="Joint database + file snapshots for PocketScore projects.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    snapshot = sub.add_parser("snapshot", help="create a joint snapshot")
    snapshot.add_argument("--database")
    snapshot.add_argument("--storage")
    snapshot.add_argument("--backup-root")
    snapshot.add_argument("--label", default="pocketscore")

    listing = sub.add_parser("list", help="list snapshots")
    listing.add_argument("--backup-root")
    listing.add_argument("--verify", action="store_true")

    verify = sub.add_parser("verify", help="verify one snapshot")
    verify.add_argument("--snapshot", required=True)

    restore = sub.add_parser("restore", help="restore a snapshot into an isolated directory")
    restore.add_argument("--snapshot", required=True)
    restore.add_argument("--target", required=True)
    restore.add_argument("--dry-run", action="store_true")
    restore.add_argument("--force", action="store_true")

    prune = sub.add_parser("prune", help="apply snapshot retention (dry-run unless --apply)")
    prune.add_argument("--backup-root")
    prune.add_argument("--daily", type=int, default=7)
    prune.add_argument("--weekly", type=int, default=4)
    prune.add_argument("--monthly", type=int, default=3)
    prune.add_argument("--apply", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "snapshot":
            result = create_snapshot(
                database_path=Path(args.database) if args.database else None,
                storage_root=Path(args.storage) if args.storage else None,
                backup_root=Path(args.backup_root) if args.backup_root else None,
                label=args.label,
            )
            _print(result.as_dict())
            return EXIT_OK

        if args.command == "list":
            root = Path(args.backup_root) if args.backup_root else dbb.default_backup_dir(dbb.settings_database_path())
            rows = list_snapshots(root, verify=args.verify)
            _print({"count": len(rows), "snapshots": [
                {"snapshot_id": n, "path": str(p), "status": s} for n, p, s in rows
            ]})
            return EXIT_OK

        if args.command == "verify":
            result = verify_snapshot(Path(args.snapshot))
            _print(result.as_dict())
            return EXIT_OK if result.ok else EXIT_FAILED

        if args.command == "restore":
            outcome = restore_snapshot(
                Path(args.snapshot),
                Path(args.target),
                dry_run=args.dry_run or not args.force,
                force=args.force,
            )
            _print(outcome.as_dict())
            return EXIT_OK if outcome.ok else EXIT_FAILED

        if args.command == "prune":
            root = Path(args.backup_root) if args.backup_root else dbb.default_backup_dir(dbb.settings_database_path())
            plan = plan_prune(list_snapshots(root, verify=True), daily=args.daily, weekly=args.weekly, monthly=args.monthly)
            removed = apply_prune(root, plan, allow_delete=args.apply)
            _print({"dry_run": not args.apply, **plan, "removed": removed})
            return EXIT_OK

    except LockBusyError as exc:
        _print({"status": "BUSY", "error": str(exc)})
        return EXIT_REFUSED
    except dbb.UnsafeTargetError as exc:
        _print({"status": "REFUSED", "error": str(exc)})
        return EXIT_REFUSED
    except SnapshotError as exc:
        _print({"status": "FAILED", "error": str(exc)})
        return EXIT_FAILED
    except (OSError, sqlite3.Error) as exc:
        _print({"status": "FAILED", "error": f"{type(exc).__name__}: {exc}"})
        return EXIT_FAILED

    parser.print_help()
    return EXIT_USAGE


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

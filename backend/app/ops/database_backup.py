"""SQLite backup, verification, restore and retention tooling (V1.1-C.2.3.2).

Design notes
------------
* **Consistency**: backups use ``sqlite3.Connection.backup()`` (the online backup
  API). A file copy is *not* used: in WAL mode the ``-wal`` file holds committed
  pages that a plain copy would miss.
* **Atomicity**: the backup is written to a temporary name, verified, then
  ``os.replace``d into place. A failed run never leaves a half file behind.
* **Verification**: every artefact is checked with ``PRAGMA integrity_check`` and
  ``PRAGMA foreign_key_check`` before it is reported as usable.
* **Safety**: restore refuses to touch anything under ``/data`` or any
  staging/production environment. ``--force`` does not lift that guard; it only
  allows replacing an existing *isolated* target file.
* **Secrets**: the manifest records metadata (paths, sizes, hashes, pragma
  results) and never row contents, tokens or user data.

CLI (run from ``backend/``):

    python -m app.ops.database_backup backup
    python -m app.ops.database_backup verify --backup <file>
    python -m app.ops.database_backup restore --backup <file> --target <file> [--dry-run]
    python -m app.ops.database_backup list
    python -m app.ops.database_backup prune [--apply]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import sys
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

BACKUP_SUFFIXES = (".sqlite3", ".db", ".sqlite")
MANIFEST_SUFFIX = ".manifest.json"
SHA_SUFFIX = ".sha256"
BACKUP_METHOD = "sqlite3.backup_api"
MANIFEST_VERSION = 1

# Tables the application genuinely needs; a backup missing one of these is not
# usable even when integrity_check passes.
CORE_TABLES = (
    "audio_assets",
    "music_documents",
    "music_events",
    "music_tracks",
    "transcription_jobs",
)

# Any path under these roots is treated as live data and never restored over.
PROTECTED_ROOTS = ("/data",)
PROTECTED_ENVIRONMENTS = {"staging", "production"}

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2
EXIT_REFUSED = 3


class BackupError(RuntimeError):
    """Raised for a failed backup/verify/restore operation."""


class UnsafeTargetError(BackupError):
    """Raised when an operation would touch live data."""


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def stamp(moment: Optional[datetime] = None) -> str:
    return (moment or utc_now()).strftime("%Y%m%d-%H%M%SZ")


def sha256_file(path: Path, chunk: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(chunk), b""):
            digest.update(block)
    return digest.hexdigest()


def settings_database_path() -> Optional[Path]:
    """Resolve the configured database file, without creating anything."""
    from app.core.config import get_settings

    settings = get_settings()
    path = settings.sqlite_file_path
    return Path(path) if path is not None else None


def default_backup_dir(db_path: Optional[Path] = None) -> Path:
    """``POCKETSCORE_BACKUP_DIR`` wins; otherwise a sibling of the database.

    Deliberately never defaults into the source tree: the database lives on a
    volume in production, so its sibling directory does too.
    """
    override = os.environ.get("POCKETSCORE_BACKUP_DIR")
    if override:
        return Path(override).expanduser()
    if db_path is not None:
        return db_path.parent / "backups"
    return Path("./data/backups")


def _pragma(connection: sqlite3.Connection, statement: str) -> List[Tuple]:
    return list(connection.execute(statement).fetchall())


def integrity_of(path: Path) -> str:
    with closing(sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)) as connection:
        rows = _pragma(connection, "PRAGMA integrity_check")
    return rows[0][0] if rows else "no-result"


def foreign_key_violations(path: Path) -> List[Tuple]:
    with closing(sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)) as connection:
        return _pragma(connection, "PRAGMA foreign_key_check")


def schema_version_of(path: Path) -> Dict[str, Any]:
    with closing(sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)) as connection:
        user_version = _pragma(connection, "PRAGMA user_version")[0][0]
        tables = {row[0] for row in _pragma(connection, "SELECT name FROM sqlite_master WHERE type='table'")}
        alembic: Optional[str] = None
        if "alembic_version" in tables:
            rows = _pragma(connection, "SELECT version_num FROM alembic_version")
            alembic = rows[0][0] if rows else None
    return {"user_version": user_version, "alembic_revision": alembic, "tables": sorted(tables)}


def missing_core_tables(tables: Iterable[str]) -> List[str]:
    present = set(tables)
    return [name for name in CORE_TABLES if name not in present]


def _normalise(path: Path) -> str:
    """Case-insensitive, absolute form used for the protected-root comparison."""
    return os.path.normcase(os.path.abspath(str(path)))


def _protected(path: Path) -> Optional[str]:
    """Return a reason when ``path`` is considered live data."""
    resolved = path.expanduser().resolve()
    target_key = _normalise(resolved)
    for root in PROTECTED_ROOTS:
        root_key = _normalise(Path(root))
        if target_key == root_key or target_key.startswith(root_key + os.sep):
            return f"target is inside the protected root {root}"
    environment = os.environ.get("POCKETSCORE_ENVIRONMENT", "").strip().lower()
    if environment in PROTECTED_ENVIRONMENTS:
        return f"POCKETSCORE_ENVIRONMENT={environment} is a live environment"
    return None


def assert_safe_target(path: Path) -> None:
    reason = _protected(path)
    if reason:
        raise UnsafeTargetError(
            f"refusing to write {path}: {reason}. Restores are only allowed in an "
            "isolated test location; production/staging restores need a dedicated "
            "operations window."
        )


# --------------------------------------------------------------------------- #
# backup
# --------------------------------------------------------------------------- #


@dataclass
class BackupResult:
    backup_id: str
    backup_file: Path
    manifest_file: Path
    sha256: str
    size_bytes: int
    status: str
    details: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "backup_id": self.backup_id,
            "backup_file": str(self.backup_file),
            "manifest_file": str(self.manifest_file),
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "status": self.status,
            **self.details,
        }


def _application_version() -> Optional[str]:
    try:
        from app import __version__

        return str(__version__)
    except Exception:  # pragma: no cover - version import is optional
        return None


def _copy_via_backup_api(source: Path, destination: Path) -> None:
    """Consistent online copy through the SQLite backup API.

    `sqlite3.connect()` used as a context manager only wraps a transaction; it
    does not close the handle. On Windows an open handle blocks unlink/replace,
    so both connections are closed explicitly.
    """
    with (
        closing(sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)) as src,
        closing(sqlite3.connect(destination)) as dst,
    ):
        src.backup(dst)
        dst.commit()


def create_backup(
    db_path: Optional[Path] = None,
    backup_dir: Optional[Path] = None,
    *,
    label: str = "pocketscore",
    moment: Optional[datetime] = None,
) -> BackupResult:
    """Create one verified backup and its manifest."""
    source = Path(db_path) if db_path is not None else settings_database_path()
    if source is None:
        raise BackupError("no SQLite database is configured (POCKETSCORE_DATABASE_URL)")
    if not source.is_file():
        raise BackupError(f"database file not found: {source}")

    target_dir = Path(backup_dir) if backup_dir is not None else default_backup_dir(source)
    target_dir.mkdir(parents=True, exist_ok=True)
    moment = moment or utc_now()
    backup_id = f"{label}-{stamp(moment)}"
    final_db = target_dir / f"{backup_id}.sqlite3"
    if final_db.exists():
        raise BackupError(f"backup already exists, refusing to overwrite: {final_db}")

    partial = target_dir / f".{backup_id}.partial"
    if partial.exists():
        partial.unlink()

    try:
        # The online backup API reads through the WAL, so committed pages that
        # still live in -wal are included.
        _copy_via_backup_api(source, partial)
    except sqlite3.Error as exc:
        partial.unlink(missing_ok=True)
        raise BackupError(f"sqlite backup failed: {exc}") from exc
    except Exception:
        partial.unlink(missing_ok=True)
        raise

    try:
        size = partial.stat().st_size
        if size <= 0:
            raise BackupError("backup file is empty")
        integrity = integrity_of(partial)
        if integrity != "ok":
            raise BackupError(f"integrity_check on the backup returned {integrity!r}")
        violations = foreign_key_violations(partial)
        if violations:
            raise BackupError(f"foreign_key_check reported {len(violations)} violation(s)")
        digest = sha256_file(partial)
        os.replace(partial, final_db)
    except Exception:
        partial.unlink(missing_ok=True)
        raise

    info = schema_version_of(final_db)
    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "backup_id": backup_id,
        "created_at_utc": moment.astimezone(timezone.utc).isoformat(),
        "database_name": source.name,
        "database_engine": "sqlite",
        "database_schema_version": info["user_version"],
        "alembic_revision": info["alembic_revision"],
        "sqlite_version": sqlite3.sqlite_version,
        "backup_method": BACKUP_METHOD,
        "backup_file": final_db.name,
        "backup_size_bytes": final_db.stat().st_size,
        "sha256": digest,
        "integrity_check": integrity,
        "foreign_key_check": "ok",
        "core_tables_present": not missing_core_tables(info["tables"]),
        "backup_status": "SUCCESS",
        "application_version": _application_version(),
        "source_path": str(source),
    }

    manifest_file = target_dir / f"{backup_id}{MANIFEST_SUFFIX}"
    sha_file = target_dir / f"{backup_id}{SHA_SUFFIX}"
    try:
        manifest_file.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        sha_file.write_text(f"{digest}  {final_db.name}\n", encoding="utf-8")
    except OSError as exc:
        raise BackupError(f"could not write manifest: {exc}") from exc

    # Final self-check: the manifest must describe the file that is on disk.
    if sha256_file(final_db) != digest:
        raise BackupError("hash changed after the atomic rename")

    return BackupResult(
        backup_id=backup_id,
        backup_file=final_db,
        manifest_file=manifest_file,
        sha256=digest,
        size_bytes=manifest["backup_size_bytes"],
        status="SUCCESS",
        details={
            "integrity_check": integrity,
            "foreign_key_check": "ok",
            "schema_version": info["user_version"],
            "alembic_revision": info["alembic_revision"],
            "core_tables_present": manifest["core_tables_present"],
        },
    )


# --------------------------------------------------------------------------- #
# verify
# --------------------------------------------------------------------------- #


@dataclass
class VerifyResult:
    backup_file: Path
    ok: bool
    problems: List[str]
    manifest: Dict[str, Any]
    computed_sha256: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "backup_file": str(self.backup_file),
            "ok": self.ok,
            "problems": self.problems,
            "manifest": self.manifest,
            "computed_sha256": self.computed_sha256,
        }


def manifest_path_for(backup_file: Path) -> Path:
    stem = backup_file.name
    for suffix in (".sqlite3", ".sqlite", ".db"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    return backup_file.with_name(stem + MANIFEST_SUFFIX)


def verify_backup(backup_file: Path, *, require_manifest: bool = True) -> VerifyResult:
    path = Path(backup_file)
    problems: List[str] = []
    manifest: Dict[str, Any] = {}

    if not path.is_file():
        return VerifyResult(path, False, [f"backup file not found: {path}"], {})

    manifest_file = manifest_path_for(path)
    if manifest_file.is_file():
        try:
            manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            problems.append(f"manifest is not valid JSON: {exc}")
    elif require_manifest:
        problems.append(f"manifest missing: {manifest_file.name}")

    if path.stat().st_size == 0:
        problems.append("backup file is empty")

    computed: Optional[str] = None
    try:
        computed = sha256_file(path)
    except OSError as exc:
        problems.append(f"could not hash backup: {exc}")

    if manifest.get("sha256") and computed and manifest["sha256"] != computed:
        problems.append("sha256 does not match the manifest")

    try:
        integrity = integrity_of(path)
        if integrity != "ok":
            problems.append(f"integrity_check returned {integrity!r}")
    except sqlite3.DatabaseError as exc:
        problems.append(f"cannot open backup as sqlite: {exc}")

    try:
        violations = foreign_key_violations(path)
        if violations:
            problems.append(f"foreign_key_check reported {len(violations)} violation(s)")
    except sqlite3.DatabaseError as exc:
        problems.append(f"foreign_key_check failed: {exc}")

    try:
        info = schema_version_of(path)
        missing = missing_core_tables(info["tables"])
        if missing:
            problems.append(f"core tables missing: {', '.join(missing)}")
        declared = manifest.get("database_schema_version")
        if declared is not None and int(declared) != int(info["user_version"]):
            problems.append(
                f"schema version mismatch: manifest={declared} file={info['user_version']}"
            )
    except sqlite3.DatabaseError as exc:
        problems.append(f"cannot read schema: {exc}")

    return VerifyResult(path, not problems, problems, manifest, computed)


# --------------------------------------------------------------------------- #
# restore
# --------------------------------------------------------------------------- #


@dataclass
class RestoreResult:
    backup_file: Path
    target: Path
    dry_run: bool
    ok: bool
    steps: List[str]
    pre_existing_safety_copy: Optional[Path] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "backup_file": str(self.backup_file),
            "target": str(self.target),
            "dry_run": self.dry_run,
            "ok": self.ok,
            "steps": self.steps,
            "safety_copy": str(self.pre_existing_safety_copy) if self.pre_existing_safety_copy else None,
        }


def restore_backup(
    backup_file: Path,
    target: Path,
    *,
    dry_run: bool = True,
    force: bool = False,
    safety_backup: bool = True,
    allow_manifest_missing: bool = False,
) -> RestoreResult:
    """Restore ``backup_file`` onto ``target`` after verifying both sides."""
    backup = Path(backup_file)
    destination = Path(target)
    steps: List[str] = []

    # 1. never touch live data, regardless of --force
    assert_safe_target(destination)
    steps.append("target passed the live-data guard")

    # 2. the source must be usable before anything is written
    verification = verify_backup(backup, require_manifest=not allow_manifest_missing)
    if not verification.ok:
        return RestoreResult(backup, destination, dry_run, False,
                             steps + ["backup verification failed"] + verification.problems)
    steps.append("backup verified (manifest, sha256, integrity, foreign keys, core tables)")

    # 3. inspect the destination
    exists = destination.exists()
    if exists:
        stat = destination.stat()
        steps.append(
            f"target exists: size={stat.st_size} bytes, "
            f"mtime={datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat()}"
        )
        if not force:
            return RestoreResult(
                backup,
                destination,
                dry_run,
                False,
                steps
                + [
                    "refusing to overwrite an existing file without --force",
                    "pass --force only in an isolated test location",
                ],
            )
        steps.append("--force given: existing target will be replaced")
    else:
        steps.append("target does not exist")

    if dry_run:
        steps.append("dry-run: no file was written")
        return RestoreResult(backup, destination, True, True, steps)

    destination.parent.mkdir(parents=True, exist_ok=True)

    # 4. safety copy of whatever is there now
    safety: Optional[Path] = None
    if exists and safety_backup:
        safety = destination.with_name(destination.name + f".pre-restore-{stamp()}")
        shutil.copy2(destination, safety)
        steps.append(f"safety copy written: {safety.name}")

    # 5. copy to a temporary sibling, verify, then atomically replace
    temp_copy = destination.with_name(f".{destination.name}.restore-partial")
    temp_copy.unlink(missing_ok=True)
    try:
        shutil.copy2(backup, temp_copy)
        if temp_copy.stat().st_size == 0:
            raise BackupError("restored file is empty")
        if integrity_of(temp_copy) != "ok":
            raise BackupError("integrity_check failed on the restored copy")
        if foreign_key_violations(temp_copy):
            raise BackupError("foreign_key_check failed on the restored copy")
        if sha256_file(temp_copy) != sha256_file(backup):
            raise BackupError("restored copy does not match the backup hash")
        steps.append("temporary copy verified (integrity, foreign keys, sha256)")
        os.replace(temp_copy, destination)
        steps.append("atomic replace completed")
    except Exception as exc:
        temp_copy.unlink(missing_ok=True)
        return RestoreResult(backup, destination, False, False, steps + [f"restore failed: {exc}"], safety)

    # 6. post-restore verification on the real target
    try:
        post = verify_backup(destination, require_manifest=False)
        if not post.ok:
            return RestoreResult(backup, destination, False, False,
                                 steps + ["post-restore verification failed"] + post.problems, safety)
        steps.append("post-restore verification passed")
    except Exception as exc:  # pragma: no cover - defensive
        return RestoreResult(backup, destination, False, False, steps + [f"post-restore check error: {exc}"], safety)

    return RestoreResult(backup, destination, False, True, steps, safety)


# --------------------------------------------------------------------------- #
# listing / retention
# --------------------------------------------------------------------------- #


@dataclass
class BackupEntry:
    backup_id: str
    file: Path
    created_at: Optional[datetime]
    size_bytes: int
    verified: Optional[bool] = None
    detail: str = ""

    @property
    def key(self) -> datetime:
        return self.created_at or datetime.min.replace(tzinfo=timezone.utc)


def _parse_stamp(name: str) -> Optional[datetime]:
    # expected: <label>-YYYYMMDD-HHMMSSZ
    parts = name.rsplit("-", 2)
    if len(parts) != 3:
        return None
    _, day, clock = parts
    if not clock.endswith("Z"):
        return None
    try:
        return datetime.strptime(f"{day}-{clock}", "%Y%m%d-%H%M%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def list_backups(backup_dir: Optional[Path] = None, *, db_path: Optional[Path] = None,
                 verify: bool = False) -> List[BackupEntry]:
    directory = Path(backup_dir) if backup_dir is not None else default_backup_dir(
        db_path if db_path is not None else settings_database_path()
    )
    if not directory.is_dir():
        return []

    entries: List[BackupEntry] = []
    for path in sorted(directory.iterdir()):
        if not path.is_file():
            continue
        if path.name.startswith(".") or not path.name.endswith(BACKUP_SUFFIXES):
            continue
        if not manifest_path_for(path).is_file():
            # not one of ours: never list, never prune
            continue
        created = _parse_stamp(path.name[: -len(".sqlite3")] if path.name.endswith(".sqlite3") else path.stem)
        entry = BackupEntry(
            backup_id=path.stem,
            file=path,
            created_at=created,
            size_bytes=path.stat().st_size,
        )
        if verify:
            result = verify_backup(path)
            entry.verified = result.ok
            entry.detail = "; ".join(result.problems)
        entries.append(entry)
    entries.sort(key=lambda item: item.key)
    return entries


@dataclass
class PrunePlan:
    keep: List[BackupEntry]
    remove: List[BackupEntry]
    skipped: List[Tuple[BackupEntry, str]]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "keep": [e.backup_id for e in self.keep],
            "remove": [e.backup_id for e in self.remove],
            "skipped": [[e.backup_id, reason] for e, reason in self.skipped],
        }


def plan_prune(
    entries: Sequence[BackupEntry],
    *,
    daily: int = 7,
    weekly: int = 4,
    monthly: int = 3,
) -> PrunePlan:
    """Grandfather-father-son retention over already-sorted entries."""
    valid = [e for e in entries if e.verified is not False]
    skipped = [(e, "unverified or failed verification") for e in entries if e.verified is False]
    newest_first = sorted(valid, key=lambda e: e.key, reverse=True)
    if not newest_first:
        return PrunePlan(keep=[], remove=[], skipped=skipped)

    keep: Dict[Path, BackupEntry] = {}

    # newest N daily
    for entry in newest_first[:daily]:
        keep[entry.file] = entry

    # newest N distinct ISO weeks, then months
    def bucket(entries_in: List[BackupEntry], key_fn) -> None:
        seen: Dict[Any, int] = {}
        for entry in entries_in:
            if entry.created_at is None:
                continue
            bucket_key = key_fn(entry.created_at)
            count = seen.get(bucket_key, 0)
            if count >= 1:
                continue
            seen[bucket_key] = count + 1
            keep[entry.file] = entry

    weeks: Dict[Tuple[int, int], List[BackupEntry]] = {}
    for entry in newest_first:
        if entry.created_at is None:
            continue
        iso = entry.created_at.isocalendar()
        weeks.setdefault((iso[0], iso[1]), []).append(entry)
    for _, group in sorted(weeks.items(), reverse=True)[:weekly]:
        keep[group[0].file] = group[0]

    months: Dict[Tuple[int, int], List[BackupEntry]] = {}
    for entry in newest_first:
        if entry.created_at is None:
            continue
        months.setdefault((entry.created_at.year, entry.created_at.month), []).append(entry)
    for _, group in sorted(months.items(), reverse=True)[:monthly]:
        keep[group[0].file] = group[0]

    # never drop the single newest valid backup, and never drop everything
    keep[newest_first[0].file] = newest_first[0]

    remove = [e for e in valid if e.file not in keep]
    return PrunePlan(keep=sorted(keep.values(), key=lambda e: e.key, reverse=True), remove=remove, skipped=skipped)


def apply_prune(plan: PrunePlan, *, allow_delete: bool = False) -> List[str]:
    """Delete planned files. Deletion only happens with ``allow_delete``."""
    removed: List[str] = []
    if not allow_delete:
        return removed
    if not plan.keep:  # defensive: never delete without a surviving backup
        raise BackupError("refusing to delete: no backup would remain")
    for entry in plan.remove:
        manifest = manifest_path_for(entry.file)
        sha_file = entry.file.with_name(entry.backup_id + SHA_SUFFIX)
        try:
            entry.file.unlink()
            manifest.unlink(missing_ok=True)
            sha_file.unlink(missing_ok=True)
            removed.append(entry.backup_id)
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
        prog="python -m app.ops.database_backup",
        description="Backup, verify, restore and prune the PocketScore SQLite database.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    backup = sub.add_parser("backup", help="create a verified online backup")
    backup.add_argument("--database", help="database file (defaults to POCKETSCORE_DATABASE_URL)")
    backup.add_argument("--backup-dir", help="where to write backups (defaults to POCKETSCORE_BACKUP_DIR)")
    backup.add_argument("--label", default="pocketscore", help="prefix for the backup file name")

    verify = sub.add_parser("verify", help="verify one backup against its manifest")
    verify.add_argument("--backup", required=True, help="path to the backup file")

    restore = sub.add_parser("restore", help="restore a backup into an isolated target")
    restore.add_argument("--backup", required=True)
    restore.add_argument("--target", required=True, help="destination database file")
    restore.add_argument("--dry-run", action="store_true", help="default: show the plan only")
    restore.add_argument("--verify-only", action="store_true", help="verify the backup and stop")
    restore.add_argument("--force", action="store_true",
                         help="replace an existing target (isolated locations only)")
    restore.add_argument("--no-backup", dest="safety_backup", action="store_false",
                         help="skip the safety copy of the current target")
    restore.add_argument("--allow-manifest-missing", action="store_true",
                         help="verify without requiring a manifest")

    listing = sub.add_parser("list", help="list backups in the backup directory")
    listing.add_argument("--backup-dir")
    listing.add_argument("--verify", action="store_true", help="verify every backup while listing")

    prune = sub.add_parser("prune", help="apply the retention policy (dry-run unless --apply)")
    prune.add_argument("--backup-dir")
    prune.add_argument("--daily", type=int, default=7)
    prune.add_argument("--weekly", type=int, default=4)
    prune.add_argument("--monthly", type=int, default=3)
    prune.add_argument("--apply", action="store_true", help="actually delete (default is dry-run)")

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "backup":
            result = create_backup(
                db_path=Path(args.database) if args.database else None,
                backup_dir=Path(args.backup_dir) if args.backup_dir else None,
                label=args.label,
            )
            _print(result.as_dict())
            return EXIT_OK

        if args.command == "verify":
            result = verify_backup(Path(args.backup))
            _print(result.as_dict())
            return EXIT_OK if result.ok else EXIT_FAILED

        if args.command == "restore":
            if args.verify_only:
                result = verify_backup(Path(args.backup))
                _print(result.as_dict())
                return EXIT_OK if result.ok else EXIT_FAILED
            outcome = restore_backup(
                Path(args.backup),
                Path(args.target),
                dry_run=not args.force or args.dry_run,
                force=args.force,
                safety_backup=args.safety_backup,
                allow_manifest_missing=args.allow_manifest_missing,
            )
            _print(outcome.as_dict())
            return EXIT_OK if outcome.ok else EXIT_FAILED

        if args.command == "list":
            entries = list_backups(Path(args.backup_dir) if args.backup_dir else None, verify=args.verify)
            _print({
                "count": len(entries),
                "backups": [
                    {
                        "backup_id": e.backup_id,
                        "file": e.file.name,
                        "created_at_utc": e.created_at.isoformat() if e.created_at else None,
                        "size_bytes": e.size_bytes,
                        "verified": e.verified,
                    }
                    for e in entries
                ],
            })
            return EXIT_OK

        if args.command == "prune":
            entries = list_backups(Path(args.backup_dir) if args.backup_dir else None, verify=True)
            plan = plan_prune(entries, daily=args.daily, weekly=args.weekly, monthly=args.monthly)
            removed = apply_prune(plan, allow_delete=args.apply)
            payload = {"dry_run": not args.apply, **plan.as_dict(), "removed": removed}
            _print(payload)
            return EXIT_OK

    except UnsafeTargetError as exc:
        _print({"status": "REFUSED", "error": str(exc)})
        return EXIT_REFUSED
    except BackupError as exc:
        _print({"status": "FAILED", "error": str(exc)})
        return EXIT_FAILED
    except sqlite3.Error as exc:
        _print({"status": "FAILED", "error": f"sqlite error: {exc}"})
        return EXIT_FAILED

    parser.print_help()
    return EXIT_USAGE


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    sys.exit(main())

"""Read-only storage integrity auditing for PocketScore AI (V1.1-C.2.3.3).

Answers four questions about the file store:

* which database rows point at a file, and does that file exist?
* which files on disk are referenced by nothing (orphans)?
* does a referenced path escape the storage root (traversal / symlink)?
* does the content still match the content-addressed name (sha256)?

Everything is read-only. Orphans are reported, never deleted.

CLI (run from ``backend/``):

    python -m app.ops.storage_audit scan --storage <dir>
    python -m app.ops.storage_audit verify --storage <dir>
    python -m app.ops.storage_audit orphans --storage <dir>
    python -m app.ops.storage_audit missing --storage <dir>
    python -m app.ops.storage_audit report --storage <dir>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
from urllib.parse import unquote

# Directories that legitimately hold in-flight or regenerable files. Their
# contents are reported separately so they are not mistaken for business data.
TRANSIENT_DIRS = {"uploads", "tmp", "temp", "cache"}

ARTWORK_URL_PREFIX = "/static/artwork/"
SNIFF_BYTES = 12

CATEGORY_AUDIO = "audio"
CATEGORY_ARTWORK = "artwork"
CATEGORY_OTHER = "other"

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_ERROR = 2


@dataclass
class Reference:
    """One database field that points into the file store."""

    record_id: str
    table: str
    column: str
    raw_value: str
    category: str
    relative_path: Optional[str] = None
    resolved: Optional[Path] = None
    exists: bool = False
    size_bytes: int = 0
    expected_sha256: Optional[str] = None
    actual_sha256: Optional[str] = None
    problems: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "record_id": self.record_id,
            "table": self.table,
            "column": self.column,
            "category": self.category,
            "relative_path": self.relative_path,
            "exists": self.exists,
            "size_bytes": self.size_bytes,
            "expected_sha256": self.expected_sha256,
            "actual_sha256": self.actual_sha256,
            "problems": self.problems,
        }


@dataclass
class AuditReport:
    storage_root: str
    references: List[Reference] = field(default_factory=list)
    files: List[Dict[str, Any]] = field(default_factory=list)
    orphans: List[str] = field(default_factory=list)
    missing: List[Dict[str, Any]] = field(default_factory=list)
    out_of_root: List[Dict[str, Any]] = field(default_factory=list)
    hash_mismatches: List[Dict[str, Any]] = field(default_factory=list)
    duplicates: List[Dict[str, Any]] = field(default_factory=list)
    artwork_missing: List[Dict[str, Any]] = field(default_factory=list)
    unreadable: List[str] = field(default_factory=list)
    transient_files: int = 0

    @property
    def ok(self) -> bool:
        return not (self.missing or self.out_of_root or self.hash_mismatches or self.artwork_missing or self.unreadable)

    def summary(self) -> Dict[str, Any]:
        referenced = [r for r in self.references if r.exists]
        return {
            "storage_root": self.storage_root,
            "file_count": len(self.files),
            "total_size_bytes": sum(f["size_bytes"] for f in self.files),
            "referenced_files": len({r.relative_path for r in referenced}),
            "reference_rows": len(self.references),
            "orphan_files": len(self.orphans),
            "missing_files": len(self.missing),
            "hash_mismatches": len(self.hash_mismatches),
            "out_of_root": len(self.out_of_root),
            "duplicate_references": len(self.duplicates),
            "artwork_missing": len(self.artwork_missing),
            "unreadable_files": len(self.unreadable),
            "transient_files": self.transient_files,
            "ok": self.ok,
        }

    def as_dict(self) -> Dict[str, Any]:
        return {
            **self.summary(),
            "references": [r.as_dict() for r in self.references],
            "orphans": self.orphans,
            "missing": self.missing,
            "out_of_root": self.out_of_root,
            "hash_mismatches": self.hash_mismatches,
            "duplicates": self.duplicates,
            "artwork_missing": self.artwork_missing,
            "unreadable": self.unreadable,
        }


# --------------------------------------------------------------------------- #
# path handling
# --------------------------------------------------------------------------- #


def sha256_file(path: Path, chunk: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(chunk), b""):
            digest.update(block)
    return digest.hexdigest()


def normalised(path: Path) -> str:
    return os.path.normcase(os.path.abspath(str(path)))


def is_within(root: Path, candidate: Path) -> bool:
    """True when ``candidate`` really lives under ``root`` after resolving links."""
    root_key = normalised(root.resolve())
    try:
        candidate_key = normalised(candidate.resolve())
    except OSError:
        return False
    return candidate_key == root_key or candidate_key.startswith(root_key + os.sep)


def artwork_relative_path(raw: str) -> Optional[str]:
    """``/static/artwork/<name>`` (a URL) → ``artwork/<name>`` (a relative path)."""
    if not raw:
        return None
    if raw.startswith(ARTWORK_URL_PREFIX):
        name = unquote(raw[len(ARTWORK_URL_PREFIX):]).lstrip("/")
        return f"artwork/{name}" if name else None
    if raw.startswith('/static/'):
        return None
    if raw.startswith('/'):
        return None
    if raw.startswith(('http://', 'https://', 'data:')):
        return None  # remote artwork lives outside the local store
    return raw


def resolve_reference(storage_root: Path, raw: str, category: str) -> tuple[Optional[str], Optional[Path]]:
    relative = artwork_relative_path(raw) if category == CATEGORY_ARTWORK else raw
    if not relative:
        return None, None
    relative = relative.replace("\\", "/").lstrip("/")
    candidate = (storage_root / relative).resolve()
    return relative, candidate


def expected_hash_for(relative: str) -> Optional[str]:
    """Content-addressed names are ``<sha256><ext>``; artwork uses the asset sha."""
    stem = Path(relative).stem
    return stem if re.fullmatch(r"[0-9a-f]{64}", stem) else None


# --------------------------------------------------------------------------- #
# database references
# --------------------------------------------------------------------------- #


def collect_references(session: Any, storage_root: Path) -> List[Reference]:
    """Read every file reference from the ORM models."""
    from sqlalchemy import select

    from app.models.audio import AudioAssetRecord

    references: List[Reference] = []
    rows = session.execute(select(AudioAssetRecord)).scalars().all()
    for record in rows:
        for column, value, category in (
            ("stored_path", record.stored_path, CATEGORY_AUDIO),
            ("artwork_path", record.artwork_path, CATEGORY_ARTWORK),
        ):
            if not value:
                continue
            relative, resolved = resolve_reference(storage_root, value, category)
            ref = Reference(
                record_id=record.id,
                table="audio_assets",
                column=column,
                raw_value=value,
                category=category,
                relative_path=relative,
                resolved=resolved,
                expected_sha256=expected_hash_for(relative) if relative else None,
            )
            if resolved is not None and not is_within(storage_root, resolved):
                ref.problems.append("path escapes the storage root")
            references.append(ref)
    return references


def _fill_file_facts(ref: Reference) -> None:
    if ref.resolved is None:
        ref.problems.append("unresolvable reference")
        return
    try:
        stat = ref.resolved.stat()
    except OSError:
        ref.exists = False
        return
    ref.exists = True
    ref.size_bytes = stat.st_size


def _check_signature(ref: Reference) -> Optional[str]:
    """Cheap sanity check on the first bytes of an audio file."""
    if ref.category != CATEGORY_AUDIO or not ref.resolved or not ref.resolved.is_file():
        return None
    try:
        with ref.resolved.open("rb") as handle:
            head = handle.read(SNIFF_BYTES)
    except OSError:
        return None
    suffix = ref.resolved.suffix.lower()
    if suffix == ".wav":
        return None if head[:4] == b"RIFF" and head[8:12] == b"WAVE" else "wav header mismatch"
    if suffix == ".mp3":
        return None if head[:3] == b"ID3" or head[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2") else "mp3 frame sync not found"
    if suffix == ".flac":
        return None if head[:4] == b"fLaC" else "flac magic mismatch"
    return None


def audit_storage(
    storage_root: Path,
    *,
    session: Any = None,
    verify_hashes: bool = True,
    check_signatures: bool = False,
) -> AuditReport:
    root = Path(storage_root).resolve()
    report = AuditReport(storage_root=str(root))

    if session is not None:
        report.references = collect_references(session, root)

    # ---- files on disk ----
    referenced_paths: Dict[str, int] = {}
    for ref in report.references:
        if ref.relative_path:
            referenced_paths[ref.relative_path] = referenced_paths.get(ref.relative_path, 0) + 1

    if root.is_dir():
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(root).as_posix()
            top = relative.split("/", 1)[0]
            if top in TRANSIENT_DIRS:
                report.transient_files += 1
                continue
            try:
                size = path.stat().st_size
            except OSError:
                report.unreadable.append(relative)
                continue
            report.files.append({"relative_path": relative, "size_bytes": size})
            if relative not in referenced_paths:
                report.orphans.append(relative)
    elif session is not None and report.references:
        # nothing on disk at all: every reference is missing
        pass

    # ---- per-reference checks ----
    for ref in report.references:
        _fill_file_facts(ref)
        if ref.resolved is not None and is_within(root, ref.resolved):
            entry = ref.as_dict()
            if not ref.exists:
                report.missing.append(entry)
                continue
            if ref.category == CATEGORY_ARTWORK and not ref.resolved.is_file():
                report.artwork_missing.append(entry)
            if verify_hashes and ref.expected_sha256:
                try:
                    ref.actual_sha256 = sha256_file(ref.resolved)
                except OSError:
                    report.unreadable.append(ref.relative_path or ref.raw_value)
                    continue
                if ref.actual_sha256 != ref.expected_sha256:
                    report.hash_mismatches.append({**ref.as_dict(), "problem": "content hash does not match the file name"})
        elif ref.resolved is not None:
            report.out_of_root.append(ref.as_dict())

        if check_signatures:
            problem = _check_signature(ref)
            if problem:
                report.hash_mismatches.append({**ref.as_dict(), "problem": problem})

    for relative, count in referenced_paths.items():
        if count > 1:
            report.duplicates.append({"relative_path": relative, "reference_count": count})

    # artwork rows whose file is missing are already in `missing`; keep a
    # dedicated list too so operators can see them separately
    report.artwork_missing = [m for m in report.missing if m["category"] == CATEGORY_ARTWORK]

    return report


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def _open_session(database: Optional[Path]) -> Any:
    """Point the app at a specific database for the audit (read-only usage)."""
    if database is not None:
        os.environ["POCKETSCORE_DATABASE_URL"] = f"sqlite:///{Path(database).as_posix()}"
    from app.core.db import dispose_engine, get_session_factory, init_db

    init_db()
    factory = get_session_factory()
    session = factory()
    session._ps_dispose = lambda: (session.close(), dispose_engine())  # type: ignore[attr-defined]
    return session


def _default_storage() -> Path:
    from app.core.config import get_settings

    return get_settings().storage_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.ops.storage_audit",
        description="Read-only audit of the PocketScore file store against the database.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("scan", "summary plus every finding"),
        ("verify", "hash every referenced file"),
        ("orphans", "list files nothing references"),
        ("missing", "list references whose file is gone"),
        ("report", "full structured report"),
    ):
        sub_parser = sub.add_parser(name, help=help_text)
        sub_parser.add_argument("--storage", help="storage root (defaults to POCKETSCORE_STORAGE_DIR)")
        sub_parser.add_argument("--database", help="database file (defaults to POCKETSCORE_DATABASE_URL)")
        sub_parser.add_argument("--no-hash", action="store_true", help="skip sha256 verification")
        sub_parser.add_argument("--signatures", action="store_true", help="also check audio magic bytes")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    storage = Path(args.storage) if args.storage else _default_storage()
    session = None
    try:
        session = _open_session(Path(args.database) if args.database else None)
        report = audit_storage(
            storage,
            session=session,
            verify_hashes=not args.no_hash,
            check_signatures=args.signatures,
        )
    except Exception as exc:  # noqa: BLE001 - CLI must report, not traceback
        print(json.dumps({"status": "ERROR", "error": str(exc)}, indent=2))
        return EXIT_ERROR
    finally:
        if session is not None:
            session.close()

    if args.command == "orphans":
        payload = {"count": len(report.orphans), "orphans": report.orphans}
    elif args.command == "missing":
        payload = {"count": len(report.missing), "missing": report.missing}
    elif args.command == "scan":
        payload = {"summary": report.summary(), "missing": report.missing, "orphans": report.orphans,
                   "hash_mismatches": report.hash_mismatches, "out_of_root": report.out_of_root}
    elif args.command == "verify":
        payload = {"summary": report.summary(), "hash_mismatches": report.hash_mismatches,
                   "missing": report.missing, "out_of_root": report.out_of_root}
    else:
        payload = report.as_dict()

    print(json.dumps(payload, indent=2, default=str))
    # ok covers integrity of referenced data; orphans are reported separately
    # but still make the command exit non-zero so schedulers notice them.
    clean = report.ok and not report.orphans and not report.unreadable
    return EXIT_OK if clean else EXIT_FINDINGS


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

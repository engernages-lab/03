"""Storage path safety primitives (V1.1-C.2.3.4.2).

Threat model
------------
* ``stored_path`` / ``artwork_path`` come from the database. They are normally
  written by the server (content-addressed), but a corrupted or tampered row must
  never turn into an arbitrary file read, write or delete.
* A caller may not escape ``storage_root`` by passing an absolute path, a Windows
  drive path, a UNC path, ``..`` segments, a NUL byte or a symlink.

Guarantees
----------
``safe_resolve_storage_path`` returns a **canonical** path that is inside the
canonical storage root, or raises ``StoragePathViolation``. It resolves
symlinks, so a link pointing outside the root is rejected rather than followed.

Known limits (documented, not hidden)
-------------------------------------
* TOCTOU: the check and the subsequent ``open``/``unlink`` are two syscalls. The
  window is narrowed by resolving to a canonical path and by refusing links, but
  it is not eliminated without ``openat``/``O_NOFOLLOW`` plumbing. Callers that
  need that guarantee must run on a volume the application alone can write.
* The storage root itself is trusted; if an attacker can replace the root with a
  symlink the boundary moves with it.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any, Iterable, Optional

from app.core.errors import AppError

WIN_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

MAX_FILENAME_LENGTH = 120
FALLBACK_FILENAME = "audio"

# Only these characters may survive filename sanitisation (plus CJK etc. which are
# letters/categories Lo, and normal spaces).
_UNSAFE_FILENAME_CHARS = re.compile(
    r'[\x00-\x1f\x7f<>:"/\\|?*\u202a-\u202e\u2066-\u2069]'
)

# Absolute paths that must never reach a client: POSIX roots, Windows drives, UNC.
_ABS_PATH_PATTERNS = (
    re.compile(r"[A-Za-z]:\\\\?[^\s'\"<>|]+"),          # C:\..., C:/...
    re.compile(r"\\\\[^\s'\"<>|]+"),                     # \\server\share
    re.compile(r"(?<![\w])/(?:data|app|home|tmp|var|usr|opt|srv|root|etc|proc|sys)(?:/[^\s'\"<>|]*)?"),
)


class StoragePathViolation(AppError):
    """A path escaped the storage root or was structurally invalid."""

    code = "STORAGE_PATH_INVALID"
    status_code = 400


def _fail(message: str = "storage path is invalid") -> None:
    # Never echo the offending value: it may contain a server path.
    raise StoragePathViolation(message, code="STORAGE_PATH_INVALID", status_code=400)


def canonical_root(storage_root: Path | str) -> Path:
    """Resolve and validate the storage root itself."""
    root = Path(storage_root)
    try:
        resolved = root.resolve(strict=True)
    except OSError as exc:  # missing or unreadable
        raise StoragePathViolation(
            "storage root is not available", code="STORAGE_UNAVAILABLE", status_code=500
        ) from exc
    if not resolved.is_dir():
        raise StoragePathViolation(
            "storage root is not a directory", code="STORAGE_UNAVAILABLE", status_code=500
        )
    return resolved


def _normalise_relative(relative_path: str | Path) -> str:
    if isinstance(relative_path, Path):
        raw = str(relative_path)
    elif isinstance(relative_path, str):
        raw = relative_path
    else:
        _fail()

    if not raw or raw.strip() in {"", ".", ".."}:
        _fail()
    if "\x00" in raw or any(ord(ch) < 32 for ch in raw):
        _fail()

    # Windows callers and legacy rows may use backslashes; treating them as
    # separators lets the traversal checks below see the real structure.
    unified = raw.replace("\\", "/")

    if unified.startswith("/"):
        _fail()  # POSIX absolute or UNC (after unification)
    if re.match(r"^[A-Za-z]:", unified):
        _fail()  # Windows drive path
    if unified.startswith("//"):
        _fail()  # UNC

    segments = [segment for segment in unified.split("/") if segment not in ("",)]
    if not segments:
        _fail()
    for segment in segments:
        if segment in (".", ".."):
            _fail()
        if segment.startswith("~"):
            _fail()
        if segment.endswith(" ") or segment.endswith("."):
            # Windows silently strips these, which can alias another file.
            _fail()
    return "/".join(segments)


def safe_resolve_storage_path(
    storage_root: Path | str,
    relative_path: str | Path,
    *,
    allow_missing: bool = False,
    must_be_file: bool = True,
) -> Path:
    """Return a canonical path inside ``storage_root`` or raise.

    ``allow_missing`` still validates the nearest existing parent, so a
    not-yet-created target cannot be used to step outside the root.
    """
    root = canonical_root(storage_root)
    relative = _normalise_relative(relative_path)

    candidate = root / relative
    try:
        resolved = candidate.resolve(strict=False)
    except OSError:
        _fail()

    try:
        resolved.relative_to(root)
    except ValueError:
        # covers symlink escapes and any residual traversal
        _fail()

    if resolved.exists():
        if must_be_file and not resolved.is_file():
            _fail()
        return resolved

    if not allow_missing:
        raise StoragePathViolation(
            "storage file is missing", code="STORAGE_FILE_MISSING", status_code=404
        )

    # Validate the closest existing ancestor as well: a dangling symlink or a
    # missing intermediate directory must not widen the boundary.
    ancestor = resolved.parent
    while True:
        if ancestor.exists():
            try:
                ancestor.resolve(strict=True).relative_to(root)
            except (ValueError, OSError):
                _fail()
            break
        if ancestor == root or ancestor.parent == ancestor:
            break
        ancestor = ancestor.parent
    return resolved


def ensure_within(storage_root: Path | str, candidate: Path) -> Path:
    """Re-validate an already-built path (used before destructive operations)."""
    root = canonical_root(storage_root)
    try:
        resolved = Path(candidate).resolve(strict=False)
    except OSError:
        _fail()
    try:
        resolved.relative_to(root)
    except ValueError:
        _fail()
    return resolved


# --------------------------------------------------------------------------- #
# upload filename
# --------------------------------------------------------------------------- #


def sanitize_upload_filename(filename: Optional[str], *, fallback: str = FALLBACK_FILENAME) -> str:
    """Return a display-safe filename: no directories, no control chars, bounded.

    The physical storage path is always content-addressed, so this value is only
    metadata. It still must not carry separators or be usable to build a path.
    """
    if not filename or not isinstance(filename, str):
        return fallback

    # Normalise Unicode so lookalike separators collapse before the regex runs.
    text = unicodedata.normalize("NFKC", filename)
    text = text.replace("\\", "/")
    # keep only the last component, whichever separator was used
    text = text.rsplit("/", 1)[-1]
    text = _UNSAFE_FILENAME_CHARS.sub("", text)
    text = text.strip().strip(".")
    text = re.sub(r"\s+", " ", text)

    if not text or text in {".", ".."}:
        return fallback

    stem, dot, suffix = text.rpartition(".")
    if not dot:
        stem, suffix = text, ""
    stem = stem.strip().strip(".") or fallback
    suffix = suffix.strip().strip(".").lower()

    # Windows reserved device names are unusable even with an extension
    if stem.upper() in WIN_RESERVED:
        stem = f"{fallback}-{stem.lower()}"

    if len(stem) > MAX_FILENAME_LENGTH:
        stem = stem[:MAX_FILENAME_LENGTH].rstrip()

    return f"{stem}.{suffix}" if suffix else stem


def sanitize_extension(filename: str) -> str:
    """Extract a lower-cased extension, rejecting anything odd."""
    suffix = Path(sanitize_upload_filename(filename)).suffix.lower()
    if not re.fullmatch(r"\.[a-z0-9]{1,8}", suffix):
        return ""
    return suffix


# --------------------------------------------------------------------------- #
# error scrubbing
# --------------------------------------------------------------------------- #


def scrub_paths(value: Any) -> Any:
    """Strip absolute filesystem paths from a value destined for a client."""
    if isinstance(value, str):
        text = value
        for pattern in _ABS_PATH_PATTERNS:
            text = pattern.sub("<redacted>", text)
        return text
    if isinstance(value, dict):
        return {key: scrub_paths(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        scrubbed = [scrub_paths(item) for item in value]
        return type(value)(scrubbed) if isinstance(value, tuple) else scrubbed
    return value


def is_within(root: Path | str, candidate: Path | str) -> bool:
    """Non-raising containment check used by tooling and tests."""
    try:
        canonical_root(root)
        ensure_within(root, Path(candidate))
    except (StoragePathViolation, OSError):
        return False
    return True


def candidate_exists(path: Path) -> bool:
    try:
        return path.exists()
    except OSError:
        return False


def iter_storage_files(root: Path) -> Iterable[Path]:
    """Yield regular files under a storage root, never following links out."""
    base = canonical_root(root)
    for path in base.rglob("*"):
        if path.is_file() and not path.is_symlink():
            yield path

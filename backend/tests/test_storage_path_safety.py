"""Storage boundary unit tests (V1.1-C.2.3.4.2).

Covers the six mandated traversal payloads, absolute/Windows/UNC forms, malformed
input, missing-target handling, symlink and junction escapes, and path scrubbing.
Every test works inside tmp_path only.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from app.core.paths import (
    StoragePathViolation,
    canonical_root,
    ensure_within,
    is_within,
    safe_resolve_storage_path,
    sanitize_upload_filename,
    scrub_paths,
)


@pytest.fixture()
def store(tmp_path: Path) -> Path:
    root = tmp_path / "storage"
    (root / "audio" / "ab").mkdir(parents=True)
    (root / "audio" / "ab" / ("a" * 64 + ".wav")).write_bytes(b"RIFF0000WAVE")
    (root / "artwork").mkdir()
    (root / "artwork" / ("b" * 64 + ".jpg")).write_bytes(b"\xff\xd8\xff")
    return root


# ---------------------------------------------------------------- P01..P06


@pytest.mark.parametrize(
    "payload",
    [
        "../../etc/passwd",            # P01
        "../../../tmp/secret.txt",     # P02
        "audio/../../outside.txt",     # P03
        "/etc/passwd",                 # P04
        r"C:\Windows\system.ini",      # P05
        r"\\server\share\secret.txt",  # P06
    ],
)
def test_traversal_payloads_are_rejected(store: Path, payload: str) -> None:
    with pytest.raises(StoragePathViolation) as error:
        safe_resolve_storage_path(store, payload)
    assert error.value.status_code == 400
    assert error.value.code == "STORAGE_PATH_INVALID"


@pytest.mark.parametrize(
    "payload",
    [
        "..\\..\\escape.txt",
        "audio\\..\\..\\escape.txt",
        "audio//..//..//escape.txt",
        "./audio/../audio/../../escape.txt",
        "audio/./../../escape.txt",
        "..",
        ".",
        "",
        "   ",
        "~/secret.txt",
        "audio/ab/x.wav\x00.png",
        "audio/ab/" + "c" * 300 + ".wav ",
        "audio/ab/name.",
    ],
)
def test_other_malformed_paths_are_rejected(store: Path, payload: str) -> None:
    with pytest.raises(StoragePathViolation):
        safe_resolve_storage_path(store, payload)


@pytest.mark.parametrize("payload", [None, 42, b"audio/x.wav", ["audio/x.wav"]])
def test_non_string_input_is_rejected(store: Path, payload) -> None:
    with pytest.raises(StoragePathViolation):
        safe_resolve_storage_path(store, payload)  # type: ignore[arg-type]


def test_encoded_traversal_is_not_decoded_by_the_resolver(store: Path) -> None:
    # %2e%2e%2f is a literal filename here; decoding happens (if at all) upstream,
    # where the decoded form is then rejected by this same check.
    resolved = safe_resolve_storage_path(store, "audio/ab/%2e%2e%2fsecret.wav", allow_missing=True)
    assert resolved.parent == (store / "audio" / "ab").resolve()


# ---------------------------------------------------------------- absolutes


def test_absolute_path_cannot_override_the_root(store: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside.wav"
    outside.write_bytes(b"secret")
    with pytest.raises(StoragePathViolation):
        safe_resolve_storage_path(store, str(outside))


def test_windows_drive_and_unc_are_rejected(store: Path) -> None:
    for payload in ("C:/Windows/system.ini", "c:\\temp\\x.wav", "\\\\host\\share\\x", "//host/share/x"):
        with pytest.raises(StoragePathViolation):
            safe_resolve_storage_path(store, payload)


# ---------------------------------------------------------------- valid paths


def test_valid_nested_path_resolves_inside_root(store: Path) -> None:
    relative = f"audio/ab/{'a' * 64}.wav"
    resolved = safe_resolve_storage_path(store, relative)
    assert resolved.is_file()
    assert resolved.parent == (store / "audio" / "ab").resolve()


def test_backslash_separator_is_normalised(store: Path) -> None:
    resolved = safe_resolve_storage_path(store, "audio\\ab\\" + "a" * 64 + ".wav")
    assert resolved.is_file()


def test_missing_file_without_flag_raises_missing(store: Path) -> None:
    with pytest.raises(StoragePathViolation) as error:
        safe_resolve_storage_path(store, "audio/ab/deadbeef.wav")
    assert error.value.code == "STORAGE_FILE_MISSING"
    assert error.value.status_code == 404


def test_allow_missing_still_validates_the_parent(store: Path) -> None:
    resolved = safe_resolve_storage_path(store, "audio/ab/new-file.wav", allow_missing=True)
    assert resolved.parent == (store / "audio" / "ab").resolve()
    with pytest.raises(StoragePathViolation):
        safe_resolve_storage_path(store, "audio/../../escape.wav", allow_missing=True)


def test_directory_is_not_accepted_as_a_file(store: Path) -> None:
    with pytest.raises(StoragePathViolation):
        safe_resolve_storage_path(store, "audio/ab")


# ---------------------------------------------------------------- root itself


def test_missing_root_is_a_storage_error(tmp_path: Path) -> None:
    with pytest.raises(StoragePathViolation) as error:
        canonical_root(tmp_path / "nope")
    assert error.value.code == "STORAGE_UNAVAILABLE"
    assert error.value.status_code == 500


def test_root_that_is_a_file_is_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "storage-file"
    bad.write_text("x", encoding="utf-8")
    with pytest.raises(StoragePathViolation):
        canonical_root(bad)


# ---------------------------------------------------------------- links


def _make_junction(link: Path, target: Path) -> bool:
    if os.name != "nt":  # pragma: no cover - windows-only helper
        return False
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True, text=True,
    )
    return result.returncode == 0


def test_symlinked_directory_cannot_escape(store: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside-dir"
    outside.mkdir()
    (outside / "secret.wav").write_bytes(b"RIFFsecret")
    link = store / "audio" / "link-dir"
    try:
        os.symlink(outside, link, target_is_directory=True)
    except (OSError, NotImplementedError):
        junction = _make_junction(link, outside)
        if not junction:
            pytest.skip("symlinks and junctions are unavailable in this environment")
    with pytest.raises(StoragePathViolation):
        safe_resolve_storage_path(store, "audio/link-dir/secret.wav", allow_missing=True)


def test_symlinked_file_cannot_escape(store: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside.wav"
    outside.write_bytes(b"RIFFsecret")
    link = store / "audio" / "linked.wav"
    try:
        os.symlink(outside, link)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are unavailable in this environment")
    with pytest.raises(StoragePathViolation):
        safe_resolve_storage_path(store, "audio/linked.wav")


def test_broken_link_is_not_treated_as_missing_target(store: Path, tmp_path: Path) -> None:
    dangling = store / "audio" / "dangling.wav"
    try:
        os.symlink(tmp_path / "does-not-exist.wav", dangling)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are unavailable in this environment")
    with pytest.raises(StoragePathViolation):
        safe_resolve_storage_path(store, "audio/dangling.wav", allow_missing=True)


# ---------------------------------------------------------------- helpers


def test_ensure_within_rejects_outside_paths(store: Path, tmp_path: Path) -> None:
    with pytest.raises(StoragePathViolation):
        ensure_within(store, tmp_path / "outside.wav")
    assert ensure_within(store, store / "audio").is_dir()
    assert is_within(store, store / "audio" / "ab") is True
    assert is_within(store, tmp_path / "outside.wav") is False


def test_scrub_paths_removes_absolute_locations() -> None:
    cases = [
        r"[Errno 13] Permission denied: 'D:\AI\storage'",
        "cannot open /data/storage/audio/ab/x.wav",
        r"\\\\server\\share\\secret.txt",
        "/tmp/tmp123456.wav",
    ]
    for text in cases:
        assert "<redacted>" in scrub_paths(text)
        assert "storage" not in scrub_paths(text) or "redacted" in scrub_paths(text)


def test_scrub_paths_walks_nested_structures() -> None:
    payload = {"reason": "/data/storage/x.wav", "items": [r"D:\app\x", 5, None]}
    cleaned = scrub_paths(payload)
    assert "<redacted>" in cleaned["reason"]
    assert "<redacted>" in cleaned["items"][0]
    assert cleaned["items"][1] == 5 and cleaned["items"][2] is None


def test_sanitize_is_idempotent() -> None:
    once = sanitize_upload_filename("../../My Song.wav")
    assert sanitize_upload_filename(once) == once

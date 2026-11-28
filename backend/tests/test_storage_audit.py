"""Storage audit tests (V1.1-C.2.3.3) — all against synthetic stores."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401 - registers mappers on Base.metadata
from app.core.db import Base
from app.models.audio import AudioAssetRecord
from app.ops import storage_audit as audit

SHA_A = "a" * 64
SHA_B = "b" * 64


def make_session(tmp_path: Path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'db' / 'audit.db').as_posix()}", future=True)
    (tmp_path / "db").mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def add_asset(session, *, asset_id: str, stored_path: str, artwork_path=None, sha: str = SHA_A) -> None:
    session.add(AudioAssetRecord(
        id=asset_id,
        filename=f"{asset_id}.wav",
        stored_path=stored_path,
        mime="audio/wav",
        ext=".wav",
        size_bytes=10,
        checksum_sha256=sha,
        artwork_path=artwork_path,
    ))
    session.commit()


def write_file(root: Path, relative: str, payload: bytes = b"RIFF....WAVEfmt ") -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def test_clean_store_reports_ok(tmp_path):
    storage = tmp_path / "storage"
    relative = f"audio/{SHA_A[:2]}/{SHA_A}.wav"
    payload = b"RIFF0000WAVEfmt " + b"\x00" * 32
    write_file(storage, relative, payload)
    # content-addressed name must match the payload hash; rebuild the name
    import hashlib

    digest = hashlib.sha256(payload).hexdigest()
    relative = f"audio/{digest[:2]}/{digest}.wav"
    (storage / f"audio/{SHA_A[:2]}/{SHA_A}.wav").unlink()
    write_file(storage, relative, payload)

    session = make_session(tmp_path)
    add_asset(session, asset_id="a1", stored_path=relative, sha=digest)

    report = audit.audit_storage(storage, session=session)
    assert report.ok, report.as_dict()
    assert report.summary()["file_count"] == 1
    assert report.summary()["referenced_files"] == 1
    assert report.orphans == []


def test_missing_file_detected(tmp_path):
    storage = tmp_path / "storage"
    storage.mkdir()
    session = make_session(tmp_path)
    add_asset(session, asset_id="a1", stored_path=f"audio/{SHA_A[:2]}/{SHA_A}.wav")

    report = audit.audit_storage(storage, session=session)
    assert not report.ok
    assert len(report.missing) == 1
    assert report.missing[0]["column"] == "stored_path"


def test_orphan_file_detected(tmp_path):
    storage = tmp_path / "storage"
    write_file(storage, f"audio/cc/{'c' * 64}.wav")
    session = make_session(tmp_path)

    report = audit.audit_storage(storage, session=session)
    assert report.orphans == [f"audio/cc/{'c' * 64}.wav"]
    assert report.summary()["orphan_files"] == 1


def test_hash_mismatch_detected(tmp_path):
    storage = tmp_path / "storage"
    relative = f"audio/{SHA_A[:2]}/{SHA_A}.wav"
    write_file(storage, relative, b"RIFF0000WAVEfmt " + b"\x11" * 32)  # content does not hash to SHA_A
    session = make_session(tmp_path)
    add_asset(session, asset_id="a1", stored_path=relative)

    report = audit.audit_storage(storage, session=session)
    assert not report.ok
    assert len(report.hash_mismatches) == 1
    assert "content hash" in report.hash_mismatches[0]["problem"]


def test_path_escape_detected(tmp_path):
    storage = tmp_path / "storage"
    storage.mkdir()
    outside = tmp_path / "outside.wav"
    outside.write_bytes(b"secret")
    session = make_session(tmp_path)
    add_asset(session, asset_id="a1", stored_path="../../outside.wav")

    report = audit.audit_storage(storage, session=session)
    assert report.out_of_root, report.as_dict()
    assert not report.ok


def test_artwork_url_maps_to_file_and_missing_is_reported(tmp_path):
    storage = tmp_path / "storage"
    write_file(storage, f"audio/{SHA_A[:2]}/{SHA_A}.wav", b"RIFF0000WAVEfmt ")
    session = make_session(tmp_path)
    add_asset(session, asset_id="a1", stored_path=f"audio/{SHA_A[:2]}/{SHA_A}.wav",
              artwork_path=f"/static/artwork/{SHA_B}.jpg")

    report = audit.audit_storage(storage, session=session, verify_hashes=False)
    assert len(report.artwork_missing) == 1
    assert report.artwork_missing[0]["relative_path"] == f"artwork/{SHA_B}.jpg"


def test_existing_artwork_counts_as_referenced(tmp_path):
    storage = tmp_path / "storage"
    write_file(storage, f"audio/{SHA_A[:2]}/{SHA_A}.wav", b"RIFF0000WAVEfmt ")
    write_file(storage, f"artwork/{SHA_B}.jpg", b"\xff\xd8\xff\xe0jpeg")
    session = make_session(tmp_path)
    add_asset(session, asset_id="a1", stored_path=f"audio/{SHA_A[:2]}/{SHA_A}.wav",
              artwork_path=f"/static/artwork/{SHA_B}.jpg")

    report = audit.audit_storage(storage, session=session, verify_hashes=False)
    assert report.artwork_missing == []
    assert report.orphans == []


def test_duplicate_references_are_not_orphans(tmp_path):
    storage = tmp_path / "storage"
    relative = f"audio/{SHA_A[:2]}/{SHA_A}.wav"
    write_file(storage, relative, b"RIFF0000WAVEfmt ")
    session = make_session(tmp_path)
    add_asset(session, asset_id="a1", stored_path=relative)
    add_asset(session, asset_id="a2", stored_path=relative)

    report = audit.audit_storage(storage, session=session, verify_hashes=False)
    assert report.orphans == []
    assert len(report.duplicates) == 1
    assert report.duplicates[0]["reference_count"] == 2


def test_empty_storage_with_no_references_is_ok(tmp_path):
    storage = tmp_path / "storage"
    storage.mkdir()
    session = make_session(tmp_path)
    report = audit.audit_storage(storage, session=session)
    assert report.ok
    assert report.summary()["file_count"] == 0


def test_transient_directory_is_not_an_orphan(tmp_path):
    storage = tmp_path / "storage"
    write_file(storage, "uploads/pocket-tmp-file.wav")
    session = make_session(tmp_path)
    report = audit.audit_storage(storage, session=session)
    assert report.orphans == []
    assert report.summary()["transient_files"] == 1


def test_symlink_escape_is_rejected(tmp_path):
    storage = tmp_path / "storage"
    storage.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    link = storage / "audio" / "escape.wav"
    link.parent.mkdir(parents=True)
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):  # pragma: no cover - needs privileges on Windows
        pytest.skip("symlinks are not available in this environment")
    assert audit.is_within(storage, link) is False


def test_cli_scan_returns_findings_exit_code(tmp_path, capsys):
    storage = tmp_path / "storage"
    write_file(storage, f"audio/cc/{'c' * 64}.wav")
    code = audit.main(["scan", "--storage", str(storage), "--database", str(tmp_path / "db" / "audit.db")])
    assert code == audit.EXIT_FINDINGS
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["orphan_files"] == 1


def test_content_address_helper():
    assert audit.expected_hash_for(f"audio/ab/{'a' * 64}.wav") == "a" * 64
    assert audit.expected_hash_for("audio/ab/not-a-hash.wav") is None
    assert audit.artwork_relative_path("/static/artwork/x.jpg") == "artwork/x.jpg"
    assert audit.artwork_relative_path("https://example.com/x.jpg") is None

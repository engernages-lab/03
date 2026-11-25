"""Audio asset ingestion: validation, hashing, storage, metadata, artwork."""

from __future__ import annotations

import base64
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import NotFoundError, PayloadTooLargeError, ValidationAppError
from app.core.logging import get_logger
from app.models.audio import AudioAssetRecord
from app.schemas.music_document import new_id
from app.services.audio.probe import (
    MIME_TYPES,
    analyse,
    decode_mono,
    normalize_peak,
    probe_audio,
    validate_extension,
    verify_decodable,
    waveform_buckets,
)

logger = get_logger("pocketscore.audio.assets")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def extract_tags(path: Path) -> Dict[str, Any]:
    """Read tags and embedded artwork with mutagen (best effort)."""
    tags: Dict[str, Any] = {
        "title": None, "artist": None, "album": None, "artwork": None, "artwork_mime": None,
    }
    try:
        import mutagen
    except ImportError:  # pragma: no cover
        return tags

    try:
        audio = mutagen.File(str(path), easy=True)
    except Exception:
        return tags
    if audio is None:
        return tags

    def _first(key: str) -> Optional[str]:
        value = audio.tags.get(key) if audio.tags else None
        if isinstance(value, list) and value:
            return str(value[0])[:255]
        return str(value)[:255] if value else None

    try:
        tags["title"] = _first("title")
        tags["artist"] = _first("artist")
        tags["album"] = _first("album")
    except Exception:  # pragma: no cover - malformed tags
        pass

    artwork = _extract_artwork(path)
    if artwork is not None:
        blob, mime = artwork
        tags["artwork"] = blob
        tags["artwork_mime"] = mime
    return tags


def _extract_artwork(path: Path) -> Optional[Tuple[bytes, str]]:
    try:
        import mutagen
        from mutagen.flac import FLAC
        from mutagen.id3 import ID3
        from mutagen.mp4 import MP4
        from mutagen.oggvorbis import OggVorbis

        _ = mutagen  # presence check only
    except ImportError:  # pragma: no cover
        return None

    suffix = path.suffix.lower()
    try:
        if suffix == ".mp3":
            tags = ID3(str(path))
            for frame in tags.values():
                if frame.FrameID == "APIC":
                    return bytes(frame.data), frame.mime or "image/jpeg"
        elif suffix == ".flac":
            flac = FLAC(str(path))
            if flac.pictures:
                picture = flac.pictures[0]
                return bytes(picture.data), picture.mime or "image/jpeg"
        elif suffix in (".m4a", ".mp4"):
            mp4 = MP4(str(path))
            covers = mp4.tags.get("covr") if mp4.tags else None
            if covers:
                return bytes(covers[0]), "image/jpeg"
        elif suffix == ".ogg":
            ogg = OggVorbis(str(path))
            raw = ogg.get("metadata_block_picture")
            if raw:
                from mutagen.flac import Picture

                picture = Picture(base64.b64decode(raw[0]))
                return bytes(picture.data), picture.mime or "image/jpeg"
    except Exception:  # pragma: no cover - best effort
        return None
    return None


def _store_artwork(sha: str, blob: bytes, mime: str) -> str:
    settings = get_settings()
    ext = ".jpg" if "jpeg" in (mime or "") or "jpg" in (mime or "") else ".png"
    target = settings.artwork_path / f"{sha}{ext}"
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        target.write_bytes(blob)
    return f"/static/artwork/{target.name}"


def ingest_audio(
    session: Session,
    data: bytes,
    filename: str,
    *,
    source_id: Optional[str] = None,
    title: Optional[str] = None,
    artist: Optional[str] = None,
) -> Tuple[AudioAssetRecord, bool]:
    """Store an uploaded audio file. Returns ``(asset, created)``."""
    settings = get_settings()
    settings.ensure_directories()

    ext = validate_extension(filename)
    if len(data) == 0:
        raise ValidationAppError("uploaded file is empty", code="AUDIO_PROBE_FAILED")
    if len(data) > settings.max_upload_bytes:
        raise PayloadTooLargeError(
            f"file exceeds the {settings.max_upload_mb}MB limit",
            details={"limit_mb": settings.max_upload_mb, "size_mb": round(len(data) / 1048576, 2)},
        )

    checksum = _sha256(data)
    existing = session.execute(
        select(AudioAssetRecord).where(AudioAssetRecord.checksum_sha256 == checksum)
    ).scalars().first()
    if existing is not None:
        logger.info("audio asset deduplicated by checksum (%s)", checksum[:12])
        return existing, False

    target_dir = settings.audio_path / checksum[:2]
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{checksum}{ext}"
    target.write_bytes(data)

    probe = probe_audio(target)
    verify_decodable(target, probe.duration)
    limit_seconds = get_settings().max_audio_duration_seconds
    if limit_seconds and probe.duration > limit_seconds:
        # Remove the file we just wrote: the upload is rejected, not kept.
        target.unlink(missing_ok=True)
        raise ValidationAppError(
            f"audio is longer than the {limit_seconds}s limit",
            code="AUDIO_TOO_LONG",
            status_code=422,
            details={"duration": round(probe.duration, 2), "limit_seconds": limit_seconds},
        )
    tags = extract_tags(target)

    artwork_path = None
    if tags.get("artwork"):
        artwork_path = _store_artwork(checksum, tags["artwork"], tags.get("artwork_mime") or "image/jpeg")

    record = AudioAssetRecord(
        id=new_id(),
        filename=(filename or target.name)[:255],
        stored_path=str(target.relative_to(settings.storage_path)),
        mime=MIME_TYPES.get(ext, "application/octet-stream"),
        ext=ext,
        size_bytes=len(data),
        duration=round(probe.duration, 4),
        sample_rate=probe.sample_rate,
        channels=probe.channels,
        bitrate=probe.bitrate,
        codec=probe.codec,
        checksum_sha256=checksum,
        artwork_path=artwork_path,
        title=(title or tags.get("title") or Path(filename).stem)[:255],
        artist=(artist or tags.get("artist") or "未知艺人")[:255],
        source_id=source_id,
        analysis_json=json.dumps(probe.as_dict(), ensure_ascii=False),
    )
    session.add(record)
    session.commit()
    return record, True


def absolute_path(record: AudioAssetRecord) -> Path:
    return get_settings().storage_path / record.stored_path


def get_asset(session: Session, asset_id: str) -> AudioAssetRecord:
    record = session.get(AudioAssetRecord, asset_id)
    if record is None:
        raise NotFoundError(
            f"audio asset {asset_id!r} not found", code="AUDIO_ASSET_NOT_FOUND"
        )
    return record


def list_assets(
    session: Session, *, limit: int = 50, offset: int = 0, query: Optional[str] = None
) -> Tuple[List[AudioAssetRecord], int]:
    from sqlalchemy import func

    stmt = select(AudioAssetRecord)
    count_stmt = select(func.count()).select_from(AudioAssetRecord)
    if query:
        like = f"%{query.strip()}%"
        condition = AudioAssetRecord.filename.ilike(like) | AudioAssetRecord.title.ilike(like)
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)
    stmt = stmt.order_by(AudioAssetRecord.created_at.desc()).limit(limit).offset(offset)
    rows = list(session.execute(stmt).scalars())
    total = int(session.execute(count_stmt).scalar_one())
    return rows, total


def delete_asset(session: Session, asset_id: str) -> None:
    record = get_asset(session, asset_id)
    path = absolute_path(record)
    session.delete(record)
    session.commit()
    try:
        if path.exists():
            path.unlink()
    except OSError:  # pragma: no cover - file may be locked on Windows
        logger.warning("could not remove audio file %s", path)


def asset_waveform(record: AudioAssetRecord, buckets: int = 800) -> List[float]:
    audio, _sr = decode_mono(absolute_path(record))
    return waveform_buckets(audio, buckets)


def asset_analysis(record: AudioAssetRecord, *, normalise: bool = True) -> Dict[str, Any]:
    audio, sr = decode_mono(absolute_path(record))
    if normalise:
        audio = normalize_peak(audio)
    return analyse(audio, sr)


def regenerate_thumbnail(record: AudioAssetRecord) -> Optional[str]:  # pragma: no cover - utility
    path = absolute_path(record)
    tags = extract_tags(path)
    if not tags.get("artwork"):
        return None
    return _store_artwork(record.checksum_sha256, tags["artwork"], tags.get("artwork_mime") or "image/jpeg")


def copy_into_library(record: AudioAssetRecord, target: Path) -> Path:
    """Copy the stored file elsewhere (used by local library import)."""
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(absolute_path(record), target)
    return target

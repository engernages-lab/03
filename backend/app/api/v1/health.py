"""Health, readiness and capability reporting.

The capability probe reports what the *actual* runtime can do (ffmpeg binary,
librosa, MIDI libraries, database).  The frontend uses it to disable features
that cannot run instead of pretending they work.
"""

from __future__ import annotations

import importlib
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import __version__
from app.core.config import get_settings
from app.core.db import get_db

router = APIRouter()

_capability_cache: Optional[Dict[str, Any]] = None


def _module_version(name: str) -> Optional[str]:
    try:
        module = importlib.import_module(name)
    except Exception:
        return None
    return getattr(module, "__version__", "installed")


def resolve_ffmpeg() -> Optional[str]:
    """Locate an ffmpeg executable.

    Preference order: ``POCKETSCORE_FFMPEG_PATH`` (not exposed as a setting to
    keep the surface small) -> system ``ffmpeg`` -> the binary bundled with
    ``imageio-ffmpeg``.
    """
    import os

    explicit = os.environ.get("POCKETSCORE_FFMPEG_PATH")
    if explicit and shutil.which(explicit):
        return shutil.which(explicit)
    system = shutil.which("ffmpeg")
    if system:
        return system
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def probe_capabilities() -> Dict[str, Any]:
    global _capability_cache
    if _capability_cache is not None:
        return _capability_cache

    ffmpeg = resolve_ffmpeg()
    ffmpeg_version = None
    if ffmpeg:
        try:
            out = subprocess.run(
                [ffmpeg, "-version"], capture_output=True, text=True, timeout=20, check=False
            )
            ffmpeg_version = (out.stdout or "").splitlines()[0] if out.stdout else None
        except Exception:  # pragma: no cover - environment dependent
            ffmpeg_version = None

    caps = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "ffmpeg": {"available": bool(ffmpeg), "path": ffmpeg, "version": ffmpeg_version},
        "librosa": {"available": _module_version("librosa") is not None,
                    "version": _module_version("librosa")},
        "soundfile": {"available": _module_version("soundfile") is not None,
                      "version": _module_version("soundfile")},
        "mido": {"available": _module_version("mido") is not None,
                 "version": _module_version("mido")},
        "pretty_midi": {"available": _module_version("pretty_midi") is not None,
                        "version": _module_version("pretty_midi")},
        "music21": {"available": _module_version("music21") is not None,
                    "version": _module_version("music21")},
        "mutagen": {"available": _module_version("mutagen") is not None,
                    "version": _module_version("mutagen")},
    }
    _capability_cache = caps
    return caps


def reset_capability_cache() -> None:
    global _capability_cache
    _capability_cache = None


@router.get("")
def health() -> Dict[str, Any]:
    settings = get_settings()
    caps = probe_capabilities()
    return {
        "status": "ok",
        "name": settings.app_name,
        "version": __version__,
        "stage": settings.release_stage,
        "environment": settings.environment,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "capabilities": caps,
    }


@router.get("/ready")
def readiness(db: Session = Depends(get_db)) -> Dict[str, Any]:
    return readiness_payload(db)


def readiness_payload(db: Optional[Session] = None) -> Dict[str, Any]:
    """Readiness for containers: DB, storage, FFmpeg, MIDI and the AI model.

    Never loads the model here - it reports the state the manager already has,
    so a healthcheck cannot accidentally trigger a 3.7 s JIT warm-up.
    """
    from app.services.audio.inference_limiter import get_limiter
    from app.services.audio.model_manager import model_manager

    settings = get_settings()
    checks: Dict[str, Any] = {}

    if db is not None:
        try:
            db.execute(text("SELECT 1"))
            checks["database"] = {"ok": True}
        except Exception as exc:  # pragma: no cover - defensive
            checks["database"] = {"ok": False, "error": str(exc)}

    storage_ok, storage_error = _storage_writable(settings.storage_path)
    checks["storage"] = {"ok": storage_ok, **({"error": storage_error} if storage_error else {})}

    caps = probe_capabilities()
    checks["ffmpeg"] = {"ok": caps["ffmpeg"]["available"], "optional": False}
    checks["librosa"] = {"ok": caps["librosa"]["available"], "optional": True}
    checks["midi"] = {
        "ok": caps["mido"]["available"] and caps["pretty_midi"]["available"],
        "optional": False,
    }

    model_state = model_manager.status()
    model_ok = model_state["status"] == "ready"
    checks["model"] = {
        "ok": model_ok,
        "status": model_state["status"],
        "version": model_state["model_version"],
        "load_seconds": model_state["load_seconds"],
        "warmup_seconds": model_state["warmup_seconds"],
        # The model is required for transcription but the API itself is usable
        # without it (MIDI import, editing, export), so it is not a hard gate
        # unless preloading was explicitly requested.
        "optional": not get_settings().model_preload,
    }
    checks["inference"] = {"ok": True, **get_limiter().stats()}

    # Deployment probes must be able to tell "protected as intended" from
    # "accidentally open" - without ever exposing the credential itself.
    try:
        from app.core.access_gate import build_gate

        checks["access_gate"] = {"ok": True, **build_gate(get_settings()).describe()}
    except Exception as exc:  # pragma: no cover - defensive
        checks["access_gate"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    required_ok = all(c["ok"] for c in checks.values() if not c.get("optional", False))
    return {
        "ready": bool(required_ok),
        "status": "ready" if required_ok else "degraded",
        "checks": checks,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _storage_writable(path) -> tuple[bool, Optional[str]]:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe_file = path / ".write-probe"
        probe_file.write_bytes(b"ok")
        probe_file.unlink(missing_ok=True)
        return True, None
    except Exception as exc:  # pragma: no cover - depends on filesystem
        return False, f"{type(exc).__name__}: {exc}"


@router.get("/capabilities")
def capabilities() -> Dict[str, Any]:
    return probe_capabilities()

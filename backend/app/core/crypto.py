"""Token encryption at rest (Fernet) with a machine-local fallback key.

Third-party OAuth tokens and server passwords must never be stored in clear
text and must never be returned by the API.
"""

from __future__ import annotations

import base64
import contextlib
import os
from pathlib import Path
from typing import Optional

from app.core.config import get_settings
from app.core.errors import DependencyMissingError
from app.core.logging import get_logger

logger = get_logger("pocketscore.crypto")

_fernet = None


def _load_fernet():
    global _fernet
    if _fernet is not None:
        return _fernet
    try:
        from cryptography.fernet import Fernet
    except ImportError as exc:  # pragma: no cover - dependency is installed
        raise DependencyMissingError(
            "token encryption requires the 'cryptography' package"
        ) from exc

    settings = get_settings()
    key = settings.token_encryption_key
    if not key:
        key = _machine_key(settings.storage_path)
    _fernet = Fernet(key.encode() if isinstance(key, str) else key)
    return _fernet


def _machine_key(storage_path: Path) -> str:
    """Create/read a local key file so development does not need configuration.

    Production deployments must set ``POCKETSCORE_TOKEN_ENCRYPTION_KEY``.
    """
    storage_path.mkdir(parents=True, exist_ok=True)
    key_file = storage_path / ".token_key"
    if key_file.exists():
        return key_file.read_text(encoding="utf-8").strip()
    from cryptography.fernet import Fernet

    key = Fernet.generate_key().decode()
    key_file.write_text(key, encoding="utf-8")
    with contextlib.suppress(OSError):  # chmod is a no-op on Windows
        os.chmod(key_file, 0o600)
    logger.warning("generated a local token encryption key at %s", key_file)
    return key


def encrypt(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    return _load_fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    try:
        return _load_fernet().decrypt(value.encode("ascii")).decode("utf-8")
    except Exception as exc:  # invalid key / corrupt payload
        logger.error("could not decrypt stored token: %s", exc)
        return None


def mask(value: Optional[str], keep: int = 4) -> str:
    """Display-safe representation of a secret."""
    if not value:
        return ""
    if len(value) <= keep * 2:
        return "*" * len(value)
    return f"{value[:keep]}…{value[-keep:]}"


def reset_cache() -> None:
    global _fernet
    _fernet = None


def encode_state(value: str) -> str:
    """Opaque OAuth state value (signed with the local key)."""
    return base64.urlsafe_b64encode(_load_fernet().encrypt(value.encode()).decode().encode()).decode()

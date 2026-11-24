"""Centralised, environment-driven configuration.

All settings are read from environment variables (optionally via a local
``.env`` file) with the ``POCKETSCORE_`` prefix.  Nothing secret is ever
hard-coded and ``.env`` is git-ignored.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    """Runtime configuration for the PocketScore AI API."""

    model_config = SettingsConfigDict(
        env_prefix="POCKETSCORE_",
        env_file=(str(BACKEND_DIR / ".env"), str(PROJECT_ROOT / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # -- application -------------------------------------------------------
    app_name: str = "PocketScore AI"
    app_version: str = "1.0.0a1"
    release_stage: str = "V1.0-A"
    environment: str = "development"  # development | test | production
    debug: bool = True
    api_v1_prefix: str = "/api/v1"

    # -- server ------------------------------------------------------------
    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: List[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:4173",
            "http://127.0.0.1:4173",
        ]
    )

    # -- persistence -------------------------------------------------------
    database_url: str = "sqlite:///./data/pocketscore.db"
    storage_dir: str = "./data/storage"
    migration_enabled: bool = True

    # -- uploads -----------------------------------------------------------
    max_upload_mb: int = 200
    allowed_audio_extensions: List[str] = Field(
        default_factory=lambda: [".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".opus"]
    )
    allowed_midi_extensions: List[str] = Field(
        default_factory=lambda: [".mid", ".midi"]
    )

    # -- security ----------------------------------------------------------
    # Fernet key used to encrypt third-party tokens at rest.  When unset a
    # key is derived from a machine-local file so development keeps working.
    token_encryption_key: Optional[str] = None
    session_secret: str = "change-me-in-production"
    allow_private_network_sources: bool = True  # Navidrome/LAN servers
    ffprobe_timeout_seconds: int = 60

    # -- logging -----------------------------------------------------------
    log_level: str = "INFO"
    log_json: bool = False

    # -- static frontend (single-service deployment) -----------------------
    # When frontend/dist exists it is served from "/" so one container can host
    # both the API and the SPA. Disable to host the frontend separately.
    serve_frontend: bool = True

    # -- third party credentials (all optional; integrations degrade
    #    gracefully when absent) -------------------------------------------
    navidrome_default_url: Optional[str] = None
    apple_music_team_id: Optional[str] = None
    apple_music_key_id: Optional[str] = None
    apple_music_private_key_path: Optional[str] = None
    apple_music_storefront: str = "us"
    spotify_client_id: Optional[str] = None
    spotify_client_secret: Optional[str] = None
    spotify_redirect_uri: Optional[str] = None

    # -- derived paths -----------------------------------------------------
    @property
    def storage_path(self) -> Path:
        return self._resolve(self.storage_dir)

    @property
    def audio_path(self) -> Path:
        return self.storage_path / "audio"

    @property
    def artwork_path(self) -> Path:
        return self.storage_path / "artwork"

    @property
    def upload_path(self) -> Path:
        return self.storage_path / "uploads"

    @property
    def midi_path(self) -> Path:
        return self.storage_path / "midi"

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    def _resolve(self, raw: str) -> Path:
        p = Path(raw).expanduser()
        if not p.is_absolute():
            p = (BACKEND_DIR / p).resolve()
        return p

    def ensure_directories(self) -> None:
        """Create every storage directory the application writes to."""
        for path in (
            self.storage_path,
            self.audio_path,
            self.artwork_path,
            self.upload_path,
            self.midi_path,
        ):
            path.mkdir(parents=True, exist_ok=True)
        db_file = self.sqlite_file_path
        if db_file is not None:
            db_file.parent.mkdir(parents=True, exist_ok=True)

    @property
    def sqlite_file_path(self) -> Optional[Path]:
        if not self.database_url.startswith("sqlite"):
            return None
        _, _, raw = self.database_url.partition(":///")
        if not raw or raw == ":memory:":
            return None
        return self._resolve(raw)

    @field_validator("environment")
    @classmethod
    def _validate_environment(cls, value: str) -> str:
        allowed = {"development", "test", "production", "prod"}
        normalised = value.strip().lower()
        if normalised not in allowed:
            raise ValueError(f"environment must be one of {sorted(allowed)}")
        return normalised

    @field_validator("cors_origins", "allowed_audio_extensions", "allowed_midi_extensions", mode="before")
    @classmethod
    def _split_csv(cls, value):
        """Allow comma separated env values, e.g. ``a,b,c``."""
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    """Used by tests that need to rebuild settings from a fresh environment."""
    get_settings.cache_clear()


settings = get_settings()

__all__ = ["Settings", "get_settings", "reset_settings_cache", "settings", "BACKEND_DIR", "PROJECT_ROOT"]

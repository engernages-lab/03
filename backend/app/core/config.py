"""Centralised, environment-driven configuration.

All settings are read from environment variables (optionally via a local
``.env`` file) with the ``POCKETSCORE_`` prefix.  Nothing secret is ever
hard-coded and ``.env`` is git-ignored.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from pydantic import Field, field_validator
from pydantic_settings import (
    BaseSettings,
    DotEnvSettingsSource,
    EnvSettingsSource,
    SettingsConfigDict,
)

BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_DIR.parent

# Fields that accept a comma separated list in the environment.
CSV_FIELDS = frozenset({"cors_origins", "allowed_audio_extensions", "allowed_midi_extensions"})


class _CsvEnvSource(EnvSettingsSource):
    def prepare_field_value(self, field_name, field, value, value_is_complex):
        if field_name in CSV_FIELDS and isinstance(value, str):
            return value
        return super().prepare_field_value(field_name, field, value, value_is_complex)


class _CsvDotEnvSource(DotEnvSettingsSource):
    def prepare_field_value(self, field_name, field, value, value_is_complex):
        if field_name in CSV_FIELDS and isinstance(value, str):
            return value
        return super().prepare_field_value(field_name, field, value, value_is_complex)


class Settings(BaseSettings):
    """Runtime configuration for the PocketScore AI API."""

    model_config = SettingsConfigDict(
        env_prefix="POCKETSCORE_",
        env_file=(str(BACKEND_DIR / ".env"), str(PROJECT_ROOT / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        # `model_preload` is a legitimate setting; relax the pydantic "model_"
        # protected namespace so it does not warn on every import.
        protected_namespaces=("settings_",),
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        """Read CSV list fields as plain strings.

        pydantic-settings 2.2 json-decodes complex fields *before* validators,
        so ``POCKETSCORE_CORS_ORIGINS=a,b`` would crash at import time. The
        subclasses below hand the raw string to ``_split_csv`` instead.
        """
        return (
            init_settings,
            _CsvEnvSource(settings_cls),
            _CsvDotEnvSource(settings_cls),
            file_secret_settings,
        )

    # -- application -------------------------------------------------------
    app_name: str = "PocketScore AI"
    app_version: str = "1.0.0a1"
    release_stage: str = "V1.0-A"
    environment: str = "development"  # development | test | staging | production
    debug: bool = True
    api_v1_prefix: str = "/api/v1"

    # -- server ------------------------------------------------------------    host: str = "127.0.0.1"
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
    max_upload_mb: int = 100
    # Hard ceiling for transcription input; keeps model runtime bounded.
    max_audio_duration_seconds: int = 600
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

    # -- staging access gate (V1.1-C.2.2) ---------------------------------
    # The backend has no user accounts until C.5, so a deployed environment must
    # be behind a shared credential. mode=auto enables the gate for
    # staging/production and leaves development/test open.
    access_gate_mode: str = "auto"  # auto | token | basic | off
    access_gate_token: Optional[str] = None
    access_gate_user: Optional[str] = None
    access_gate_password: Optional[str] = None

    # -- inference capacity (C.2) -----------------------------------------
    # One CPU inference at a time is the safe default: a single job peaks at
    # ~262 MB, so concurrency multiplies memory without adding throughput.
    max_concurrent_inferences: int = 1
    # How long a job may wait for a free inference slot before returning 503.
    inference_queue_timeout_seconds: int = 30
    # Wall-clock budget for one inference; exceeding it marks the job failed.
    inference_timeout_seconds: int = 300
    # Load the model (and run one warm-up inference) during startup.
    model_preload: bool = False

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
    def is_test(self) -> bool:
        return self.environment.lower() == "test"

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}

    @property
    def is_staging(self) -> bool:
        return self.environment.lower() == "staging"

    @property
    def requires_hardened_secrets(self) -> bool:
        """Staging and production must not run on placeholder secrets."""
        return self.is_staging or self.is_production

    def validate_hardened_secrets(self) -> list[str]:
        """Return the configuration problems that must block a hardened boot.

        Called from the app factory rather than a field validator so that unit
        tests may construct ``Settings`` freely; a *running* staging/production
        service refuses to start with placeholder secrets.
        """
        if not self.requires_hardened_secrets:
            return []
        problems: list[str] = []
        if not self.session_secret or self.session_secret == "change-me-in-production":
            problems.append(
                "POCKETSCORE_SESSION_SECRET must be set to a random value of at least 32 characters"
            )
        elif len(self.session_secret) < 32:
            problems.append("POCKETSCORE_SESSION_SECRET must be at least 32 characters long")
        if not self.token_encryption_key:
            problems.append(
                "POCKETSCORE_TOKEN_ENCRYPTION_KEY must be set (tokens would be lost on redeploy)"
            )
        if "*" in self.cors_origins:
            problems.append("POCKETSCORE_CORS_ORIGINS must not contain '*' when credentials are allowed")
        if self.allow_private_network_sources:
            problems.append(
                "POCKETSCORE_ALLOW_PRIVATE_NETWORK_SOURCES must be false outside a trusted LAN"
            )
        mode = (self.access_gate_mode or "auto").strip().lower()
        if mode not in {"auto", "token", "basic", "off"}:
            problems.append("POCKETSCORE_ACCESS_GATE_MODE must be one of auto|token|basic|off")
        if mode == "off":
            problems.append(
                "POCKETSCORE_ACCESS_GATE_MODE=off is not allowed in staging/production: this API "
                "has no user authentication yet and must not be exposed unauthenticated"
            )
        elif mode == "token" and not self.access_gate_token:
            problems.append("POCKETSCORE_ACCESS_GATE_TOKEN is required when the gate mode is token")
        elif mode == "basic":
            if not (self.access_gate_user and self.access_gate_password):
                problems.append(
                    "POCKETSCORE_ACCESS_GATE_USER and POCKETSCORE_ACCESS_GATE_PASSWORD are both "
                    "required when the gate mode is basic"
                )
        elif mode == "auto" and not (
            self.access_gate_token or (self.access_gate_user and self.access_gate_password)
        ):
            problems.append(
                "no access gate credential configured: this API has no user authentication yet, so "
                "staging/production refuses to start without POCKETSCORE_ACCESS_GATE_TOKEN or "
                "POCKETSCORE_ACCESS_GATE_USER/PASSWORD"
            )
        return problems

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
        allowed = {"development", "test", "staging", "production", "prod"}
        normalised = value.strip().lower()
        if normalised not in allowed:
            raise ValueError(f"environment must be one of {sorted(allowed)}")
        return normalised

    @field_validator("cors_origins", "allowed_audio_extensions", "allowed_midi_extensions", mode="before")
    @classmethod
    def _split_csv(cls, value):
        """Accept ``a,b,c`` (preferred) or a JSON list for compatibility."""
        if isinstance(value, str):
            text = value.strip()
            if text.startswith("["):
                try:
                    import json

                    parsed = json.loads(text)
                    if isinstance(parsed, list):
                        return [str(item).strip() for item in parsed if str(item).strip()]
                except ValueError:
                    pass
            return [item.strip() for item in text.split(",") if item.strip()]
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    """Used by tests that need to rebuild settings from a fresh environment."""
    get_settings.cache_clear()


settings = get_settings()

__all__ = ["Settings", "get_settings", "reset_settings_cache", "settings", "BACKEND_DIR", "PROJECT_ROOT"]

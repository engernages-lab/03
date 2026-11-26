"""Production hardening rules for settings (V1.1-C.2).

The point of these tests is that a staging/production process must refuse to run
with placeholder secrets instead of silently serving with a known key.
"""

from __future__ import annotations

from app.core.config import Settings

GOOD_SECRET = "x" * 40


def build(**overrides) -> Settings:
    """Build Settings without reading a developer .env file."""
    base = {
        "environment": "staging",
        "session_secret": GOOD_SECRET,
        "token_encryption_key": "ZmFrZS1mZXJuZXQta2V5LWZvci10ZXN0cy0xMjM0NTY=",
        "cors_origins": ["https://engernages-lab.github.io"],
        "allow_private_network_sources": False,
    }
    base.update(overrides)
    return Settings(**base)


def test_development_may_use_local_defaults():
    settings = Settings(environment="development")
    assert settings.validate_hardened_secrets() == []


def test_staging_rejects_placeholder_session_secret():
    settings = build(session_secret="change-me-in-production")
    problems = settings.validate_hardened_secrets()
    assert any("SESSION_SECRET" in problem for problem in problems)


def test_staging_rejects_short_session_secret():
    settings = build(session_secret="short")
    assert any("at least 32" in problem for problem in settings.validate_hardened_secrets())


def test_staging_requires_token_encryption_key():
    settings = build(token_encryption_key=None)
    assert any("TOKEN_ENCRYPTION_KEY" in problem for problem in settings.validate_hardened_secrets())


def test_staging_rejects_wildcard_cors():
    settings = build(cors_origins=["*"])
    assert any("CORS_ORIGINS" in problem for problem in settings.validate_hardened_secrets())


def test_staging_rejects_private_network_sources():
    settings = build(allow_private_network_sources=True)
    assert any("ALLOW_PRIVATE_NETWORK_SOURCES" in problem for problem in settings.validate_hardened_secrets())


def test_fully_configured_staging_is_accepted():
    assert build().validate_hardened_secrets() == []


def test_production_is_treated_as_hardened():
    settings = build(environment="production", session_secret="change-me-in-production")
    assert settings.is_production is True
    assert settings.validate_hardened_secrets() != []


def test_environment_accepts_staging():
    assert Settings(environment="STAGING").environment == "staging"


def test_inference_defaults_are_conservative():
    settings = Settings(environment="development")
    assert settings.max_concurrent_inferences == 1
    assert settings.inference_timeout_seconds >= 60
    assert settings.max_upload_mb <= 200

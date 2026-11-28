"""CORS hardening tests (V1.1-C.2.3.4.3)."""

from __future__ import annotations

import pytest

from app.core import config as config_module
from app.core import db as db_module

ALLOWED = "http://localhost:5173"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    root = tmp_path / "cors"
    (root / "storage").mkdir(parents=True)
    monkeypatch.setenv("POCKETSCORE_ENVIRONMENT", "test")
    monkeypatch.setenv("POCKETSCORE_DATABASE_URL", f"sqlite:///{(root / 'db.sqlite').as_posix()}")
    monkeypatch.setenv("POCKETSCORE_STORAGE_DIR", str(root / "storage"))
    monkeypatch.setenv("POCKETSCORE_ACCESS_GATE_MODE", "off")
    monkeypatch.setenv("POCKETSCORE_MODEL_PRELOAD", "false")
    monkeypatch.setenv("POCKETSCORE_CORS_ORIGINS", ALLOWED)
    config_module.get_settings.cache_clear()
    db_module.dispose_engine()

    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client
    config_module.get_settings.cache_clear()
    db_module.dispose_engine()


def test_allowed_origin_is_echoed_exactly(client) -> None:
    response = client.get("/health", headers={"Origin": ALLOWED})
    assert response.headers.get("access-control-allow-origin") == ALLOWED
    assert response.headers.get("access-control-allow-credentials") == "true"


@pytest.mark.parametrize(
    "origin",
    [
        "http://localhost:5173.evil.example",   # lookalike suffix
        "https://localhost:5173",               # scheme swap
        "http://localhost:5174",                # wrong port
        "http://evil.example",                  # unrelated
        "null",                                 # opaque origin
        "http://localhost:5173/path",           # origin must not carry a path
        "http://user:pass@localhost:5173",      # credentials in origin
        "ftp://localhost:5173",                 # non-http scheme
    ],
)
def test_other_origins_are_not_allowed(client, origin: str) -> None:
    response = client.get("/health", headers={"Origin": origin})
    assert response.headers.get("access-control-allow-origin") is None


def test_wildcard_is_never_returned(client) -> None:
    response = client.get("/health", headers={"Origin": ALLOWED})
    assert response.headers.get("access-control-allow-origin") != "*"


def test_preflight_allows_configured_method_and_header(client) -> None:
    response = client.options(
        "/api/v1/audio/upload",
        headers={
            "Origin": ALLOWED,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Authorization, Content-Type",
        },
    )
    assert response.status_code == 200
    allowed_methods = response.headers.get("access-control-allow-methods", "")
    assert "POST" in allowed_methods
    assert "OPTIONS" in allowed_methods
    assert "*" not in allowed_methods
    allowed_headers = response.headers.get("access-control-allow-headers", "").lower()
    assert "authorization" in allowed_headers
    assert "content-type" in allowed_headers


def test_preflight_rejects_unlisted_header(client) -> None:
    response = client.options(
        "/api/v1/audio/assets",
        headers={
            "Origin": ALLOWED,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "X-Not-Allowed",
        },
    )
    allowed_headers = response.headers.get("access-control-allow-headers", "").lower()
    assert "x-not-allowed" not in allowed_headers


def test_range_header_is_allowed_for_audio_streaming(client) -> None:
    response = client.options(
        "/api/v1/audio/assets/x/stream",
        headers={
            "Origin": ALLOWED,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Range",
        },
    )
    assert "range" in response.headers.get("access-control-allow-headers", "").lower()


def test_retry_after_is_exposed(client) -> None:
    response = client.get("/health", headers={"Origin": ALLOWED})
    exposed = response.headers.get("access-control-expose-headers", "").lower()
    assert "retry-after" in exposed


def test_invalid_origin_entry_is_reported_in_hardened_mode() -> None:
    from app.core.config import Settings

    settings = Settings(
        environment="production",
        session_secret="s" * 40,
        token_encryption_key="k" * 44,
        access_gate_mode="token",
        access_gate_token="t" * 40,
        allow_private_network_sources=False,
        cors_origins=["https://ok.example", "https://bad.example/path"],
    )
    problems = settings.validate_hardened_secrets()
    assert any("not a scheme://host[:port] origin" in problem for problem in problems)

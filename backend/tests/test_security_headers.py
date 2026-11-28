"""Security response header tests (V1.1-C.2.3.4.3)."""

from __future__ import annotations

import pytest

from app.core.security_headers import BASE_HEADERS, DEFAULT_CSP, header_values

REQUIRED = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from app.core import config as config_module
    from app.core import db as db_module

    root = tmp_path / "hdr"
    (root / "storage").mkdir(parents=True)
    monkeypatch.setenv("POCKETSCORE_ENVIRONMENT", "test")
    monkeypatch.setenv("POCKETSCORE_DATABASE_URL", f"sqlite:///{(root / 'db.sqlite').as_posix()}")
    monkeypatch.setenv("POCKETSCORE_STORAGE_DIR", str(root / "storage"))
    monkeypatch.setenv("POCKETSCORE_ACCESS_GATE_MODE", "off")
    monkeypatch.setenv("POCKETSCORE_MODEL_PRELOAD", "false")
    monkeypatch.setenv("POCKETSCORE_RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("POCKETSCORE_RATE_LIMIT_REQUESTS", "2")
    config_module.get_settings.cache_clear()
    db_module.dispose_engine()

    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client
    config_module.get_settings.cache_clear()
    db_module.dispose_engine()


def _assert_secured(response) -> None:
    for name, value in REQUIRED.items():
        assert response.headers.get(name) == value, f"{name} missing on {response.request.method} {response.request.url}"
    assert "content-security-policy" in response.headers
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert "object-src 'none'" in response.headers["content-security-policy"]
    assert "camera=()" in response.headers["permissions-policy"]


def test_headers_on_success(client) -> None:
    _assert_secured(client.get("/health"))


def test_headers_on_error_404(client) -> None:
    _assert_secured(client.get("/api/v1/audio/assets/does-not-exist"))


def test_headers_on_401(client) -> None:
    from fastapi.testclient import TestClient

    from app.core import config as config_module
    from app.core import db as db_module
    from app.main import create_app

    config_module.get_settings.cache_clear()
    db_module.dispose_engine()
    import os

    os.environ["POCKETSCORE_ACCESS_GATE_MODE"] = "token"
    os.environ["POCKETSCORE_ACCESS_GATE_TOKEN"] = "h" * 32
    try:
        config_module.get_settings.cache_clear()
        with TestClient(create_app()) as gated:
            response = gated.get("/api/v1/audio/assets")
            assert response.status_code == 401
            _assert_secured(response)
    finally:
        os.environ.pop("POCKETSCORE_ACCESS_GATE_TOKEN", None)
        config_module.get_settings.cache_clear()


def test_headers_on_429(client) -> None:
    client.get("/api/v1/audio/assets")
    client.get("/api/v1/audio/assets")
    blocked = client.get("/api/v1/audio/assets")
    assert blocked.status_code == 429
    _assert_secured(blocked)


def test_headers_on_preflight(client) -> None:
    response = client.options(
        "/api/v1/audio/assets",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"},
    )
    assert response.status_code == 200
    _assert_secured(response)


def test_no_hsts_by_default() -> None:
    assert "Strict-Transport-Security" not in header_values()


def test_hsts_only_when_enabled() -> None:
    headers = header_values(hsts=True, hsts_max_age=600)
    assert headers["Strict-Transport-Security"] == "max-age=600"


def test_csp_allows_the_bundled_spa() -> None:
    # inline styles are used by the built bundle; scripts are same-origin only
    assert "style-src 'self' 'unsafe-inline'" in DEFAULT_CSP
    assert "script-src 'self'" in DEFAULT_CSP
    assert "connect-src 'self'" in DEFAULT_CSP


def test_base_headers_do_not_include_cors(client) -> None:
    # CORS headers belong to the CORS middleware, not this one
    assert "Access-Control-Allow-Origin" not in BASE_HEADERS

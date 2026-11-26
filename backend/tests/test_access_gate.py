"""Access gate contract (V1.1-C.2.2).

The staging deployment must never be reachable without credentials, and a
misconfigured gate must stop the process instead of silently serving openly.
"""

from __future__ import annotations

import base64

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.core.access_gate import (
    EXEMPT_PATHS,
    MAX_FAILURES,
    AccessGate,
    AccessGateMiddleware,
    build_gate,
    gate_problems,
)
from app.core.config import Settings

TOKEN = "staging-token-abcdef0123456789"
USER = "tester"
PASSWORD = "s3cret-pass"


def staging(**overrides) -> Settings:
    base = {
        "environment": "staging",
        "session_secret": "x" * 40,
        "token_encryption_key": "ZmFrZS1mZXJuZXQta2V5LWZvci10ZXN0cy0xMjM0NTY=",
        "cors_origins": ["https://engernages-lab.github.io"],
        "allow_private_network_sources": False,
        "access_gate_token": TOKEN,
    }
    base.update(overrides)
    return Settings(**base)


def build_app(gate: AccessGate) -> TestClient:
    app = FastAPI()
    app.add_middleware(AccessGateMiddleware, gate=gate)

    @app.get("/health")
    def health():  # noqa: D401
        return {"status": "ok"}

    @app.get("/ready")
    def ready():  # noqa: D401
        return {"ready": True}

    @app.get("/api/v1/documents")
    def documents():  # noqa: D401
        return {"items": [], "total": 0}

    @app.post("/api/v1/audio/upload")
    def upload():  # noqa: D401
        return JSONResponse({"ok": True}, status_code=201)

    return TestClient(app)


# -- configuration gate -------------------------------------------------------


def test_staging_refuses_to_start_without_any_credential():
    settings = staging(access_gate_token=None)
    problems = settings.validate_hardened_secrets()
    assert any("access gate" in problem.lower() for problem in problems)


def test_staging_refuses_explicit_off_mode():
    settings = staging(access_gate_token=None, access_gate_mode="off")
    assert any("MODE=off" in problem for problem in settings.validate_hardened_secrets())


def test_staging_accepts_bearer_token():
    assert staging().validate_hardened_secrets() == []


def test_staging_accepts_basic_credentials():
    settings = staging(
        access_gate_token=None, access_gate_user=USER, access_gate_password=PASSWORD
    )
    assert settings.validate_hardened_secrets() == []


def test_token_mode_without_token_is_reported():
    settings = staging(access_gate_mode="token", access_gate_token=None)
    assert any("ACCESS_GATE_TOKEN" in problem for problem in settings.validate_hardened_secrets())


def test_basic_mode_requires_both_halves():
    settings = staging(access_gate_mode="basic", access_gate_token=None, access_gate_user="only-user")
    assert any("USER and" in problem for problem in settings.validate_hardened_secrets())


def test_development_stays_open():
    settings = Settings(environment="development")
    problems, gate = gate_problems(settings)
    assert problems == []
    assert gate.enabled is False


def test_auto_mode_picks_the_configured_credential():
    token_gate = build_gate(staging())
    basic_gate = build_gate(staging(access_gate_token=None, access_gate_user=USER, access_gate_password=PASSWORD))
    assert token_gate.mode == "token"
    assert basic_gate.mode == "basic"


# -- runtime gate -------------------------------------------------------------


def test_probes_stay_reachable_without_credentials():
    client = build_app(AccessGate("token", TOKEN, None, None))
    for path in EXEMPT_PATHS:
        response = client.get(path)
        assert response.status_code == 200, path


def test_api_requires_credentials():
    client = build_app(AccessGate("token", TOKEN, None, None))
    response = client.get("/api/v1/documents")
    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "ACCESS_GATE_REQUIRED"
    assert "Basic realm" in response.headers.get("www-authenticate", "")


def test_valid_bearer_token_is_allowed():
    client = build_app(AccessGate("token", TOKEN, None, None))
    response = client.get("/api/v1/documents", headers={"Authorization": f"Bearer {TOKEN}"})
    assert response.status_code == 200


def test_wrong_token_is_rejected():
    client = build_app(AccessGate("token", TOKEN, None, None))
    response = client.get("/api/v1/documents", headers={"Authorization": "Bearer nope"})
    assert response.status_code == 401


def test_basic_auth_is_accepted_in_basic_mode():
    gate = AccessGate("basic", None, USER, PASSWORD)
    client = build_app(gate)
    encoded = base64.b64encode(f"{USER}:{PASSWORD}".encode()).decode()
    assert client.get("/api/v1/documents").status_code == 401
    assert client.get("/api/v1/documents", headers={"Authorization": f"Basic {encoded}"}).status_code == 200


def test_malformed_basic_header_is_rejected():
    gate = AccessGate("basic", None, USER, PASSWORD)
    client = build_app(gate)
    response = client.get("/api/v1/documents", headers={"Authorization": "Basic !!!not-base64!!!"})
    assert response.status_code == 401


def test_preflight_is_not_blocked():
    """CORS preflight never carries credentials; blocking it breaks the browser."""
    client = build_app(AccessGate("token", TOKEN, None, None))
    response = client.options("/api/v1/documents", headers={"Origin": "https://x.example"})
    assert response.status_code != 401


def test_repeated_failures_are_throttled():
    gate = AccessGate("token", TOKEN, None, None)
    client = build_app(gate)
    codes = [client.get("/api/v1/documents").status_code for _ in range(MAX_FAILURES + 3)]
    assert codes[0] == 401
    assert 429 in codes


def test_gate_description_never_contains_the_credential():
    gate = build_gate(staging())
    described = gate.describe()
    serialised = str(described)
    assert TOKEN not in serialised
    assert described["token_configured"] is True


def test_upload_route_is_protected_too():
    client = build_app(AccessGate("token", TOKEN, None, None))
    assert client.post("/api/v1/audio/upload").status_code == 401
    assert (
        client.post("/api/v1/audio/upload", headers={"Authorization": f"Bearer {TOKEN}"}).status_code
        == 201
    )


def test_gate_disabled_passes_everything():
    client = build_app(AccessGate("off", None, None, None))
    assert client.get("/api/v1/documents").status_code == 200

"""Health and readiness endpoint tests."""

from __future__ import annotations


def test_health_reports_identity_and_capabilities(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["stage"] == "V1.0-A"
    assert body["version"]
    caps = body["capabilities"]
    for key in ("ffmpeg", "librosa", "mido", "pretty_midi", "music21", "mutagen"):
        assert key in caps, f"capability {key} missing from probe"
    assert isinstance(caps["ffmpeg"]["available"], bool)


def test_readiness_checks_database(client):
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["checks"]["database"]["ok"] is True
    assert body["status"] in {"ready", "degraded"}


def test_root_endpoint(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["stage"] == "V1.0-A"


def test_request_id_header_is_echoed(client):
    response = client.get("/api/v1/health", headers={"X-Request-ID": "abc123"})
    assert response.headers["X-Request-ID"] == "abc123"


def test_unknown_route_uses_error_envelope(client):
    response = client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    body = response.json()
    assert "error" in body
    assert body["error"]["code"] == "HTTP_404"
    assert body["error"]["request_id"]

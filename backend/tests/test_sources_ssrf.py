"""SSRF and credential-handling tests."""

from __future__ import annotations

import pytest

from app.core.errors import SSRFBlockedError
from app.core.ssrf import validate_server_url


def test_rejects_non_http_schemes():
    for url in ("file:///etc/passwd", "ftp://example.com", "gopher://x", "javascript:alert(1)"):
        with pytest.raises(SSRFBlockedError):
            validate_server_url(url)


def test_rejects_localhost_and_loopback():
    for url in ("http://localhost:4533", "http://127.0.0.1", "https://127.0.0.2:8000", "http://[::1]:80"):
        with pytest.raises(SSRFBlockedError):
            validate_server_url(url, allow_private=True)


def test_rejects_cloud_metadata_addresses():
    with pytest.raises(SSRFBlockedError):
        validate_server_url("http://169.254.169.254/latest/meta-data/")
    with pytest.raises(SSRFBlockedError):
        validate_server_url("http://100.100.100.200/")


def test_rejects_embedded_credentials():
    with pytest.raises(SSRFBlockedError):
        validate_server_url("https://user:pass@music.example.com")


def test_private_network_allowed_only_when_enabled():
    allowed = validate_server_url("http://192.168.1.10:4533", allow_private=True)
    assert allowed.host == "192.168.1.10"
    assert allowed.port == 4533

    with pytest.raises(SSRFBlockedError):
        validate_server_url("http://192.168.1.10:4533", allow_private=False)


def test_public_ip_is_normalised():
    result = validate_server_url("https://93.184.216.34/", allow_private=False)
    assert result.normalized == "https://93.184.216.34"
    assert result.scheme == "https"
    assert result.port == 443
    assert result.resolved_ips == ["93.184.216.34"]


def test_scheme_defaults_to_https():
    result = validate_server_url("93.184.216.34:8443", allow_private=False)
    assert result.normalized == "https://93.184.216.34:8443"
    assert result.port == 8443


def test_empty_url_rejected():
    with pytest.raises(SSRFBlockedError):
        validate_server_url("   ")


def test_api_source_creation_blocks_ssrf(client):
    response = client.post(
        "/api/v1/sources",
        json={
            "provider": "subsonic",
            "server_url": "http://169.254.169.254",
            "username": "u",
            "password": "p",
        },
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "SSRF_BLOCKED"


def test_api_source_requires_credentials(client):
    response = client.post(
        "/api/v1/sources", json={"provider": "subsonic", "server_url": "http://192.168.1.10:4533"}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "SOURCE_CONFIG_INVALID"


def test_unsupported_provider_cannot_be_created(client):
    response = client.post("/api/v1/sources", json={"provider": "local"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "PROVIDER_NOT_CREATABLE"

"""Apple Music developer-token and Spotify OAuth URL tests.

The Apple test signs a real ES256 JWT with a generated P-256 key and verifies
the signature - no mocks, no canned token.
"""

from __future__ import annotations

import base64
import json
import uuid

import pytest

from app.core.errors import ProviderError
from app.services import library
from app.services.sources.apple import AppleMusicAdapter


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


@pytest.fixture(scope="module")
def ec_key(tmp_path_factory):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    path = tmp_path_factory.mktemp("apple") / "AuthKey_TEST.p8"
    path.write_bytes(pem)
    return key, path


def test_developer_token_is_a_valid_es256_jwt(ec_key):
    private_key, key_path = ec_key
    adapter = AppleMusicAdapter(
        "src_apple",
        {
            "team_id": "TEAM123456",
            "key_id": "KEY7890123",
            "private_key_path": str(key_path),
            "storefront": "cn",
        },
    )
    token = adapter.developer_token()
    header_b64, payload_b64, signature_b64 = token.split(".")

    header = json.loads(_b64decode(header_b64))
    payload = json.loads(_b64decode(payload_b64))
    assert header == {"alg": "ES256", "kid": "KEY7890123", "typ": "JWT"}
    assert payload["iss"] == "TEAM123456"
    assert payload["exp"] - payload["iat"] == 180 * 24 * 3600

    # Verify the raw r||s signature with the matching public key.
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

    raw = _b64decode(signature_b64)
    assert len(raw) == 64
    r = int.from_bytes(raw[:32], "big")
    s = int.from_bytes(raw[32:], "big")
    der = encode_dss_signature(r, s)
    signing_input = f"{header_b64}.{payload_b64}".encode()
    # raises InvalidSignature if the token was not signed by this key
    private_key.public_key().verify(der, signing_input, ec.ECDSA(hashes.SHA256()))


def test_developer_token_is_cached(ec_key):
    _private_key, key_path = ec_key
    adapter = AppleMusicAdapter(
        "src_apple2",
        {"team_id": "T", "key_id": "K", "private_key_path": str(key_path)},
    )
    assert adapter.developer_token() == adapter.developer_token()


def test_missing_configuration_raises_provider_error(tmp_path):
    adapter = AppleMusicAdapter("src_missing", {"team_id": "T"})
    with pytest.raises(ProviderError) as exc:
        adapter.developer_token()
    assert exc.value.code == "PROVIDER_NOT_CONFIGURED"


def test_missing_key_file_raises_provider_error():
    adapter = AppleMusicAdapter(
        "src_nofile",
        {"team_id": "T", "key_id": "K", "private_key_path": "C:/does/not/exist.p8"},
    )
    with pytest.raises(ProviderError):
        adapter.developer_token()


def test_api_returns_token_and_reports_storefront(client, db_session, ec_key):
    _private_key, key_path = ec_key
    source = library.create_source(
        db_session,
        provider="apple_music",
        display_name=f"apple-{uuid.uuid4().hex[:6]}",
        config={
            "team_id": "TEAM123456",
            "key_id": "KEY7890123",
            "private_key_path": str(key_path),
            "storefront": "cn",
        },
    )
    response = client.get(f"/api/v1/sources/{source.id}/apple/developer-token")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["developer_token"].count(".") == 2
    assert body["storefront"] == "cn"
    assert body["expires_in"] == 86_400


def test_api_returns_501_when_apple_not_configured(client, db_session):
    source = library.create_source(
        db_session,
        provider="apple_music",
        display_name=f"apple-{uuid.uuid4().hex[:6]}",
        config={},
    )
    response = client.get(f"/api/v1/sources/{source.id}/apple/developer-token")
    assert response.status_code == 501
    assert response.json()["error"]["code"] == "PROVIDER_NOT_CONFIGURED"


def test_api_rejects_provider_mismatch(client, db_session):
    source = library.create_source(
        db_session,
        provider="subsonic",
        display_name=f"sub-{uuid.uuid4().hex[:6]}",
        config={},
    )
    response = client.get(f"/api/v1/sources/{source.id}/apple/developer-token")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "PROVIDER_MISMATCH"


def test_spotify_authorize_url_with_config(client, db_session):
    source = library.create_source(
        db_session,
        provider="spotify",
        display_name=f"spotify-{uuid.uuid4().hex[:6]}",
        config={
            "client_id": "client123",
            "client_secret": "secret456",
            "redirect_uri": "http://127.0.0.1:8000/api/v1/sources/spotify/callback",
        },
    )
    response = client.get(f"/api/v1/sources/{source.id}/spotify/authorize-url")
    assert response.status_code == 200, response.text
    body = response.json()
    url = body["authorize_url"]
    assert url.startswith("https://accounts.spotify.com/authorize?")
    assert "client_id=client123" in url
    assert "response_type=code" in url
    assert "playlist-read-private" in url
    assert body["state"]
    assert "AI 分析被平台政策禁止" in body["note"]


def test_spotify_authorize_url_without_config_is_501(client, db_session):
    source = library.create_source(
        db_session,
        provider="spotify",
        display_name=f"spotify-{uuid.uuid4().hex[:6]}",
        config={},
    )
    response = client.get(f"/api/v1/sources/{source.id}/spotify/authorize-url")
    assert response.status_code == 501
    assert response.json()["error"]["code"] == "PROVIDER_NOT_CONFIGURED"

"""API rate limiting tests (V1.1-C.2.3.4.3).

The limiter takes an injectable clock, so window behaviour is tested without
sleeping. API-level tests build a dedicated app with tiny limits.
"""

from __future__ import annotations

import pytest

from app.core import config as config_module
from app.core import db as db_module
from app.core.ratelimit import (
    BUCKET_GENERAL,
    BUCKET_TRANSCRIPTION,
    BUCKET_UPLOAD,
    BUCKET_WAVEFORM,
    RATE_LIMIT_EXCEEDED,
    RateLimiter,
    Rule,
    bucket_for,
    client_ip,
    parse_cidrs,
)


class Clock:
    def __init__(self, now: float = 1000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture()
def limiter() -> RateLimiter:
    clock = Clock()
    return RateLimiter({BUCKET_UPLOAD: Rule(2, 60)}, clock=clock)


def test_requests_are_allowed_until_the_limit(limiter: RateLimiter) -> None:
    assert limiter.check(BUCKET_UPLOAD, "1.1.1.1").allowed is True
    assert limiter.check(BUCKET_UPLOAD, "1.1.1.1").allowed is True
    third = limiter.check(BUCKET_UPLOAD, "1.1.1.1")
    assert third.allowed is False
    assert third.retry_after >= 1
    assert third.remaining == 0


def test_window_slides_and_resets(limiter: RateLimiter) -> None:
    for _ in range(2):
        limiter.check(BUCKET_UPLOAD, "1.1.1.1")
    assert limiter.check(BUCKET_UPLOAD, "1.1.1.1").allowed is False
    limiter._clock.advance(61)  # type: ignore[attr-defined]
    assert limiter.check(BUCKET_UPLOAD, "1.1.1.1").allowed is True


def test_clients_are_isolated(limiter: RateLimiter) -> None:
    assert limiter.check(BUCKET_UPLOAD, "1.1.1.1").allowed
    assert limiter.check(BUCKET_UPLOAD, "2.2.2.2").allowed
    limiter.check(BUCKET_UPLOAD, "1.1.1.1")
    assert limiter.check(BUCKET_UPLOAD, "1.1.1.1").allowed is False
    assert limiter.check(BUCKET_UPLOAD, "2.2.2.2").allowed is True


def test_buckets_are_independent() -> None:
    clock = Clock()
    limiter = RateLimiter(
        {BUCKET_UPLOAD: Rule(1, 60), BUCKET_GENERAL: Rule(5, 60)}, clock=clock
    )
    assert limiter.check(BUCKET_UPLOAD, "ip").allowed
    assert limiter.check(BUCKET_UPLOAD, "ip").allowed is False
    assert limiter.check(BUCKET_GENERAL, "ip").allowed is True


def test_disabled_limiter_allows_everything() -> None:
    limiter = RateLimiter({BUCKET_UPLOAD: Rule(1, 60)}, enabled=False, clock=Clock())
    for _ in range(10):
        assert limiter.check(BUCKET_UPLOAD, "ip").allowed is True


def test_key_space_is_bounded() -> None:
    clock = Clock()
    limiter = RateLimiter({BUCKET_GENERAL: Rule(10, 60)}, max_keys=50, clock=clock)
    for index in range(500):
        limiter.check(BUCKET_GENERAL, f"10.0.0.{index % 250}-{index}")
        clock.advance(0.01)
    assert len(limiter) <= 50, "the key space must not grow without bound"


def test_stale_keys_are_evicted() -> None:
    clock = Clock()
    limiter = RateLimiter({BUCKET_GENERAL: Rule(5, 10)}, max_keys=4, clock=clock)
    for index in range(4):
        limiter.check(BUCKET_GENERAL, f"ip-{index}")
    clock.advance(60)
    limiter.check(BUCKET_GENERAL, "fresh")
    assert len(limiter) <= 4


# ------------------------------------------------------------------ client ip


TRUSTED = parse_cidrs(["127.0.0.1/32", "10.0.0.0/8"])


def test_untrusted_peer_cannot_spoof_forwarded_for() -> None:
    # rotating X-Forwarded-For from an untrusted peer must not change the identity
    assert client_ip("203.0.113.9", "1.2.3.4", TRUSTED) == "203.0.113.9"
    assert client_ip("203.0.113.9", "5.6.7.8, 9.9.9.9", TRUSTED) == "203.0.113.9"


def test_trusted_peer_uses_rightmost_untrusted_hop() -> None:
    assert client_ip("10.1.1.1", "198.51.100.7, 203.0.113.5", TRUSTED) == "203.0.113.5"
    # client-supplied leftmost value must never win
    assert client_ip("10.1.1.1", "1.1.1.1, 203.0.113.5", TRUSTED) == "203.0.113.5"


def test_all_trusted_chain_falls_back_safely() -> None:
    assert client_ip("10.1.1.1", "10.2.2.2, 10.3.3.3", TRUSTED) == "10.2.2.2"


def test_malformed_forwarded_for_is_ignored() -> None:
    assert client_ip("203.0.113.9", "not-an-ip", TRUSTED) == "203.0.113.9"
    assert client_ip("10.1.1.1", "not-an-ip", TRUSTED) == "10.1.1.1"


def test_ipv6_peer_and_hops() -> None:
    trusted = parse_cidrs(["::1/128", "fd00::/8"])
    assert client_ip("::1", "2001:db8::1", trusted) == "2001:db8::1"
    assert client_ip("2001:db8::2", "2001:db8::1", trusted) == "2001:db8::2"


# ------------------------------------------------------------------ routing


@pytest.mark.parametrize(
    ("method", "path", "bucket"),
    [
        ("POST", "/api/v1/audio/upload", BUCKET_UPLOAD),
        ("POST", "/api/v1/transcription/upload", BUCKET_UPLOAD),
        ("POST", "/api/v1/transcription/jobs", BUCKET_TRANSCRIPTION),
        ("GET", "/api/v1/audio/assets/abc/waveform", BUCKET_WAVEFORM),
        ("GET", "/api/v1/audio/assets", BUCKET_GENERAL),
        ("OPTIONS", "/api/v1/audio/upload", None),
        ("GET", "/health", None),
        ("GET", "/ready", None),
    ],
)
def test_bucket_routing(method: str, path: str, bucket) -> None:
    assert bucket_for(method, path) == bucket


# ------------------------------------------------------------------ API level


@pytest.fixture()
def tiny_limits(tmp_path, monkeypatch):
    """A dedicated app with a 3/minute general bucket and a 1/minute upload bucket."""
    root = tmp_path / "rl"
    (root / "storage").mkdir(parents=True)
    monkeypatch.setenv("POCKETSCORE_ENVIRONMENT", "test")
    monkeypatch.setenv("POCKETSCORE_DATABASE_URL", f"sqlite:///{(root / 'db.sqlite').as_posix()}")
    monkeypatch.setenv("POCKETSCORE_STORAGE_DIR", str(root / "storage"))
    monkeypatch.setenv("POCKETSCORE_ACCESS_GATE_MODE", "off")
    monkeypatch.setenv("POCKETSCORE_MODEL_PRELOAD", "false")
    monkeypatch.setenv("POCKETSCORE_RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("POCKETSCORE_RATE_LIMIT_REQUESTS", "3")
    monkeypatch.setenv("POCKETSCORE_UPLOAD_RATE_LIMIT_REQUESTS", "1")
    monkeypatch.setenv("POCKETSCORE_WAVEFORM_RATE_LIMIT_REQUESTS", "2")
    config_module.get_settings.cache_clear()
    db_module.dispose_engine()

    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app()
    with TestClient(app) as client:
        yield client
    config_module.get_settings.cache_clear()
    db_module.dispose_engine()


def test_general_bucket_returns_429_with_retry_after(tiny_limits) -> None:
    statuses = [tiny_limits.get("/api/v1/audio/assets").status_code for _ in range(3)]
    assert statuses == [200, 200, 200]
    blocked = tiny_limits.get("/api/v1/audio/assets")
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == RATE_LIMIT_EXCEEDED
    assert int(blocked.headers["retry-after"]) >= 1
    assert blocked.headers["x-ratelimit-remaining"] == "0"
    assert "storage" not in blocked.text.lower()


def test_upload_bucket_is_independent(tiny_limits) -> None:
    files = {"file": ("a.wav", b"RIFF0000WAVEfmt " + b"\x00" * 32, "audio/wav")}
    first = tiny_limits.post("/api/v1/audio/upload", files=files)
    second = tiny_limits.post("/api/v1/audio/upload", files=files)
    assert first.status_code in (201, 415, 422)
    assert second.status_code == 429
    # the general bucket was not touched by the upload attempts
    assert tiny_limits.get("/api/v1/audio/assets").status_code == 200


def test_health_and_ready_are_exempt(tiny_limits) -> None:
    for _ in range(10):
        assert tiny_limits.get("/health").status_code == 200
        assert tiny_limits.get("/ready").status_code == 200


def test_options_is_never_rate_limited(tiny_limits) -> None:
    headers = {"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"}
    for _ in range(10):
        assert tiny_limits.options("/api/v1/audio/assets", headers=headers).status_code == 200


def test_spoofed_forwarded_for_cannot_reset_the_bucket(tiny_limits) -> None:
    for _ in range(3):
        assert tiny_limits.get("/api/v1/audio/assets").status_code == 200
    # TestClient's peer is "testclient", which is not a trusted proxy
    for index in range(3):
        response = tiny_limits.get(
            "/api/v1/audio/assets", headers={"X-Forwarded-For": f"198.51.100.{index}"}
        )
        assert response.status_code == 429, "a forged header must not reset the limit"

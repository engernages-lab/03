"""Independent API rate limiting (V1.1-C.2.3.4.3).

This is deliberately **not** the access gate. The gate throttles repeated
credential failures; this module throttles ordinary API traffic by client IP and
by endpoint class, so a valid token cannot be used to saturate uploads or
inference.

Design
------
* Sliding window per (bucket, client) with a bounded number of keys.
* Bucket rules are configurable; ``upload``/``transcription`` are stricter.
* The store is an in-memory dict guarded by a lock, with a pluggable interface so
  a Redis-backed store can replace it later. **Single instance only**: counters
  do not survive a restart and are not shared between replicas.

Client identity
---------------
``X-Forwarded-For`` is honoured only when the *peer* is inside
``POCKETSCORE_TRUSTED_PROXY_CIDRS``; otherwise the header is ignored, because
trusting it unconditionally lets a client forge a fresh IP per request and bypass
the limit entirely. When a trusted proxy is present the rightmost address that is
not itself trusted is used (the standard "rightmost untrusted" rule), never the
leftmost value, which the client controls.
"""

from __future__ import annotations

import ipaddress
import json
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from app.core.errors import AppError

BUCKET_GENERAL = "general"
BUCKET_UPLOAD = "upload"
BUCKET_TRANSCRIPTION = "transcription"
BUCKET_WAVEFORM = "waveform"

RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"

DEFAULT_TRUSTED_PROXIES = (
    "127.0.0.1/32",
    "::1/128",
    "10.0.0.0/8",
    "172.16.0.0/12",
    "192.168.0.0/16",
)


class RateLimitExceeded(AppError):
    status_code = 429
    code = RATE_LIMIT_EXCEEDED
    message = "Too many requests; please retry later"


@dataclass(frozen=True)
class Rule:
    """One bucket: how many requests per window."""

    requests: int
    window_seconds: float

    def __post_init__(self) -> None:
        if self.requests <= 0:
            raise ValueError("requests must be positive")
        if self.window_seconds <= 0:
            raise ValueError("window_seconds must be positive")


@dataclass
class Decision:
    allowed: bool
    bucket: str
    limit: int
    remaining: int
    retry_after: int
    reset_after: float


@dataclass
class _Window:
    hits: List[float] = field(default_factory=list)


class RateLimiter:
    """Sliding-window limiter with a bounded key space."""

    def __init__(
        self,
        rules: Dict[str, Rule],
        *,
        enabled: bool = True,
        max_keys: int = 10_000,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.rules = dict(rules)
        self.enabled = enabled
        self.max_keys = max_keys
        self._clock = clock
        self._windows: Dict[Tuple[str, str], _Window] = {}
        self._lock = threading.Lock()

    # -- introspection ---------------------------------------------------- #
    def __len__(self) -> int:
        with self._lock:
            return len(self._windows)

    def rule_for(self, bucket: str) -> Optional[Rule]:
        return self.rules.get(bucket)

    # -- core ------------------------------------------------------------- #
    def check(self, bucket: str, client: str) -> Decision:
        rule = self.rules.get(bucket)
        if not self.enabled or rule is None:
            return Decision(True, bucket, 0, 0, 0, 0.0)

        now = self._clock()
        cutoff = now - rule.window_seconds
        key = (bucket, client)

        with self._lock:
            window = self._windows.get(key)
            if window is None:
                if len(self._windows) >= self.max_keys:
                    self._evict_locked(now)
                window = _Window()
                self._windows[key] = window

            window.hits = [stamp for stamp in window.hits if stamp > cutoff]
            allowed = len(window.hits) < rule.requests
            if allowed:
                window.hits.append(now)

            used = len(window.hits)
            remaining = max(0, rule.requests - used)
            if allowed:
                retry_after = 0
                reset_after = rule.window_seconds - (now - window.hits[0]) if window.hits else 0.0
            else:
                oldest = window.hits[0] if window.hits else now
                reset_after = max(0.0, rule.window_seconds - (now - oldest))
                retry_after = max(1, int(reset_after + 0.999))

        return Decision(allowed, bucket, rule.requests, remaining, retry_after, reset_after)

    def _evict_locked(self, now: float) -> None:
        """Drop stale keys, then the oldest ones if still at capacity."""
        stale = [
            key for key, window in self._windows.items()
            if not window.hits or now - window.hits[-1] > self.rules.get(key[0], Rule(1, 60)).window_seconds
        ]
        for key in stale:
            self._windows.pop(key, None)
        if len(self._windows) < self.max_keys:
            return
        # still full: drop the least recently used third
        ordered = sorted(self._windows.items(), key=lambda item: item[1].hits[-1] if item[1].hits else 0.0)
        for key, _window in ordered[: max(1, len(ordered) // 3)]:
            self._windows.pop(key, None)

    def reset(self) -> None:
        with self._lock:
            self._windows.clear()

    def snapshot(self) -> Dict[str, int]:
        with self._lock:
            counts: Dict[str, int] = {}
            for (bucket, _client), window in self._windows.items():
                counts[bucket] = counts.get(bucket, 0) + len(window.hits)
            return counts


# --------------------------------------------------------------------------- #
# client identity
# --------------------------------------------------------------------------- #


def parse_cidrs(values: Iterable[str]) -> List[ipaddress._BaseNetwork]:
    networks: List[ipaddress._BaseNetwork] = []
    for value in values:
        text = (value or "").strip()
        if not text:
            continue
        try:
            networks.append(ipaddress.ip_network(text, strict=False))
        except ValueError:
            continue
    return networks


def _addr(value: str) -> Optional[ipaddress._BaseAddress]:
    try:
        return ipaddress.ip_address(value.strip())
    except ValueError:
        return None


def _in_networks(address: ipaddress._BaseAddress, networks: List[ipaddress._BaseNetwork]) -> bool:
    return any(address.version == net.version and address in net for net in networks)


def client_ip(peer: Optional[str], forwarded_for: Optional[str], trusted: List[ipaddress._BaseNetwork]) -> str:
    """Resolve the effective client address without trusting forged headers."""
    peer_text = (peer or "").strip() or "unknown"
    peer_addr = _addr(peer_text)

    if peer_addr is None or not _in_networks(peer_addr, trusted):
        # Untrusted peer (or unknown): the header cannot be believed.
        return peer_text

    if not forwarded_for:
        return peer_text

    hops = [hop.strip() for hop in forwarded_for.split(",") if hop.strip()]
    for hop in reversed(hops):
        hop_addr = _addr(hop)
        if hop_addr is not None and not _in_networks(hop_addr, trusted):
            return str(hop_addr)
    # every hop is a trusted proxy: fall back to the outermost hop we saw
    return str(_addr(hops[0])) if hops and _addr(hops[0]) else peer_text


# --------------------------------------------------------------------------- #
# middleware
# --------------------------------------------------------------------------- #


class RateLimitMiddleware:
    """ASGI middleware: 429 with Retry-After when a bucket is exhausted.

    Written as a raw ASGI callable (not BaseHTTPMiddleware) so it does not buffer
    the streaming responses used by audio playback.
    """

    def __init__(self, app, limiter: RateLimiter, trusted: List[object]) -> None:
        self.app = app
        self.limiter = limiter
        self.trusted = trusted

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        method = scope.get("method", "GET").upper()
        bucket = bucket_for(method, path)
        if bucket is None:
            await self.app(scope, receive, send)
            return

        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        peer = scope["client"][0] if scope.get("client") else None
        address = client_ip(peer, headers.get("x-forwarded-for"), self.trusted)
        decision = self.limiter.check(bucket, address)

        if decision.allowed:
            await self.app(scope, receive, send)
            return

        body = json.dumps(
            {
                "error": {
                    "code": RATE_LIMIT_EXCEEDED,
                    "message": "Too many requests; please retry later",
                    "details": {
                        "bucket": bucket,
                        "limit": decision.limit,
                        "window_seconds": max(1, int(decision.reset_after)),
                    },
                }
            }
        ).encode()
        response_headers = [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode()),
            (b"retry-after", str(decision.retry_after).encode()),
            (b"x-ratelimit-limit", str(decision.limit).encode()),
            (b"x-ratelimit-remaining", b"0"),
        ]
        await send({"type": "http.response.start", "status": 429, "headers": response_headers})
        await send({"type": "http.response.body", "body": body})


# --------------------------------------------------------------------------- #
# bucket routing
# --------------------------------------------------------------------------- #

UPLOAD_PATHS = ("/api/v1/audio/upload", "/api/v1/transcription/upload")
TRANSCRIPTION_PATHS = ("/api/v1/transcription/jobs",)
WAVEFORM_SUFFIX = "/waveform"

EXEMPT_PATHS = frozenset({"/health", "/ready"})


def bucket_for(method: str, path: str) -> Optional[str]:
    """Pick the bucket for a request, or ``None`` when it is exempt."""
    if path in EXEMPT_PATHS:
        return None
    if method == "OPTIONS":
        return None  # preflight must never be throttled by business limits
    if method == "POST" and path in UPLOAD_PATHS:
        return BUCKET_UPLOAD
    if method == "POST" and path in TRANSCRIPTION_PATHS and not path.endswith("/run"):
        return BUCKET_TRANSCRIPTION
    if path.endswith(WAVEFORM_SUFFIX):
        return BUCKET_WAVEFORM
    return BUCKET_GENERAL

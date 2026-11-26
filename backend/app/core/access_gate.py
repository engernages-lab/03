"""Staging/production access gate (V1.1-C.2.2).

The backend has no user accounts yet (that is C.5), so exposing it publicly would
mean "anyone on the internet can use the AI and read every project". This module
puts a credential wall in front of *everything* except the container probes, and
it is enforced twice:

1. **Startup**: a staging/production process refuses to boot when the gate is off
   or its credentials are missing (``Settings.validate_hardened_secrets``).
2. **Runtime**: every non-probe request without valid credentials gets 401.

Two credential modes are supported:

* ``token`` - ``Authorization: Bearer <token>``, for scripts and the CI smoke test
* ``basic`` - HTTP Basic, for a human with curl or a browser tab

``off`` is only accepted outside staging/production. The gate is deliberately
*not* a substitute for real authentication: it is a single shared credential, it
does not isolate users, and it must be replaced by C.5.
"""

from __future__ import annotations

import base64
import binascii
import secrets
import threading
import time
from typing import Dict, Optional, Tuple

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.logging import get_logger

logger = get_logger(__name__)

# Container probes must stay reachable: Railway's healthcheck cannot send
# credentials, and a gated /health would make every deployment look unhealthy.
EXEMPT_PATHS = frozenset({"/health", "/ready"})

# Brute-force brake: after this many failures from one address inside the
# window, further attempts get 429 instead of another credential check.
MAX_FAILURES = 20
FAILURE_WINDOW_SECONDS = 60


class AccessGate:
    """Validates credentials and throttles repeated failures."""

    def __init__(self, mode: str, token: Optional[str], user: Optional[str], password: Optional[str]) -> None:
        self.mode = mode
        self._token = token or None
        self._user = user or None
        self._password = password or None
        self._lock = threading.Lock()
        self._failures: Dict[str, list[float]] = {}

    # -- configuration -----------------------------------------------------
    @property
    def enabled(self) -> bool:
        return self.mode in {"token", "basic"}

    @property
    def realm(self) -> str:
        return "PocketScore Staging"

    def describe(self) -> Dict[str, object]:
        """Non-secret description, safe for /ready and logs."""
        return {
            "mode": self.mode,
            "enabled": self.enabled,
            "token_configured": bool(self._token),
            "basic_configured": bool(self._user and self._password),
            "exempt_paths": sorted(EXEMPT_PATHS),
        }

    # -- credential checks -------------------------------------------------
    def check_bearer(self, header: str) -> bool:
        if not self._token or not header.lower().startswith("bearer "):
            return False
        return secrets.compare_digest(header[7:].strip(), self._token)

    def check_basic(self, header: str) -> bool:
        if not (self._user and self._password):
            return False
        if not header.lower().startswith("basic "):
            return False
        try:
            decoded = base64.b64decode(header[6:].strip(), validate=True).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError):
            return False
        username, _, password = decoded.partition(":")
        user_ok = secrets.compare_digest(username, self._user)
        password_ok = secrets.compare_digest(password, self._password)
        return user_ok and password_ok

    def authorize(self, header: Optional[str]) -> bool:
        if not self.enabled:
            return True
        if not header:
            return False
        if self.mode == "token":
            return self.check_bearer(header)
        return self.check_basic(header) or self.check_bearer(header)

    # -- throttling --------------------------------------------------------
    def register_failure(self, client: str) -> int:
        now = time.monotonic()
        with self._lock:
            timestamps = [value for value in self._failures.get(client, []) if now - value < FAILURE_WINDOW_SECONDS]
            timestamps.append(now)
            self._failures[client] = timestamps
            if len(self._failures) > 5_000:  # pragma: no cover - defensive cap
                self._failures.clear()
            return len(timestamps)

    def blocked(self, client: str) -> bool:
        now = time.monotonic()
        with self._lock:
            timestamps = [value for value in self._failures.get(client, []) if now - value < FAILURE_WINDOW_SECONDS]
            self._failures[client] = timestamps
            return len(timestamps) >= MAX_FAILURES

    def reset_failures(self) -> None:
        with self._lock:
            self._failures.clear()


class AccessGateMiddleware(BaseHTTPMiddleware):
    """Rejects unauthenticated requests with a project-style error envelope."""

    def __init__(self, app, gate: AccessGate) -> None:
        super().__init__(app)
        self.gate = gate

    async def dispatch(self, request: Request, call_next):
        if not self.gate.enabled:
            return await call_next(request)

        path = request.url.path
        if path in EXEMPT_PATHS or request.method == "OPTIONS":
            # OPTIONS must pass: CORS preflight never carries credentials.
            return await call_next(request)

        header = request.headers.get("authorization")
        if self.gate.authorize(header):
            return await call_next(request)

        client = request.client.host if request.client else "unknown"
        if self.gate.blocked(client):
            logger.warning("access gate: too many failed attempts from %s", client)
            return JSONResponse(
                {"error": {"code": "TOO_MANY_ATTEMPTS", "message": "尝试次数过多，请稍后再试"}},
                status_code=429,
            )

        attempts = self.gate.register_failure(client)
        logger.info(
            "access gate rejected %s %s from %s (attempt %d)",
            request.method,
            path,
            client,
            attempts,
        )
        return JSONResponse(
            {
                "error": {
                    "code": "ACCESS_GATE_REQUIRED",
                    "message": "需要访问凭据（该环境启用了 staging 访问保护）",
                    "details": {"mode": self.gate.mode, "realm": self.gate.realm},
                }
            },
            status_code=401,
            headers={"WWW-Authenticate": f'Basic realm="{self.gate.realm}"'},
        )


def build_gate(settings) -> AccessGate:
    """Resolve the configured mode and construct the gate.

    ``auto`` turns the gate on for staging/production and off elsewhere, so a
    developer checkout keeps working while a deployed staging process cannot
    start without credentials (see ``validate_hardened_secrets``).
    """
    mode = (settings.access_gate_mode or "auto").strip().lower()
    if mode == "auto":
        if settings.requires_hardened_secrets:
            if settings.access_gate_password and settings.access_gate_user:
                mode = "basic"
            elif settings.access_gate_token:
                mode = "token"
            else:
                mode = "off"  # validation will refuse to boot
        else:
            mode = "off"
    gate = AccessGate(
        mode=mode,
        token=settings.access_gate_token,
        user=settings.access_gate_user,
        password=settings.access_gate_password,
    )
    return gate


def gate_problems(settings) -> Tuple[list[str], AccessGate]:
    """Return configuration problems and the resolved gate (used at startup)."""
    gate = build_gate(settings)
    problems: list[str] = []
    if settings.requires_hardened_secrets:
        if gate.mode == "off":
            problems.append(
                "access gate is disabled: set POCKETSCORE_ACCESS_GATE_TOKEN (token mode) or "
                "POCKETSCORE_ACCESS_GATE_USER + POCKETSCORE_ACCESS_GATE_PASSWORD (basic mode)"
            )
        elif gate.mode == "token" and not gate.describe()["token_configured"]:
            problems.append("access gate mode=token but POCKETSCORE_ACCESS_GATE_TOKEN is empty")
        elif gate.mode == "basic" and not gate.describe()["basic_configured"]:
            problems.append(
                "access gate mode=basic but POCKETSCORE_ACCESS_GATE_USER/PASSWORD are not both set"
            )
    return problems, gate

"""Security response headers (V1.1-C.2.3.4.3).

Applied to every response, including errors and preflight, because a browser only
enforces them when they are present on the response it actually reads.

CSP is deliberately conservative but compatible with the built SPA: Vite emits
same-origin scripts, same-origin API calls and inline style attributes. HSTS is
opt-in (``POCKETSCORE_ENABLE_HSTS``) because this service may sit behind a proxy
whose TLS termination has not been confirmed; sending HSTS over plain HTTP is
ignored by browsers but sending it with the wrong includeSubDomains policy is
hard to undo.
"""

from __future__ import annotations

from typing import Callable, Dict, Iterable, Mapping, Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

BASE_HEADERS: Dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}

DEFAULT_CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; "
    "media-src 'self' blob:; "
    "font-src 'self' data:; "
    "connect-src 'self'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'none'"
)


def header_values(
    *,
    csp: Optional[str] = DEFAULT_CSP,
    hsts: bool = False,
    hsts_max_age: int = 31536000,
    extra: Optional[Mapping[str, str]] = None,
) -> Dict[str, str]:
    headers = dict(BASE_HEADERS)
    if csp:
        headers["Content-Security-Policy"] = csp
    if hsts:
        headers["Strict-Transport-Security"] = f"max-age={int(hsts_max_age)}"
    if extra:
        headers.update({str(k): str(v) for k, v in extra.items()})
    return headers


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach the configured headers to every outgoing response."""

    def __init__(
        self,
        app,
        headers: Optional[Mapping[str, str]] = None,
        *,
        csp: Optional[str] = DEFAULT_CSP,
        hsts: bool = False,
        hsts_max_age: int = 31536000,
    ) -> None:
        super().__init__(app)
        self._headers = dict(headers) if headers is not None else header_values(
            csp=csp, hsts=hsts, hsts_max_age=hsts_max_age
        )

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        for name, value in self._headers.items():
            # never overwrite a header the application already set deliberately
            if name not in response.headers:
                response.headers[name] = value
        return response


def headers_for_settings(settings) -> Dict[str, str]:
    """Build the header set from application settings."""
    return header_values(
        csp=getattr(settings, "content_security_policy", DEFAULT_CSP) or None,
        hsts=bool(getattr(settings, "enable_hsts", False)),
        hsts_max_age=int(getattr(settings, "hsts_max_age_seconds", 31536000)),
    )


def describe(headers: Iterable[str]) -> str:  # pragma: no cover - debug helper
    return ", ".join(sorted(headers))

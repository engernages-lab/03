"""Unified application error model.

Every failure surfaced by the API uses the same envelope::

    {
      "error": {
        "code": "MUSIC_DOCUMENT_NOT_FOUND",
        "message": "MusicDocument not found",
        "details": {...},
        "request_id": "..."
      }
    }

Domain code raises :class:`AppError` subclasses and never leaks stack traces
to clients.  Unhandled exceptions are converted to ``INTERNAL_ERROR`` and the
traceback is only written to the server log.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


class AppError(Exception):
    """Base class for all handled application errors."""

    status_code: int = 400
    code: str = "APP_ERROR"
    message: str = "Application error"

    def __init__(
        self,
        message: Optional[str] = None,
        *,
        code: Optional[str] = None,
        status_code: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.message = message or self.message
        self.code = code or self.code
        self.status_code = status_code or self.status_code
        self.details = details or {}
        super().__init__(self.message)

    def to_payload(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details:
            payload["details"] = self.details
        return payload


class BadRequestError(AppError):
    status_code = 400
    code = "BAD_REQUEST"
    message = "Invalid request"


class ValidationAppError(AppError):
    status_code = 422
    code = "VALIDATION_ERROR"
    message = "Validation failed"


class NotFoundError(AppError):
    status_code = 404
    code = "NOT_FOUND"
    message = "Resource not found"


class ConflictError(AppError):
    status_code = 409
    code = "CONFLICT"
    message = "Resource conflict"


class UnauthorizedError(AppError):
    status_code = 401
    code = "UNAUTHORIZED"
    message = "Authentication required"


class ForbiddenError(AppError):
    status_code = 403
    code = "FORBIDDEN"
    message = "Operation not permitted"


class PayloadTooLargeError(AppError):
    status_code = 413
    code = "PAYLOAD_TOO_LARGE"
    message = "Uploaded payload is too large"


class UnsupportedMediaError(AppError):
    status_code = 415
    code = "UNSUPPORTED_MEDIA_TYPE"
    message = "Unsupported media type"


class RateLimitedError(AppError):
    status_code = 429
    code = "RATE_LIMITED"
    message = "Too many requests"


class ProviderError(AppError):
    """A third-party music source misbehaved or rejected the request."""

    status_code = 502
    code = "PROVIDER_ERROR"
    message = "Music source provider error"


class ProviderUnavailableError(ProviderError):
    status_code = 503
    code = "PROVIDER_UNAVAILABLE"
    message = "Music source provider unavailable"


class ProviderAuthError(ProviderError):
    status_code = 401
    code = "PROVIDER_AUTH_FAILED"
    message = "Music source authentication failed"


class ProviderRestrictedError(AppError):
    """The provider's policy forbids the requested capability."""

    status_code = 403
    code = "PROVIDER_RESTRICTED"
    message = "This capability is restricted by the provider policy"


class DependencyMissingError(AppError):
    """An optional runtime dependency (ffmpeg, librosa, ...) is not installed."""

    status_code = 501
    code = "DEPENDENCY_MISSING"
    message = "Required optional dependency is not available"


class SSRFBlockedError(AppError):
    status_code = 400
    code = "SSRF_BLOCKED"
    message = "The requested address is not allowed"


class InternalError(AppError):
    status_code = 500
    code = "INTERNAL_ERROR"
    message = "Internal server error"


__all__ = [
    "AppError", "BadRequestError", "ValidationAppError", "NotFoundError",
    "ConflictError", "UnauthorizedError", "ForbiddenError", "PayloadTooLargeError",
    "UnsupportedMediaError", "RateLimitedError", "ProviderError",
    "ProviderUnavailableError", "ProviderAuthError", "ProviderRestrictedError",
    "DependencyMissingError", "SSRFBlockedError", "InternalError",
]

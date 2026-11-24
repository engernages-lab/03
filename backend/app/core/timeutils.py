"""UTC helpers for API payloads.

SQLite has no timezone support: ``DateTime(timezone=True)`` columns come back
naive even though every value written is UTC. Serialising those naive values
makes browsers interpret them as *local* time (an 8 hour error in UTC+8), so all
API timestamps go through :func:`utc_iso`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional


def as_utc(value: Optional[datetime]) -> Optional[datetime]:
    """Attach UTC to a naive value (SQLite) and normalise aware values."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def utc_iso(value: Optional[datetime]) -> Optional[str]:
    """ISO-8601 with an explicit ``Z`` suffix, e.g. ``2026-11-24T14:33:00Z``."""
    normalised = as_utc(value)
    if normalised is None:
        return None
    return normalised.isoformat().replace("+00:00", "Z")

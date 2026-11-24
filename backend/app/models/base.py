"""Shared ORM mixins and column helpers."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column


def utcnow() -> datetime:
    """Timezone-aware UTC now (SQLite stores naive, we normalise on read)."""
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, server_default=func.now(), nullable=False
    )


class IdMixin:
    """String UUID primary key (portable across SQLite/Postgres)."""

    id: Mapped[str] = mapped_column(String(36), primary_key=True)


__all__ = ["TimestampMixin", "IdMixin", "utcnow"]

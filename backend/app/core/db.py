"""Database engine, session management and declarative base.

SQLite is used as the V1.0-A storage backend.  The engine is created lazily so
that tests can point ``POCKETSCORE_DATABASE_URL`` at a temporary file or an
in-memory database without import side effects.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Generator, Iterator, List, Optional

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class Base(DeclarativeBase):
    """Declarative base shared by every ORM model."""


_engine: Optional[Engine] = None
_session_factory: Optional[sessionmaker] = None


def _make_engine() -> Engine:
    settings = get_settings()
    settings.ensure_directories()
    url = settings.database_url
    connect_args = {}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    engine = create_engine(url, connect_args=connect_args, future=True, pool_pre_ping=True)
    if url.startswith("sqlite"):
        # SQLite ignores FK constraints unless explicitly enabled per connection.
        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, _record):  # pragma: no cover - driver hook
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()
    return engine


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = _make_engine()
    return _engine


def get_session_factory() -> sessionmaker:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False, future=True)
    return _session_factory


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a scoped session."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional scope for background work and tests."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db() -> None:
    """Create all tables that do not exist yet and heal additive columns.

    Alembic owns schema evolution in production; ``create_all`` keeps a fresh
    developer checkout bootable without running migrations first. It does *not*
    alter existing tables, so an older database would break as soon as a model
    gains a column - :func:`sync_additive_columns` closes that gap safely.
    """
    from app import models  # noqa: F401  (import registers all mappers)

    Base.metadata.create_all(bind=get_engine())
    sync_additive_columns()


def sync_additive_columns() -> List[str]:
    """Add columns the models declared but the database is missing.

    Only *additive, nullable* columns without defaults are handled: nothing is
    dropped, renamed or retyped, so the operation is safe to run on every
    startup and cannot destroy data. Returns the added ``table.column`` names.
    """
    import sqlalchemy as sa

    from app import models  # noqa: F401

    engine = get_engine()
    inspector = sa.inspect(engine)
    added: List[str] = []
    with engine.begin() as connection:
        for table in Base.metadata.sorted_tables:
            if not inspector.has_table(table.name):
                continue
            existing = {column["name"] for column in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing:
                    continue
                if not column.nullable or column.server_default is not None:
                    # not safely addable without a migration
                    continue
                if column.primary_key or column.foreign_keys:
                    continue
                column_type = column.type.compile(dialect=engine.dialect)
                connection.execute(
                    sa.text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {column_type}')
                )
                added.append(f"{table.name}.{column.name}")
    if added:
        logger.info("schema healed (additive columns): %s", ", ".join(added))
    return added


def dispose_engine() -> None:
    """Drop cached engine/session factory (used by tests)."""
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None

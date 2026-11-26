"""Schema upgrade safety: an older database must keep working after a model change.

This is the regression test for the bug found while running the V1.1-B E2E suite:
``create_all`` never alters existing tables, so a database created before
``music_events.confidence`` existed made every document query fail with
``no such column``.
"""

from __future__ import annotations

import sqlite3

import pytest

from app.core import db as db_module


@pytest.fixture()
def old_database(tmp_path, monkeypatch):
    """A database whose music_events table predates the confidence column."""
    path = tmp_path / "old.db"
    connection = sqlite3.connect(path)
    connection.execute(
        """
        CREATE TABLE music_events (
            pk INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id VARCHAR(36) NOT NULL,
            event_id VARCHAR(48) NOT NULL,
            track_id VARCHAR(48) NOT NULL,
            pitch INTEGER,
            start_time FLOAT NOT NULL,
            duration FLOAT NOT NULL,
            velocity INTEGER NOT NULL DEFAULT 96,
            measure INTEGER NOT NULL DEFAULT 1,
            beat FLOAT NOT NULL DEFAULT 1.0,
            mapped_key VARCHAR(48),
            kind VARCHAR(8) NOT NULL DEFAULT 'note',
            chord_id VARCHAR(48),
            tie_group VARCHAR(48)
        )
        """
    )
    connection.commit()
    connection.close()

    monkeypatch.setattr(db_module, "_engine", None)
    monkeypatch.setattr(db_module, "_session_factory", None)
    monkeypatch.setenv("POCKETSCORE_DATABASE_URL", f"sqlite:///{path.as_posix()}")
    db_module.get_settings.cache_clear()
    yield path
    db_module.dispose_engine()
    db_module.get_settings.cache_clear()


def _columns(path) -> set[str]:
    connection = sqlite3.connect(path)
    try:
        return {row[1] for row in connection.execute("PRAGMA table_info(music_events)")}
    finally:
        connection.close()


def test_init_db_adds_missing_nullable_columns(old_database):
    assert "confidence" not in _columns(old_database)

    db_module.init_db()

    assert "confidence" in _columns(old_database)


def test_sync_additive_columns_is_idempotent(old_database):
    db_module.init_db()
    added = db_module.sync_additive_columns()
    assert added == []  # nothing left to add


def test_sync_never_drops_or_retypes_existing_columns(old_database):
    before = _columns(old_database)
    db_module.init_db()
    after = _columns(old_database)
    assert before.issubset(after)
    # the original column types are untouched
    connection = sqlite3.connect(old_database)
    try:
        types = {row[1]: row[2] for row in connection.execute("PRAGMA table_info(music_events)")}
    finally:
        connection.close()
    assert types["pitch"] == "INTEGER"
    assert types["duration"] == "FLOAT"
    assert types["tie_group"] == "VARCHAR(48)"

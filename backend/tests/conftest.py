"""Pytest configuration for the PocketScore AI backend.

Every test session runs against a throwaway SQLite database and a temporary
storage directory so tests never touch developer data.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

_TMP = Path(tempfile.mkdtemp(prefix="pocketscore-tests-"))
os.environ.setdefault("POCKETSCORE_ENVIRONMENT", "test")
os.environ.setdefault("POCKETSCORE_DATABASE_URL", f"sqlite:///{(_TMP / 'test.db').as_posix()}")
os.environ.setdefault("POCKETSCORE_STORAGE_DIR", str(_TMP / "storage"))
os.environ.setdefault("POCKETSCORE_LOG_LEVEL", "WARNING")


@pytest.fixture(scope="session")
def tmp_root() -> Path:
    return _TMP


@pytest.fixture(scope="session")
def app_module():
    from app.main import app

    return app


@pytest.fixture(scope="session")
def client(app_module):
    from fastapi.testclient import TestClient

    with TestClient(app_module) as c:
        yield c


@pytest.fixture()
def db_session():
    from app.core.db import get_session_factory, init_db

    init_db()
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.rollback()
        session.close()

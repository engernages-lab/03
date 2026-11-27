"""SPA bundle resolution and single-service hosting (V1.1-C.2.2.1).

The image copies the built bundle to /app/frontend/dist, but the process runs
with /app as the backend directory, so the historical PROJECT_ROOT/frontend/dist
lookup resolved to /frontend/dist and silently skipped mounting the SPA: the
container shipped a bundle nobody could load.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import BACKEND_DIR, PROJECT_ROOT, Settings


def _make_dist(root: Path) -> Path:
    dist = root / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>spa</title>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log('app')", encoding="utf-8")
    return dist


def test_explicit_directory_is_used_when_it_exists(tmp_path):
    dist = _make_dist(tmp_path)
    settings = Settings(frontend_dist_dir=str(dist))
    assert settings.frontend_dist_path == dist.resolve()


def test_explicit_directory_that_does_not_exist_is_ignored(tmp_path):
    settings = Settings(frontend_dist_dir=str(tmp_path / "missing"))
    assert settings.frontend_dist_path is None


def test_autodetect_falls_back_to_the_backend_directory(tmp_path, monkeypatch):
    """The container layout is <backend>/frontend/dist, not <project>/frontend/dist."""
    dist = _make_dist(tmp_path / "frontend")
    monkeypatch.setattr("app.core.config.BACKEND_DIR", tmp_path)
    monkeypatch.setattr("app.core.config.PROJECT_ROOT", tmp_path / "no-project-root")
    assert Settings().frontend_dist_path == dist


def test_no_bundle_anywhere_returns_none(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.BACKEND_DIR", tmp_path / "a")
    monkeypatch.setattr("app.core.config.PROJECT_ROOT", tmp_path / "b")
    assert Settings().frontend_dist_path is None


def test_repository_lookup_still_works():
    """Guards the normal developer layout: <repo>/frontend/dist."""
    settings = Settings()
    if (PROJECT_ROOT / "frontend" / "dist").is_dir() or (BACKEND_DIR / "frontend" / "dist").is_dir():
        assert settings.frontend_dist_path is not None
    else:  # pragma: no cover - clean checkout without a build
        assert settings.frontend_dist_path is None


def test_spa_is_served_when_a_bundle_is_configured(tmp_path):
    dist = _make_dist(tmp_path)
    app = FastAPI()

    @app.get("/api/v1/ping")
    def ping():  # noqa: D401
        return {"ok": True}

    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    app.mount("/assets", StaticFiles(directory=str(dist / "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):  # noqa: D401
        candidate = (dist / full_path).resolve()
        if full_path and dist in candidate.parents and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(dist / "index.html")

    client = TestClient(app)
    assert client.get("/").text.startswith("<!doctype html>")
    assert client.get("/projects/abc").text.startswith("<!doctype html>")
    assert client.get("/assets/app.js").text.startswith("console.log")
    assert client.get("/api/v1/ping").json() == {"ok": True}

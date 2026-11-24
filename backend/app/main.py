"""FastAPI application factory and middleware wiring."""

from __future__ import annotations

import time
import uuid
from typing import Callable

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import __version__
from app.api.v1.router import api_router
from app.core.config import PROJECT_ROOT, get_settings
from app.core.db import init_db
from app.core.errors import AppError, InternalError
from app.core.logging import configure_logging, get_logger, request_id_var

logger = get_logger("pocketscore.app")

REQUEST_ID_HEADER = "X-Request-ID"


def _error_response(exc: AppError, request_id: str) -> JSONResponse:
    payload = exc.to_payload()
    payload["request_id"] = request_id
    headers = {REQUEST_ID_HEADER: request_id}
    if exc.status_code == 401:
        headers["WWW-Authenticate"] = "Bearer"
    return JSONResponse(status_code=exc.status_code, content={"error": payload}, headers=headers)


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "PocketScore AI API - V1.0-A Foundation & Multi-Source Music Ecosystem. "
            "Unified music library, playback, AI-assisted transcription pipeline, "
            "custom pocket keyboard and dual notation (grid + jianpu) engines."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[REQUEST_ID_HEADER],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next: Callable) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except AppError as exc:  # raised inside a dependency/route outside handler scope
            response = _error_response(exc, request_id)
        finally:
            request_id_var.reset(token)
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        response.headers[REQUEST_ID_HEADER] = request_id
        logger.info(
            "%s %s -> %s (%.2fms)",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
            extra={"method": request.method, "path": request.url.path,
                   "status": response.status_code, "duration_ms": elapsed_ms},
        )
        return response

    @app.exception_handler(AppError)
    async def _app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
        rid = request_id_var.get() or "-"
        if exc.status_code >= 500:
            logger.error("AppError %s: %s", exc.code, exc.message, exc_info=exc)
        else:
            logger.warning("AppError %s: %s", exc.code, exc.message)
        return _error_response(exc, rid)

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
        rid = request_id_var.get() or "-"
        details = {"fields": []}
        for err in exc.errors():
            details["fields"].append(
                {
                    "loc": [str(p) for p in err.get("loc", ())],
                    "msg": err.get("msg", ""),
                    "type": err.get("type", ""),
                }
            )
        return _error_response(
            AppError("Request validation failed", code="VALIDATION_ERROR", status_code=422, details=details),
            rid,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_handler(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        rid = request_id_var.get() or "-"
        return _error_response(
            AppError(str(exc.detail), code=f"HTTP_{exc.status_code}", status_code=exc.status_code),
            rid,
        )

    @app.exception_handler(Exception)
    async def _unhandled_handler(_request: Request, exc: Exception) -> JSONResponse:  # pragma: no cover
        rid = request_id_var.get() or "-"
        logger.exception("Unhandled exception")
        return _error_response(InternalError(), rid)

    app.include_router(api_router, prefix=settings.api_v1_prefix)

    # Uploaded audio and extracted artwork are served read-only under /static so
    # the browser can stream them with Range requests.
    from fastapi.staticfiles import StaticFiles

    settings.ensure_directories()
    app.mount("/static", StaticFiles(directory=str(settings.storage_path)), name="static")

    # Optional: serve the built SPA from the same origin (single-service deploy).
    dist = PROJECT_ROOT / "frontend" / "dist"
    if settings.serve_frontend and dist.is_dir():
        from fastapi.responses import FileResponse

        assets = dist / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")
        index_file = dist / "index.html"

        @app.get("/{full_path:path}", include_in_schema=False)
        def spa(full_path: str):  # pragma: no cover - static hosting
            candidate = (dist / full_path).resolve()
            if full_path and dist in candidate.parents and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(index_file)

    @app.get("/", include_in_schema=False)
    def root() -> dict:
        return {
            "name": settings.app_name,
            "version": __version__,
            "stage": settings.release_stage,
            "docs": "/docs",
            "api": settings.api_v1_prefix,
        }

    @app.on_event("startup")
    def _startup() -> None:
        settings.ensure_directories()
        init_db()
        logger.info(
            "%s %s started (env=%s, db=%s)",
            settings.app_name, settings.app_version, settings.environment, settings.database_url,
        )

    return app


app = create_app()

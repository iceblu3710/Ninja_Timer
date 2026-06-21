"""Main FastAPI application for Dynasty Ninja Timer."""

import logging
import os
import sys
import threading
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import (
    routes_auth,
    routes_courses,
    routes_hardware,
    routes_leaderboards,
    routes_ops,
    routes_queue,
    routes_runs,
    routes_settings,
    routes_status,
    routes_timer,
    routes_ws,
)
from app.api.auth import AdminAuthError, admin_auth_exception_handler
from app.config import get_settings
from app.db.database import initialize_database
from app.logging_config import configure_logging
from app.services.hardware_service import get_hardware_service
from app.services.operations_service import recover_after_restart

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    configure_logging(debug=settings.debug)

    logger.info(f"Initializing {settings.app_name} v{settings.app_version}")
    _warn_if_insecure_defaults(settings)

    _ensure_data_directories()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Local-first timing system for Dynasty Ninja courses",
        debug=settings.debug,
    )
    app.add_exception_handler(AdminAuthError, admin_auth_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    # Middleware to enforce port separation on display/kiosk static files and pages
    @app.middleware("http")
    async def port_restriction_middleware(request: Request, call_next):
        path = request.url.path
        port = request.url.port
        settings = get_settings()

        if port == settings.scoreboard_port:
            if (
                path.startswith("/admin")
                or path.startswith("/kiosk")
                or "admin.html" in path
                or "kiosk.html" in path
            ):
                return JSONResponse(
                    status_code=403,
                    content={
                        "ok": False,
                        "error": {"code": "FORBIDDEN", "message": "Access denied on this port."},
                    },
                )
        elif port == settings.kiosk_port:
            if (
                path.startswith("/admin")
                or path.startswith("/display")
                or "admin.html" in path
                or "display.html" in path
            ):
                return JSONResponse(
                    status_code=403,
                    content={
                        "ok": False,
                        "error": {"code": "FORBIDDEN", "message": "Access denied on this port."},
                    },
                )

        return await call_next(request)

    _setup_static_files(app)

    app.include_router(routes_status.router)
    app.include_router(routes_auth.router)
    app.include_router(routes_timer.router)
    app.include_router(routes_courses.router)
    app.include_router(routes_hardware.router)
    app.include_router(routes_queue.router)
    app.include_router(routes_runs.router)
    app.include_router(routes_leaderboards.router)
    app.include_router(routes_settings.router)
    app.include_router(routes_ops.router)
    app.include_router(routes_ws.router)

    @app.get("/")
    async def get_root(request: Request):
        """Serve default view depending on port"""
        port = request.url.port
        settings = get_settings()
        if port == settings.scoreboard_port:
            return FileResponse("app/static/display.html")
        elif port == settings.kiosk_port:
            return FileResponse("app/static/kiosk.html")
        else:
            return FileResponse("app/static/admin.html")

    @app.get("/display")
    async def get_display(request: Request):
        """Serve display view"""
        port = request.url.port
        settings = get_settings()
        if port == settings.kiosk_port:
            raise HTTPException(status_code=403, detail="Access denied on this port.")
        return FileResponse("app/static/display.html")

    @app.get("/admin")
    async def get_admin(request: Request):
        """Serve admin view"""
        port = request.url.port
        settings = get_settings()
        if port in (settings.scoreboard_port, settings.kiosk_port):
            raise HTTPException(status_code=403, detail="Access denied on this port.")
        return FileResponse("app/static/admin.html")

    @app.get("/kiosk")
    async def get_kiosk(request: Request):
        """Serve kiosk view"""
        port = request.url.port
        settings = get_settings()
        if port == settings.scoreboard_port:
            raise HTTPException(status_code=403, detail="Access denied on this port.")
        return FileResponse("app/static/kiosk.html")

    @app.on_event("startup")
    async def startup_event():
        initialize_database(settings)
        get_hardware_service().reconnect()
        recovery = recover_after_restart()
        if recovery["recovered_queue_entries"]:
            logger.warning(
                "Recovered %s queue entries after restart",
                recovery["recovered_queue_entries"],
            )
        logger.info(f"App started on {settings.host}:{settings.port}")

        # Start auxiliary servers if not running unit tests
        if not ("pytest" in sys.modules or "PYTEST_CURRENT_TEST" in os.environ):
            _start_auxiliary_servers(app, settings)

    @app.on_event("shutdown")
    async def shutdown_event():
        logger.info("App shutting down")

    return app


def _ensure_data_directories() -> None:
    """Create required data directories if they don't exist."""
    dirs = [
        Path("data"),
        Path("data/backups"),
        Path("data/exports"),
        Path("data/logs"),
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Data directory ready: {d}")


def _setup_static_files(app: FastAPI) -> None:
    """Configure static file serving."""
    static_path = Path("app/static")
    static_path.mkdir(parents=True, exist_ok=True)

    if static_path.exists():
        app.mount("/static", StaticFiles(directory=str(static_path)), name="static")
        logger.info(f"Static files mounted from {static_path}")


def _start_auxiliary_servers(app: FastAPI, settings) -> None:
    """Start scoreboard and kiosk servers in background threads."""

    def run_server(port: int, name: str):
        logger.info(f"Starting auxiliary server '{name}' on port {port}")
        try:
            uvicorn.run(
                app,
                host=settings.host,
                port=port,
                log_level="warning",
                lifespan="off",
            )
        except Exception as e:
            logger.error(f"Error running auxiliary server '{name}' on port {port}: {e}")

    t_scoreboard = threading.Thread(
        target=run_server,
        args=(settings.scoreboard_port, "Scoreboard"),
        name="ScoreboardServer",
        daemon=True,
    )
    t_scoreboard.start()

    t_kiosk = threading.Thread(
        target=run_server,
        args=(settings.kiosk_port, "Kiosk"),
        name="KioskServer",
        daemon=True,
    )
    t_kiosk.start()


def _warn_if_insecure_defaults(settings) -> None:
    if str(getattr(settings, "admin_pin", "")) == "1234":
        logger.warning(
            "Default ADMIN_PIN is active. Set ADMIN_PIN or security.admin_pin before deployment."
        )
    if not getattr(settings, "admin_token_secret", None):
        logger.warning(
            "ADMIN_TOKEN_SECRET is not set. Admin session tokens are falling back to the PIN."
        )


async def http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, str) else "HTTP request failed."
    code = "FORBIDDEN" if exc.status_code == 403 else "HTTP_ERROR"
    return JSONResponse(
        status_code=exc.status_code,
        content={"ok": False, "error": {"code": code, "message": detail}},
        headers=getattr(exc, "headers", None),
    )


async def validation_exception_handler(
    _request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "ok": False,
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Request validation failed.",
                "details": jsonable_encoder(exc.errors()),
            },
        },
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled request error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "ok": False,
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected server error occurred.",
            },
        },
    )


app = create_app()

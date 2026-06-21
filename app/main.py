"""Main FastAPI application for Dynasty Ninja Timer"""
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import (
    routes_auth,
    routes_courses,
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
from app.services.operations_service import recover_after_restart

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application"""
    settings = get_settings()

    configure_logging(debug=settings.debug)

    logger.info(f"Initializing {settings.app_name} v{settings.app_version}")

    _ensure_data_directories()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Local-first timing system for Dynasty Ninja courses",
        debug=settings.debug,
    )
    app.add_exception_handler(AdminAuthError, admin_auth_exception_handler)

    _setup_static_files(app)

    app.include_router(routes_status.router)
    app.include_router(routes_auth.router)
    app.include_router(routes_timer.router)
    app.include_router(routes_courses.router)
    app.include_router(routes_queue.router)
    app.include_router(routes_runs.router)
    app.include_router(routes_leaderboards.router)
    app.include_router(routes_settings.router)
    app.include_router(routes_ops.router)
    app.include_router(routes_ws.router)

    @app.get("/")
    async def get_root():
        """Serve default display view"""
        return FileResponse("app/static/index.html")

    @app.get("/display")
    async def get_display():
        """Serve display view"""
        return FileResponse("app/static/index.html")

    @app.get("/admin")
    async def get_admin():
        """Serve admin view"""
        return FileResponse("app/static/index.html")

    @app.get("/kiosk")
    async def get_kiosk():
        """Serve kiosk view"""
        return FileResponse("app/static/index.html")

    @app.on_event("startup")
    async def startup_event():
        initialize_database(settings)
        recovery = recover_after_restart()
        if recovery["recovered_queue_entries"]:
            logger.warning(
                "Recovered %s queue entries after restart",
                recovery["recovered_queue_entries"],
            )
        logger.info(f"App started on {settings.host}:{settings.port}")

    @app.on_event("shutdown")
    async def shutdown_event():
        logger.info("App shutting down")

    return app


def _ensure_data_directories() -> None:
    """Create required data directories if they don't exist"""
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
    """Configure static file serving"""
    static_path = Path("app/static")
    static_path.mkdir(parents=True, exist_ok=True)

    if static_path.exists():
        app.mount("/static", StaticFiles(directory=str(static_path)), name="static")
        logger.info(f"Static files mounted from {static_path}")


app = create_app()

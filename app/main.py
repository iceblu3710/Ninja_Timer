"""Main FastAPI application for Dynasty Ninja Timer"""
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.config import get_settings
from app.logging_config import configure_logging
from app.api import routes_status

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
    
    _setup_static_files(app)
    
    app.include_router(routes_status.router)
    
    @app.get("/")
    async def root_redirect():
        """Redirect root to display"""
        return FileResponse("app/static/display.html")
    
    @app.get("/display")
    async def get_display():
        """Serve display view"""
        return FileResponse("app/static/display.html")
    
    @app.get("/admin")
    async def get_admin():
        """Serve admin view"""
        return FileResponse("app/static/admin.html")
    
    @app.get("/kiosk")
    async def get_kiosk():
        """Serve kiosk view"""
        return FileResponse("app/static/kiosk.html")
    
    @app.on_event("startup")
    async def startup_event():
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

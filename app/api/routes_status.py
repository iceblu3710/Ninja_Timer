"""Status API routes"""
from fastapi import APIRouter

from app.config import get_settings

router = APIRouter(prefix="/api/v1", tags=["status"])


@router.get("/status")
async def get_status() -> dict:
    """Get application status including app, config, database, and hardware status"""
    settings = get_settings()

    return {
        "app": {
            "name": settings.app_name,
            "version": settings.app_version,
            "status": "running",
        },
        "config": settings.to_dict(),
        "database": {
            "status": "initialized",
            "type": "sqlite",
            "path": settings.database_url,
        },
        "hardware": {
            "status": "ready",
            "driver": settings.hardware_driver,
        },
    }

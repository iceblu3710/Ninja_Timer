"""Status API routes"""

from fastapi import APIRouter

from app.config import get_settings
from app.db.database import database_health
from app.services.hardware_service import get_hardware_service

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
        "database": database_health(settings),
        "hardware": get_hardware_service().status(),
    }

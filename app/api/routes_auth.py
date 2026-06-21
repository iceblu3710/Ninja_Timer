"""Admin authentication routes."""
from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from app.api.auth import create_admin_token, verify_admin_pin
from app.config import Settings, get_settings
from app.db.schemas import AdminLoginRequest

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/login")
async def admin_login(
    payload: AdminLoginRequest,
    settings: Settings = Depends(get_settings),
):
    if not verify_admin_pin(payload.pin, settings):
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={
                "ok": False,
                "error": {
                    "code": "INVALID_ADMIN_PIN",
                    "message": "Admin PIN is incorrect.",
                },
            },
        )
    return {
        "ok": True,
        "data": {
            "token": create_admin_token(settings),
            "expires_in_seconds": settings.admin_session_seconds,
        },
    }

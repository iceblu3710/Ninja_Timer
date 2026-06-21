"""Admin authentication routes."""

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse

from app.api.auth import (
    clear_failed_logins,
    create_admin_token,
    is_login_rate_limited,
    login_client_key,
    record_failed_login,
    verify_admin_pin,
)
from app.config import Settings, get_settings
from app.db.schemas import AdminLoginRequest

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/login")
async def admin_login(
    payload: AdminLoginRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
):
    client_key = login_client_key(request)
    if is_login_rate_limited(client_key):
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={
                "ok": False,
                "error": {
                    "code": "ADMIN_LOGIN_RATE_LIMITED",
                    "message": "Too many failed admin PIN attempts. Try again shortly.",
                },
            },
        )
    if not verify_admin_pin(payload.pin, settings):
        record_failed_login(client_key)
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
    clear_failed_logins(client_key)
    return {
        "ok": True,
        "data": {
            "token": create_admin_token(settings),
            "expires_in_seconds": settings.admin_session_seconds,
        },
    }

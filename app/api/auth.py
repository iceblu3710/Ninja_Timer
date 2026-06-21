"""Simple local admin PIN authentication for V1 gym deployments."""
import base64
import hashlib
import hmac
import time

from fastapi import Depends, Header, Request, status
from fastapi.responses import JSONResponse

from app.config import Settings, get_settings


class AdminAuthError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def create_admin_token(settings: Settings | None = None) -> str:
    active_settings = settings or get_settings()
    issued_at = str(int(time.time()))
    signature = _sign(issued_at, active_settings)
    raw = f"{issued_at}:{signature}".encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def verify_admin_pin(pin: str, settings: Settings | None = None) -> bool:
    active_settings = settings or get_settings()
    return hmac.compare_digest(str(pin), str(active_settings.admin_pin))


def require_admin(
    authorization: str | None = Header(default=None),
    x_admin_token: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> str:
    token = x_admin_token or _bearer_token(authorization)
    if token is None:
        _auth_error("ADMIN_AUTH_REQUIRED", "An admin session token is required.")
    try:
        _verify_admin_token(token, settings)
    except AdminAuthError as exc:
        _auth_error("ADMIN_AUTH_INVALID", exc.message)
    return "ADMIN"


async def admin_auth_exception_handler(_request: Request, exc: AdminAuthError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"ok": False, "error": {"code": exc.code, "message": exc.message}},
    )


def _bearer_token(authorization: str | None) -> str | None:
    if authorization is None:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token


def _verify_admin_token(token: str, settings: Settings) -> None:
    try:
        raw = base64.urlsafe_b64decode(token.encode("ascii")).decode("utf-8")
        issued_at, signature = raw.split(":", 1)
        issued_at_int = int(issued_at)
    except Exception as exc:
        raise AdminAuthError(
            "ADMIN_AUTH_MALFORMED",
            "Admin session token is malformed.",
        ) from exc

    expected = _sign(issued_at, settings)
    if not hmac.compare_digest(signature, expected):
        raise AdminAuthError(
            "ADMIN_AUTH_INVALID_SIGNATURE",
            "Admin session token signature is invalid.",
        )
    if issued_at_int + settings.admin_session_seconds < int(time.time()):
        raise AdminAuthError("ADMIN_AUTH_EXPIRED", "Admin session token has expired.")


def _sign(issued_at: str, settings: Settings) -> str:
    key = str(settings.admin_pin).encode("utf-8")
    message = f"{issued_at}:{settings.app_version}".encode("utf-8")
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def _auth_error(code: str, message: str) -> None:
    raise AdminAuthError(code, message)

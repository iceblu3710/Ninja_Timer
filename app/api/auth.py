"""Simple local admin PIN authentication for V1 gym deployments."""

import base64
import hashlib
import hmac
import time
from collections import deque

from fastapi import Depends, Header, Request, status
from fastapi.responses import JSONResponse

from app.config import Settings, get_settings

MAX_LOGIN_ATTEMPTS = 5
LOGIN_ATTEMPT_WINDOW_SECONDS = 60
MAX_TRACKED_LOGIN_CLIENTS = 1024
_login_failures: dict[str, deque[float]] = {}


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
    token_secret = getattr(settings, "admin_token_secret", None)
    key = str(token_secret or settings.admin_pin).encode("utf-8")
    message = f"{issued_at}:{settings.app_version}".encode("utf-8")
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def _auth_error(code: str, message: str) -> None:
    raise AdminAuthError(code, message)


def login_client_key(request: Request) -> str:
    """Return the best available key for local login throttling."""
    if request.client is None:
        return "unknown"
    return request.client.host or "unknown"


def is_login_rate_limited(client_key: str, now: float | None = None) -> bool:
    """Return True when a client has too many recent failed PIN attempts."""
    active_now = now if now is not None else time.monotonic()
    attempts = _login_failures.get(client_key)
    if attempts is None:
        return False
    _prune_attempts(attempts, active_now)
    return len(attempts) >= MAX_LOGIN_ATTEMPTS


def record_failed_login(client_key: str, now: float | None = None) -> None:
    """Track a failed local admin login attempt with bounded memory use."""
    active_now = now if now is not None else time.monotonic()
    if len(_login_failures) >= MAX_TRACKED_LOGIN_CLIENTS and client_key not in _login_failures:
        _prune_login_clients(active_now)
    attempts = _login_failures.setdefault(client_key, deque())
    _prune_attempts(attempts, active_now)
    attempts.append(active_now)


def clear_failed_logins(client_key: str) -> None:
    _login_failures.pop(client_key, None)


def reset_login_rate_limits_for_tests() -> None:
    _login_failures.clear()


def _prune_attempts(attempts: deque[float], now: float) -> None:
    cutoff = now - LOGIN_ATTEMPT_WINDOW_SECONDS
    while attempts and attempts[0] < cutoff:
        attempts.popleft()


def _prune_login_clients(now: float) -> None:
    stale_keys: list[str] = []
    for key, attempts in _login_failures.items():
        _prune_attempts(attempts, now)
        if not attempts:
            stale_keys.append(key)
    for key in stale_keys:
        _login_failures.pop(key, None)
    if len(_login_failures) >= MAX_TRACKED_LOGIN_CLIENTS:
        oldest_key = min(
            _login_failures,
            key=lambda item: _login_failures[item][0] if _login_failures[item] else now,
        )
        _login_failures.pop(oldest_key, None)

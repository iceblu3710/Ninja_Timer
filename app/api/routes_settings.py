"""Settings API routes."""

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.auth import require_admin
from app.db.database import get_db
from app.db.schemas import (
    SettingRollbackRequest,
    SettingsPatchRequest,
    SettingsValidateRequest,
)
from app.services.event_bus import event_bus
from app.services.settings_service import (
    SettingsConflictError,
    SettingsValidationError,
    apply_settings,
    list_settings,
    rollback_setting,
    validate_changes,
)

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])


def _ok(data: object) -> dict:
    return {"ok": True, "data": data}


def _error(http_status: int, code: str, message: str, extra: object = None) -> JSONResponse:
    payload: dict[str, object] = {"ok": False, "error": {"code": code, "message": message}}
    if extra is not None:
        payload["error"]["details"] = extra  # type: ignore[index]
    return JSONResponse(status_code=http_status, content=payload)


@router.get("")
async def get_settings(db: Session = Depends(get_db)) -> dict:
    return _ok(list_settings(db))


@router.post("/validate")
async def validate_settings(payload: SettingsValidateRequest) -> dict:
    return _ok(validate_changes(payload.changes))


@router.patch("")
async def patch_settings(
    payload: SettingsPatchRequest,
    db: Session = Depends(get_db),
    actor: str = Depends(require_admin),
):
    if not payload.apply_immediately:
        return _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "DEFERRED_APPLY_UNSUPPORTED",
            "Deferred settings apply is not supported in V1.",
        )
    try:
        changed = apply_settings(
            db,
            changes=payload.changes,
            request_id=payload.request_id,
            actor=actor,
        )
    except SettingsConflictError as exc:
        db.rollback()
        return _error(status.HTTP_409_CONFLICT, "STALE_VERSION", str(exc))
    except SettingsValidationError as exc:
        db.commit()
        return _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "INVALID_SETTINGS",
            str(exc),
            exc.errors,
        )

    db.commit()
    await event_bus.publish("settings.updated", {"settings": changed})
    return _ok(changed)


@router.post("/{key}/rollback")
async def rollback_settings_key(
    key: str,
    payload: SettingRollbackRequest,
    db: Session = Depends(get_db),
    actor: str = Depends(require_admin),
):
    try:
        setting = rollback_setting(
            db,
            key=key,
            request_id=payload.request_id,
            reason=payload.reason,
            actor=actor,
        )
    except KeyError:
        db.rollback()
        return _error(status.HTTP_404_NOT_FOUND, "NOT_FOUND", f"Setting {key} was not found.")
    except ValueError as exc:
        db.rollback()
        return _error(status.HTTP_409_CONFLICT, "ROLLBACK_UNAVAILABLE", str(exc))

    db.commit()
    await event_bus.publish("settings.updated", {"settings": {key: setting}})
    return _ok(setting)

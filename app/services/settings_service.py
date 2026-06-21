"""Validated settings workflows for local operations."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from app.db.models import Setting
from app.db.repositories import (
    AuditRepository,
    SettingsRepository,
    SystemEventRepository,
)
from app.db.schemas import SettingChange


class SettingsConflictError(ValueError):
    pass


class SettingsValidationError(ValueError):
    def __init__(self, errors: list[dict[str, str]]):
        super().__init__("One or more settings failed validation.")
        self.errors = errors


@dataclass(frozen=True)
class SettingDefinition:
    default: Any
    value_type: str


SETTING_DEFINITIONS: dict[str, SettingDefinition] = {
    "system.site_name": SettingDefinition("Dynasty Ninja Training Center", "string"),
    "system.timezone": SettingDefinition("America/Regina", "string"),
    "timer.default_mode": SettingDefinition("OPEN_GYM", "string"),
    "timer.countdown_seconds": SettingDefinition(3, "integer"),
    "leaderboard.default_course_revision_mode": SettingDefinition(
        "CURRENT_REVISION_ONLY",
        "string",
    ),
    "hardware.active_transport": SettingDefinition("SIMULATED", "string"),
    "hardware.mqtt_host": SettingDefinition("", "string"),
}


def seed_default_settings(db: Session) -> list[Setting]:
    repository = SettingsRepository(db)
    settings: list[Setting] = []
    for key, definition in SETTING_DEFINITIONS.items():
        settings.append(
            repository.upsert_default(
                key,
                _to_json(definition.default),
                value_type=definition.value_type,
            )
        )
    return settings


def list_settings(db: Session) -> dict[str, dict[str, Any]]:
    return {setting.key: setting_response(setting) for setting in SettingsRepository(db).list_all()}


def validate_changes(changes: dict[str, SettingChange]) -> dict[str, Any]:
    errors = _validate_changes(changes)
    return {"valid": not errors, "errors": errors}


def apply_settings(
    db: Session,
    *,
    changes: dict[str, SettingChange],
    request_id: str | None,
    actor: str,
) -> dict[str, dict[str, Any]]:
    repository = SettingsRepository(db)
    _ensure_known_settings(db)
    _raise_on_stale_versions(repository, changes)

    errors = _validate_changes(changes)
    if errors:
        _store_invalid_attempts(db, changes, errors, actor=actor, request_id=request_id)
        raise SettingsValidationError(errors)

    changed: dict[str, dict[str, Any]] = {}
    for key, change in changes.items():
        setting = repository.get(key)
        if setting is None:
            definition = SETTING_DEFINITIONS[key]
            setting = repository.upsert_default(
                key,
                _to_json(definition.default),
                value_type=definition.value_type,
            )
        repository.update_value(
            setting,
            value_json=_to_json(change.value),
            value_type=SETTING_DEFINITIONS[key].value_type,
            updated_by=actor,
        )
        changed[key] = setting_response(setting)

    AuditRepository(db).record(
        actor=actor,
        action="UPDATE_SETTINGS",
        target_type="settings",
        request_id=request_id,
        payload_json=_to_json({"keys": sorted(changes.keys())}),
    )
    return changed


def rollback_setting(
    db: Session,
    *,
    key: str,
    request_id: str | None,
    reason: str | None,
    actor: str,
) -> dict[str, Any]:
    repository = SettingsRepository(db)
    setting = repository.get(key)
    if setting is None:
        raise KeyError(key)
    repository.rollback(setting, updated_by=actor)
    AuditRepository(db).record(
        actor=actor,
        action="ROLLBACK_SETTING",
        target_type="settings",
        request_id=request_id,
        payload_json=_to_json({"key": key, "reason": reason}),
    )
    return setting_response(setting)


def setting_response(setting: Setting) -> dict[str, Any]:
    return {
        "value": _from_json(setting.value_json),
        "version": setting.version,
        "validation_status": setting.validation_status,
        "validation_error": setting.validation_error,
        "pending_value": (
            _from_json(setting.pending_value_json)
            if setting.pending_value_json is not None
            else None
        ),
        "updated_at": setting.updated_at,
        "updated_by": setting.updated_by,
    }


def _ensure_known_settings(db: Session) -> None:
    seed_default_settings(db)


def _raise_on_stale_versions(
    repository: SettingsRepository,
    changes: dict[str, SettingChange],
) -> None:
    for key, change in changes.items():
        setting = repository.get(key)
        if setting is None or change.version is None:
            continue
        if setting.version != change.version:
            raise SettingsConflictError(f"Setting {key} version is stale.")


def _validate_changes(changes: dict[str, SettingChange]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    for key, change in changes.items():
        if key not in SETTING_DEFINITIONS:
            errors.append(_error(key, "UNKNOWN_SETTING", "Setting key is not editable."))
            continue
        message = _validation_error(key, change.value)
        if message is not None:
            errors.append(_error(key, "INVALID_VALUE", message))
    return errors


def _validation_error(key: str, value: Any) -> str | None:
    if key == "system.site_name":
        return _validate_string(value, max_length=120)
    if key == "system.timezone":
        if not isinstance(value, str):
            return "Value must be a string."
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError:
            return "Value must be a valid IANA timezone."
        return None
    if key == "timer.default_mode":
        return _validate_enum(value, {"OPEN_GYM", "PARTY", "COMPETITION"})
    if key == "timer.countdown_seconds":
        if not isinstance(value, int) or isinstance(value, bool):
            return "Value must be an integer."
        if value < 0 or value > 10:
            return "Value must be between 0 and 10 seconds."
        return None
    if key == "leaderboard.default_course_revision_mode":
        return _validate_enum(value, {"CURRENT_REVISION_ONLY", "ALL_REVISIONS"})
    if key == "hardware.active_transport":
        return _validate_enum(value, {"SIMULATED", "USB_SERIAL", "MQTT", "M5STAMP_WIFI"})
    if key == "hardware.mqtt_host":
        return _validate_string(value, max_length=255, allow_empty=True)
    return None


def _store_invalid_attempts(
    db: Session,
    changes: dict[str, SettingChange],
    errors: list[dict[str, str]],
    *,
    actor: str,
    request_id: str | None,
) -> None:
    repository = SettingsRepository(db)
    event_repository = SystemEventRepository(db)
    errors_by_key = {error["key"]: error for error in errors}
    for key, error in errors_by_key.items():
        if key not in SETTING_DEFINITIONS:
            continue
        setting = repository.get(key)
        if setting is None:
            definition = SETTING_DEFINITIONS[key]
            setting = repository.upsert_default(
                key,
                _to_json(definition.default),
                value_type=definition.value_type,
            )
        repository.store_invalid_pending(
            setting,
            pending_value_json=_to_json(changes[key].value),
            validation_error=error["message"],
            updated_by=actor,
        )
        event_repository.record(
            level="ERROR",
            category="CONFIG",
            source="settings",
            message=f"Invalid setting update rejected for {key}.",
            payload_json=_to_json(error),
            request_id=request_id,
        )


def _validate_string(value: Any, *, max_length: int, allow_empty: bool = False) -> str | None:
    if not isinstance(value, str):
        return "Value must be a string."
    if not allow_empty and not value.strip():
        return "Value cannot be empty."
    if len(value) > max_length:
        return f"Value must be {max_length} characters or fewer."
    return None


def _validate_enum(value: Any, allowed: set[str]) -> str | None:
    if value not in allowed:
        return f"Value must be one of: {', '.join(sorted(allowed))}."
    return None


def _error(key: str, code: str, message: str) -> dict[str, str]:
    return {"key": key, "code": code, "message": message}


def _to_json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def _from_json(value_json: str) -> Any:
    return json.loads(value_json)

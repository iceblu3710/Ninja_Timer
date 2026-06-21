"""Relay command persistence and dispatch."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from app.db.models import RelayAction
from app.db.repositories import HardwareRepository, RelayRepository
from app.hardware.arduino_protocol import format_relay_command
from app.services.event_bus import event_bus
from app.services.hardware_service import get_hardware_service

ACTION_DEFAULTS = {
    "HORN_PULSE": ("HORN", "PULSE", 200),
    "GREEN_ON": ("GREEN", "ON", None),
    "GREEN_OFF": ("GREEN", "OFF", None),
    "RED_ON": ("RED", "ON", None),
    "RED_OFF": ("RED", "OFF", None),
    "ALL_OFF": ("ALL", "OFF", None),
    "FINISH_CHIME": ("CHIME", "PULSE", 200),
    "SMOKE_BURST": ("SMOKE", "PULSE", 500),
    "CROWD_CHEER": ("CROWD", "PULSE", 1000),
}


class RelayService:
    def dispatch(
        self,
        db: Session,
        *,
        action_key: str,
        command: str | None = None,
        target: str | None = None,
        action: str | None = None,
        duration_ms: int | None = None,
        requested_by: str = "ADMIN",
        run_id: int | None = None,
    ) -> RelayAction:
        action_key = action_key.upper()
        command_text = command or self._command_from_parts(action_key, target, action, duration_ms)
        device = self._preferred_device(db)
        repository = RelayRepository(db)
        relay_action = repository.create(
            action_id=str(uuid4()),
            device_id=device.id if device is not None else None,
            action_key=action_key,
            command=command_text,
            requested_by=requested_by,
            run_id=run_id,
        )

        try:
            raw_response = get_hardware_service().transport.send_command(command_text)
            repository.mark_sent(
                relay_action,
                raw_response=raw_response,
                acknowledged=raw_response is not None and "ACK" in raw_response.upper(),
            )
        except Exception as exc:
            repository.mark_failed(relay_action, str(exc))
        return relay_action

    def _command_from_parts(
        self,
        action_key: str,
        target: str | None,
        action: str | None,
        duration_ms: int | None,
    ) -> str:
        if target is None or action is None:
            default = ACTION_DEFAULTS.get(action_key)
            if default is None:
                raise ValueError("command or target/action is required")
            target, action, default_duration = default
            duration_ms = duration_ms if duration_ms is not None else default_duration
        return format_relay_command(target, action, duration_ms)

    def _preferred_device(self, db: Session):
        devices = HardwareRepository(db).list_devices()
        return devices[0] if devices else None


async def publish_relay_action(action: RelayAction) -> None:
    await event_bus.publish("hardware.status", {"relay_action": relay_action_response(action)})


def relay_action_response(action: RelayAction) -> dict[str, Any]:
    return {
        "id": action.id,
        "action_id": action.action_id,
        "device_id": action.device_id,
        "action_key": action.action_key,
        "command": action.command,
        "requested_by": action.requested_by,
        "run_id": action.run_id,
        "status": action.status,
        "requested_at": action.requested_at,
        "sent_at": action.sent_at,
        "acknowledged_at": action.acknowledged_at,
        "raw_response": action.raw_response,
        "error": action.error,
    }


relay_service = RelayService()


def get_relay_service() -> RelayService:
    return relay_service

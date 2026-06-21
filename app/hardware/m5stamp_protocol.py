"""M5Stamp HTTP/MQTT payload normalization helpers."""

from __future__ import annotations

from typing import Any

from app.hardware.hardware_models import NormalizedHardwareEvent


def parse_m5stamp_payload(payload: dict[str, Any]) -> NormalizedHardwareEvent:
    event_type = str(payload.get("type") or payload.get("event") or "EVT").upper()
    input_key = payload.get("input") or payload.get("device")
    state = payload.get("state")
    device_id = str(payload.get("device_id") or payload.get("id") or "m5stamp-controller")
    sequence_number = payload.get("seq")
    try:
        sequence_number = int(sequence_number) if sequence_number is not None else None
    except (TypeError, ValueError):
        sequence_number = None

    return NormalizedHardwareEvent(
        transport="M5STAMP",
        event_type=event_type,
        input_key=str(input_key).upper() if input_key is not None else None,
        state=str(state).upper() if state is not None else None,
        sequence_number=sequence_number,
        raw_payload=str(payload),
        device_key=device_id,
        display_name=f"M5Stamp {device_id}",
        device_type="INPUT" if input_key is not None else "CONTROLLER",
        parsed=dict(payload),
    )

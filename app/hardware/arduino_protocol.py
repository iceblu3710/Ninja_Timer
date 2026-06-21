"""Arduino serial line parsing and command formatting."""

from __future__ import annotations

from app.hardware.hardware_models import NormalizedHardwareEvent

VALID_RELAY_TARGETS = {"HORN", "GREEN", "RED", "ALL", "SMOKE", "CHIME", "CROWD"}
VALID_RELAY_ACTIONS = {"ON", "OFF", "PULSE"}


def parse_arduino_line(line: str) -> NormalizedHardwareEvent:
    raw = line.strip()
    if not raw:
        raise ValueError("Empty Arduino line.")

    parts = [part.strip() for part in raw.split(",")]
    message_type = parts[0].upper()

    if message_type == "READY" and len(parts) == 1:
        return NormalizedHardwareEvent(
            transport="ARDUINO",
            event_type="READY",
            raw_payload=raw,
            device_key="arduino-controller",
            display_name="Arduino Controller",
            parsed={"message": "READY"},
        )

    if message_type == "HEARTBEAT" and len(parts) == 2:
        sequence_number = _parse_int(parts[1])
        return NormalizedHardwareEvent(
            transport="ARDUINO",
            event_type="HEARTBEAT",
            raw_payload=raw,
            device_key="arduino-controller",
            display_name="Arduino Controller",
            sequence_number=sequence_number,
            parsed={"heartbeat": parts[1]},
        )

    if message_type == "EVT" and len(parts) in (3, 4):
        sequence_number = _parse_int(parts[3]) if len(parts) == 4 else None
        return NormalizedHardwareEvent(
            transport="ARDUINO",
            event_type="EVT",
            input_key=parts[1].upper(),
            state=parts[2].upper(),
            sequence_number=sequence_number,
            raw_payload=raw,
            device_key=f"arduino-{parts[1].lower()}",
            display_name=f"Arduino {parts[1].title()}",
            device_type="INPUT",
            parsed={"parts": parts},
        )

    raise ValueError(f"Unsupported Arduino message: {raw}")


def format_relay_command(target: str, action: str, duration_ms: int | None = None) -> str:
    target = target.upper()
    action = action.upper()
    if target not in VALID_RELAY_TARGETS:
        raise ValueError(f"Unsupported relay target: {target}")
    if action not in VALID_RELAY_ACTIONS:
        raise ValueError(f"Unsupported relay action: {action}")
    if action == "PULSE":
        duration = int(duration_ms if duration_ms is not None else 200)
        return f"CMD,{target},PULSE,{max(1, duration)}"
    return f"CMD,{target},{action}"


def _parse_int(value: str) -> int | None:
    try:
        return int(value)
    except ValueError:
        return None

"""In-process hardware transport for tests and gym dry-runs."""

from __future__ import annotations

from typing import Any

from app.hardware.hardware_models import NormalizedHardwareEvent
from app.hardware.transport_base import HardwareTransport


class SimulatedTransport(HardwareTransport):
    name = "SIMULATED"

    def __init__(self) -> None:
        self.connected = True
        self.command_log: list[str] = []
        self.sequence_number = 0

    def reconnect(self) -> None:
        self.connected = True

    def close(self) -> None:
        self.connected = False

    def send_command(self, command: str) -> str:
        self.command_log.append(command)
        return "SIMULATED_ACK"

    def status(self) -> dict[str, Any]:
        return {
            "transport": self.name,
            "connected": self.connected,
            "last_command": self.command_log[-1] if self.command_log else None,
            "command_count": len(self.command_log),
        }

    def make_event(self, input_key: str, state: str = "DOWN") -> NormalizedHardwareEvent:
        self.sequence_number += 1
        input_key = input_key.upper()
        state = state.upper()
        return NormalizedHardwareEvent(
            transport=self.name,
            event_type="EVT",
            input_key=input_key,
            state=state,
            device_key="simulated-controller",
            display_name="Simulated Controller",
            sequence_number=self.sequence_number,
            raw_payload=f"EVT,{input_key},{state}",
            parsed={"source": "simulate"},
        )

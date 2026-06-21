"""Normalized hardware DTOs used by transports and services."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class NormalizedHardwareEvent:
    transport: str
    event_type: str
    raw_payload: str
    input_key: str | None = None
    state: str | None = None
    device_key: str | None = None
    display_name: str | None = None
    device_type: str = "CONTROLLER"
    sequence_number: int | None = None
    parsed: dict[str, Any] = field(default_factory=dict)

    def normalized_input(self) -> tuple[str | None, str | None]:
        return (
            self.input_key.upper() if self.input_key is not None else None,
            self.state.upper() if self.state is not None else None,
        )


@dataclass(frozen=True)
class RelayCommand:
    action_key: str
    command: str
    requested_by: str = "ADMIN"
    run_id: int | None = None

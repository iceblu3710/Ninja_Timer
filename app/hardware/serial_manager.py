"""Minimal Arduino serial transport."""

from __future__ import annotations

from collections.abc import Callable
from time import monotonic
from typing import Any

from app.hardware.arduino_protocol import parse_arduino_line
from app.hardware.hardware_models import NormalizedHardwareEvent
from app.hardware.transport_base import HardwareTransport


class ArduinoSerialTransport(HardwareTransport):
    name = "ARDUINO"

    def __init__(
        self,
        port: str | None,
        baud_rate: int = 115200,
        timeout_seconds: float = 0.1,
        serial_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.port = port
        self.baud_rate = baud_rate
        self.timeout_seconds = timeout_seconds
        self._serial_factory = serial_factory
        self._serial: Any | None = None
        self._last_message_monotonic: float | None = None
        self._last_error: str | None = None

    def reconnect(self) -> None:
        self.close()
        if not self.port:
            self._last_error = "No serial port configured."
            return
        try:
            factory = self._serial_factory or _load_pyserial()
            self._serial = factory(self.port, self.baud_rate, timeout=self.timeout_seconds)
            self._last_error = None
        except Exception as exc:  # pragma: no cover - hardware dependent
            self._serial = None
            self._last_error = str(exc)

    def close(self) -> None:
        if self._serial is not None:
            try:
                self._serial.close()
            except Exception:
                pass
        self._serial = None

    def send_command(self, command: str) -> str | None:
        if self._serial is None:
            raise RuntimeError("Arduino serial transport is not connected.")
        self._serial.write(f"{command}\n".encode("utf-8"))
        return None

    def read_event(self) -> NormalizedHardwareEvent | None:
        if self._serial is None:
            return None
        raw = self._serial.readline()
        if not raw:
            return None
        if isinstance(raw, bytes):
            line = raw.decode("utf-8", errors="replace")
        else:
            line = str(raw)
        event = parse_arduino_line(line)
        self._last_message_monotonic = monotonic()
        return event

    def status(self) -> dict[str, Any]:
        return {
            "transport": self.name,
            "connected": self._serial is not None,
            "port": self.port,
            "baud_rate": self.baud_rate,
            "last_message_seconds_ago": (
                round(monotonic() - self._last_message_monotonic, 3)
                if self._last_message_monotonic is not None
                else None
            ),
            "last_error": self._last_error,
        }


def _load_pyserial() -> Callable[..., Any]:
    import serial

    return serial.Serial

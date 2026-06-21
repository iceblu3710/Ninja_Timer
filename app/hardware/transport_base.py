"""Common transport interface for timing hardware adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class HardwareTransport(ABC):
    name: str

    @abstractmethod
    def reconnect(self) -> None:
        """Reconnect or initialize the transport."""

    @abstractmethod
    def close(self) -> None:
        """Close the transport."""

    @abstractmethod
    def send_command(self, command: str) -> str | None:
        """Send a relay/control command and return an optional raw response."""

    @abstractmethod
    def status(self) -> dict[str, Any]:
        """Return transport health information."""

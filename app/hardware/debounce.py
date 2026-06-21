"""Backend input debounce for physical and simulated hardware events."""

from __future__ import annotations


class InputDebouncer:
    def __init__(self, window_ms: int = 250) -> None:
        self.window_ns = max(0, window_ms) * 1_000_000
        self._last_seen: dict[tuple[str, str], int] = {}

    def should_accept(self, input_key: str, state: str, now_ns: int) -> bool:
        key = (input_key.upper(), state.upper())
        previous = self._last_seen.get(key)
        if previous is not None and now_ns - previous < self.window_ns:
            return False
        self._last_seen[key] = now_ns
        return True

    def reset(self) -> None:
        self._last_seen.clear()

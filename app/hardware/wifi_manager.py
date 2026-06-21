"""M5Stamp/StamPLC MQTT transport."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.hardware.transport_base import HardwareTransport


class M5StampTransport(HardwareTransport):
    name = "M5STAMP"

    def __init__(
        self,
        host: str | None = None,
        port: int = 1883,
        topic_prefix: str = "dynasty/timer/io",
        device_id: str = "m5stamp-main",
        username: str | None = None,
        password: str | None = None,
        event_handler: Callable[[dict[str, Any]], None] | None = None,
        client_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.topic_prefix = topic_prefix.strip("/")
        self.device_id = device_id
        self.username = username
        self.password = password
        self._event_handler = event_handler
        self._client_factory = client_factory
        self._client: Any | None = None
        self.connected = False
        self.last_error: str | None = None
        self.last_message_at: str | None = None
        self.last_command_id: str | None = None

    def reconnect(self) -> None:
        self.close()
        if not self.host:
            self.connected = False
            self.last_error = "No MQTT host configured."
            return

        try:
            client = self._build_client()
            client.on_connect = self._on_connect
            client.on_disconnect = self._on_disconnect
            client.on_message = self._on_message
            if self.username:
                client.username_pw_set(self.username, self.password)
            client.connect(self.host, self.port, keepalive=30)
            client.loop_start()
            self._client = client
            self.last_error = None
        except Exception as exc:  # pragma: no cover - hardware/network dependent
            self.connected = False
            self._client = None
            self.last_error = str(exc)

    def close(self) -> None:
        if self._client is not None:
            try:
                self._client.loop_stop()
                self._client.disconnect()
            except Exception:
                pass
        self._client = None
        self.connected = False

    def send_command(self, command: str) -> str | None:
        if self._client is None or not self.connected:
            raise RuntimeError("M5Stamp transport is not connected.")

        payload = self._command_payload(command)
        command_topic = f"{self.topic_prefix}/{self.device_id}/cmd"
        self._client.publish(command_topic, json.dumps(payload), qos=1, retain=False)
        self.last_command_id = payload["command_id"]
        return f"MQTT_PUBLISHED,{payload['command_id']}"

    def status(self) -> dict[str, Any]:
        return {
            "transport": self.name,
            "connected": self.connected,
            "host": self.host,
            "port": self.port,
            "topic_prefix": self.topic_prefix,
            "device_id": self.device_id,
            "last_message_at": self.last_message_at,
            "last_command_id": self.last_command_id,
            "last_error": self.last_error,
        }

    def _build_client(self) -> Any:
        if self._client_factory is not None:
            return self._client_factory()
        import paho.mqtt.client as mqtt

        return mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

    def _on_connect(
        self,
        client: Any,
        _userdata: Any,
        _flags: Any,
        reason_code: Any,
        _properties: Any = None,
    ) -> None:
        reason_value = _reason_code_value(reason_code)
        if reason_value == 0:
            self.connected = True
            self.last_error = None
            client.subscribe(f"{self.topic_prefix}/+/event", qos=1)
            client.subscribe(f"{self.topic_prefix}/+/heartbeat", qos=0)
            client.subscribe(f"{self.topic_prefix}/+/state", qos=0)
        else:
            self.connected = False
            self.last_error = f"MQTT connect failed: {reason_code}"

    def _on_disconnect(
        self,
        _client: Any,
        _userdata: Any,
        _disconnect_flags: Any,
        reason_code: Any,
        _properties: Any = None,
    ) -> None:
        self.connected = False
        if _reason_code_value(reason_code) != 0:
            self.last_error = f"MQTT disconnected: {reason_code}"

    def _on_message(self, _client: Any, _userdata: Any, message: Any) -> None:
        try:
            payload = json.loads(message.payload.decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("MQTT payload must be a JSON object.")
            self.last_message_at = datetime.now(UTC).replace(microsecond=0).isoformat()
            topic_tail = str(message.topic).rsplit("/", 1)[-1]
            if topic_tail == "heartbeat":
                payload.setdefault("type", "HEARTBEAT")
            if self._event_handler is not None:
                self._event_handler(payload)
        except Exception as exc:
            self.last_error = str(exc)

    def _command_payload(self, command: str) -> dict[str, Any]:
        parts = [part.strip().upper() for part in command.split(",")]
        if len(parts) < 3 or parts[0] != "CMD":
            raise ValueError(f"Unsupported M5Stamp command: {command}")

        payload: dict[str, Any] = {
            "command_id": str(uuid4()),
            "device": parts[1],
            "action": parts[2],
        }
        if len(parts) >= 4 and parts[3].isdigit():
            payload["value_ms"] = int(parts[3])
        return payload


def _reason_code_value(reason_code: Any) -> int:
    value = getattr(reason_code, "value", reason_code)
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0 if str(reason_code).lower() in {"success", "normal disconnection"} else -1

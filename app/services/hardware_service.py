"""Hardware event normalization, persistence, and timer integration."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from time import perf_counter_ns
from typing import Any

from sqlalchemy.orm import Session

from app.api.response_models import run_response
from app.config import get_settings
from app.db.database import SessionLocal
from app.db.models import HardwareEvent
from app.db.repositories import HardwareRepository, RunRepository
from app.db.schemas import TimerArmRequest, TimerStateRead
from app.hardware.arduino_protocol import parse_arduino_line
from app.hardware.debounce import InputDebouncer
from app.hardware.hardware_models import NormalizedHardwareEvent
from app.hardware.m5stamp_protocol import parse_m5stamp_payload
from app.hardware.serial_manager import ArduinoSerialTransport
from app.hardware.simulated_transport import SimulatedTransport
from app.hardware.transport_base import HardwareTransport
from app.hardware.wifi_manager import M5StampTransport
from app.services.event_bus import event_bus
from app.services.timer_service import TimerServiceError, get_timer_service

logger = logging.getLogger(__name__)


@dataclass
class HardwareProcessResult:
    event: HardwareEvent
    timer_state: TimerStateRead | None = None
    run_id: int | None = None
    error: str | None = None

    @property
    def processed(self) -> bool:
        return self.event.process_status == "PROCESSED"

    def as_dict(self) -> dict[str, Any]:
        return {
            "event": hardware_event_response(self.event),
            "timer_state": self.timer_state.model_dump() if self.timer_state is not None else None,
            "run_id": self.run_id,
            "error": self.error,
        }


class HardwareService:
    def __init__(self, transport: HardwareTransport | None = None, debounce_ms: int | None = None):
        settings = get_settings()
        self.debouncer = InputDebouncer(
            debounce_ms if debounce_ms is not None else settings.hardware_debounce_ms
        )
        self.transport = transport or _build_transport(settings, self.process_transport_payload)

    def parse_raw_event(
        self, line: str | None = None, payload: dict | None = None
    ) -> NormalizedHardwareEvent:
        active_transport = self.transport.name.upper()
        if payload is not None:
            return parse_m5stamp_payload(payload)
        if not line:
            raise ValueError("line or payload is required")
        if active_transport == "ARDUINO":
            return parse_arduino_line(line)
        return _parse_csv_event(line, active_transport)

    def simulate_event(self, input_key: str, state: str = "DOWN") -> NormalizedHardwareEvent:
        if isinstance(self.transport, SimulatedTransport):
            return self.transport.make_event(input_key, state)
        return NormalizedHardwareEvent(
            transport="SIMULATED",
            event_type="EVT",
            input_key=input_key.upper(),
            state=state.upper(),
            raw_payload=f"EVT,{input_key.upper()},{state.upper()}",
            device_key="simulated-controller",
            display_name="Simulated Controller",
            parsed={"source": "simulate"},
        )

    def process_event(
        self, db: Session, normalized: NormalizedHardwareEvent
    ) -> HardwareProcessResult:
        repository = HardwareRepository(db)
        now_ns = perf_counter_ns()
        device = None
        if normalized.device_key is not None:
            device = repository.ensure_device(
                device_key=normalized.device_key,
                display_name=normalized.display_name or normalized.device_key,
                device_type=normalized.device_type,
                transport=normalized.transport.upper(),
            )

        duplicate_sequence = repository.is_duplicate_sequence(device, normalized.sequence_number)
        event = repository.record_event(
            device_id=device.id if device is not None else None,
            transport=normalized.transport.upper(),
            event_type=normalized.event_type.upper(),
            input_key=normalized.input_key.upper() if normalized.input_key else None,
            state=normalized.state.upper() if normalized.state else None,
            sequence_number=normalized.sequence_number,
            raw_payload=normalized.raw_payload,
            parsed_json=json.dumps(normalized.parsed) if normalized.parsed else None,
            received_monotonic_ns=now_ns,
            process_status="IGNORED" if duplicate_sequence else "PENDING",
            process_error="Duplicate sequence number." if duplicate_sequence else None,
        )
        if duplicate_sequence:
            return HardwareProcessResult(event=event, error=event.process_error)

        if device is not None:
            repository.mark_device_seen(device, sequence_number=normalized.sequence_number)

        try:
            return self._process_recorded_event(db, event, normalized, now_ns)
        except TimerServiceError as exc:
            repository.mark_event_processed(event, status="FAILED", error=str(exc))
            return HardwareProcessResult(event=event, error=str(exc))

    def _process_recorded_event(
        self,
        db: Session,
        event: HardwareEvent,
        normalized: NormalizedHardwareEvent,
        now_ns: int,
    ) -> HardwareProcessResult:
        repository = HardwareRepository(db)
        event_type = normalized.event_type.upper()

        if event_type in {"READY", "HEARTBEAT"}:
            repository.mark_event_processed(event, status="PROCESSED")
            return HardwareProcessResult(event=event)

        input_key, state = normalized.normalized_input()
        if event_type != "EVT" or input_key is None or state is None:
            repository.mark_event_processed(event, status="IGNORED", error="Unsupported event.")
            return HardwareProcessResult(event=event, error=event.process_error)

        if not self.debouncer.should_accept(input_key, state, now_ns):
            repository.mark_event_processed(
                event, status="IGNORED", error="Debounced duplicate event."
            )
            return HardwareProcessResult(event=event, error=event.process_error)

        if state != "DOWN":
            repository.mark_event_processed(event, status="IGNORED", error="Non-DOWN input state.")
            return HardwareProcessResult(event=event, error=event.process_error)

        timer_service = get_timer_service()
        if input_key == "ARM":
            timer_state = timer_service.arm(db, TimerArmRequest())
        elif input_key == "START":
            timer_state = timer_service.start(source="HARDWARE:START")
        elif input_key == "FINISH":
            timer_state = timer_service.finish(db, source="HARDWARE:FINISH")
        else:
            repository.mark_event_processed(event, status="IGNORED", error="Unsupported input.")
            return HardwareProcessResult(event=event, error=event.process_error)

        run_id = timer_state.run_id
        repository.mark_event_processed(event, status="PROCESSED", run_id=run_id)
        return HardwareProcessResult(event=event, timer_state=timer_state, run_id=run_id)

    def reconnect(self) -> None:
        self.transport.reconnect()

    def process_transport_payload(self, payload: dict[str, Any]) -> None:
        """Process async hardware payloads delivered by network transports."""
        with SessionLocal() as db:
            try:
                normalized = self.parse_raw_event(payload=payload)
                result = self.process_event(db, normalized)
                db.commit()
                asyncio.run(publish_hardware_result(db, result))
            except Exception as exc:  # pragma: no cover - hardware callback safety
                db.rollback()
                logger.exception("Failed to process hardware payload: %s", exc)

    def status(self, db: Session | None = None) -> dict[str, Any]:
        transport_status = self.transport.status()
        devices: list[dict[str, Any]] = []
        if db is not None:
            devices = [
                {
                    "id": device.id,
                    "device_key": device.device_key,
                    "display_name": device.display_name,
                    "device_type": device.device_type,
                    "transport": device.transport,
                    "active": device.active,
                    "last_seen_at": device.last_seen_at,
                    "last_sequence_number": device.last_sequence_number,
                    "health_status": device.health_status,
                }
                for device in HardwareRepository(db).list_devices()
            ]
        return {
            "driver": self.transport.name.lower(),
            "status": "connected" if transport_status.get("connected") else "disconnected",
            "transport": transport_status,
            "devices": devices,
        }


async def publish_hardware_result(db: Session, result: HardwareProcessResult) -> None:
    await event_bus.publish("hardware.status", {"event": hardware_event_response(result.event)})
    if result.timer_state is not None:
        await event_bus.publish("timer.state", result.timer_state.model_dump())
    if result.run_id is not None:
        run = RunRepository(db).get(result.run_id)
        if run is not None:
            await event_bus.publish("run.saved", {"run": run_response(run)})
            if run.status == "VALID":
                await event_bus.publish("leaderboard.updated", {"run_id": run.id})

    if (
        result.timer_state is not None
        and result.timer_state.state == "COUNTDOWN"
        and result.timer_state.countdown_token is not None
        and result.timer_state.countdown_remaining_ms is not None
    ):
        asyncio.create_task(
            _complete_countdown_later(
                token=result.timer_state.countdown_token,
                delay_ms=result.timer_state.countdown_remaining_ms,
            )
        )


async def _complete_countdown_later(token: int, delay_ms: int) -> None:
    await asyncio.sleep(delay_ms / 1000)
    state = get_timer_service().complete_countdown(token=token, source="HARDWARE:START")
    await event_bus.publish("timer.state", state.model_dump())


def hardware_event_response(event: HardwareEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "device_id": event.device_id,
        "transport": event.transport,
        "event_type": event.event_type,
        "input_key": event.input_key,
        "state": event.state,
        "sequence_number": event.sequence_number,
        "raw_payload": event.raw_payload,
        "parsed_json": event.parsed_json,
        "received_at": event.received_at,
        "processed_at": event.processed_at,
        "process_status": event.process_status,
        "process_error": event.process_error,
        "run_id": event.run_id,
    }


def _build_transport(
    settings: Any,
    event_handler: Any | None = None,
) -> HardwareTransport:
    driver = str(settings.hardware_driver).upper()
    if driver == "ARDUINO":
        return ArduinoSerialTransport(
            port=settings.hardware_serial_port,
            baud_rate=settings.hardware_serial_baud,
        )
    if driver == "M5STAMP":
        return M5StampTransport(
            host=settings.hardware_mqtt_host or settings.hardware_m5_host,
            port=settings.hardware_mqtt_port,
            topic_prefix=settings.hardware_mqtt_topic_prefix,
            device_id=settings.hardware_mqtt_device_id,
            username=settings.hardware_mqtt_username,
            password=settings.hardware_mqtt_password,
            event_handler=event_handler,
        )
    return SimulatedTransport()


def _parse_csv_event(line: str, transport: str) -> NormalizedHardwareEvent:
    parts = [part.strip() for part in line.strip().split(",")]
    if len(parts) < 3 or parts[0].upper() != "EVT":
        raise ValueError(f"Unsupported hardware event: {line}")
    return NormalizedHardwareEvent(
        transport=transport.upper(),
        event_type="EVT",
        input_key=parts[1].upper(),
        state=parts[2].upper(),
        sequence_number=int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else None,
        raw_payload=line.strip(),
        device_key=f"{transport.lower()}-{parts[1].lower()}",
        display_name=f"{transport.title()} {parts[1].title()}",
        device_type="INPUT",
        parsed={"parts": parts},
    )


hardware_service = HardwareService()


def get_hardware_service() -> HardwareService:
    return hardware_service


def reset_hardware_service_for_tests() -> None:
    global hardware_service
    hardware_service = HardwareService(transport=SimulatedTransport(), debounce_ms=250)

import json
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.api import routes_hardware
from app.api.auth import require_admin
from app.db.database import SessionLocal, get_db, initialize_database, reset_engine_for_tests
from app.db.models import Course, HardwareEvent, RelayAction, Run
from app.db.schemas import QueueEntryCreate
from app.hardware.arduino_protocol import format_relay_command, parse_arduino_line
from app.hardware.debounce import InputDebouncer
from app.hardware.wifi_manager import M5StampTransport
from app.services.hardware_service import reset_hardware_service_for_tests
from app.services.queue_service import add_queue_entry
from app.services.timer_service import reset_timer_service_for_tests


def _settings_for(db_path):
    return SimpleNamespace(database_url=f"sqlite:///{db_path}", database_echo=False)


def _hardware_api_client():
    app = FastAPI()
    app.include_router(routes_hardware.router)

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_admin] = lambda: "ADMIN"
    return TestClient(app)


def test_arduino_protocol_parser_and_command_formatting():
    ready = parse_arduino_line("READY")
    assert ready.event_type == "READY"
    assert ready.transport == "ARDUINO"

    heartbeat = parse_arduino_line("HEARTBEAT,42")
    assert heartbeat.event_type == "HEARTBEAT"
    assert heartbeat.sequence_number == 42

    event = parse_arduino_line("EVT,START,DOWN,43")
    assert event.event_type == "EVT"
    assert event.input_key == "START"
    assert event.state == "DOWN"
    assert event.sequence_number == 43

    assert format_relay_command("HORN", "PULSE", 200) == "CMD,HORN,PULSE,200"
    assert format_relay_command("GREEN", "ON") == "CMD,GREEN,ON"
    assert format_relay_command("ALL", "OFF") == "CMD,ALL,OFF"


def test_m5stamp_mqtt_transport_formats_relay_command():
    published = []

    class FakeClient:
        def publish(self, topic, payload, qos=0, retain=False):
            published.append((topic, json.loads(payload), qos, retain))

    transport = M5StampTransport(
        host="broker.local",
        topic_prefix="dynasty/timer/io",
        device_id="m5stamp-main",
    )
    transport._client = FakeClient()
    transport.connected = True

    response = transport.send_command("CMD,HORN,PULSE,200")

    assert response.startswith("MQTT_PUBLISHED,")
    assert published[0][0] == "dynasty/timer/io/m5stamp-main/cmd"
    assert published[0][1]["device"] == "HORN"
    assert published[0][1]["action"] == "PULSE"
    assert published[0][1]["value_ms"] == 200


def test_input_debounce_rejects_duplicates_inside_window():
    debouncer = InputDebouncer(window_ms=250)

    assert debouncer.should_accept("START", "DOWN", 1_000_000_000) is True
    assert debouncer.should_accept("START", "DOWN", 1_100_000_000) is False
    assert debouncer.should_accept("START", "DOWN", 1_300_000_000) is True
    assert debouncer.should_accept("FINISH", "DOWN", 1_350_000_000) is True


def test_simulated_hardware_arm_start_finish_persists_run_and_events(tmp_path):
    reset_engine_for_tests()
    reset_timer_service_for_tests()
    reset_hardware_service_for_tests()
    settings = _settings_for(tmp_path / "hardware.sqlite")
    initialize_database(settings)

    with SessionLocal() as db:
        course = db.scalar(select(Course).where(Course.slug == "speed-gauntlet"))
        assert course is not None
        course.countdown_seconds = 0
        entry = add_queue_entry(
            db,
            QueueEntryCreate(
                request_id="hardware-run-1",
                runner_name="Avery",
                age_group="U12",
                course_slug="speed-gauntlet",
            ),
        )
        db.commit()
        assert entry.id is not None

    client = _hardware_api_client()

    arm = client.post("/api/v1/hardware/simulate", json={"input_key": "ARM"})
    assert arm.status_code == 200
    assert arm.json()["data"]["timer_state"]["state"] == "READY"

    start = client.post("/api/v1/hardware/simulate", json={"input_key": "START"})
    assert start.status_code == 200
    assert start.json()["data"]["timer_state"]["state"] == "RUNNING"

    finish = client.post("/api/v1/hardware/simulate", json={"input_key": "FINISH"})
    assert finish.status_code == 200
    finish_data = finish.json()["data"]
    assert finish_data["timer_state"]["state"] == "SAVED"
    assert finish_data["run_id"] is not None

    with SessionLocal() as db:
        run = db.get(Run, finish_data["run_id"])
        event_count = db.scalar(select(func.count()).select_from(HardwareEvent))
        processed_count = db.scalar(
            select(func.count())
            .select_from(HardwareEvent)
            .where(HardwareEvent.process_status == "PROCESSED")
        )

    assert run is not None
    assert run.status == "VALID"
    assert run.source == "HARDWARE:FINISH"
    assert event_count == 3
    assert processed_count == 3

    reset_timer_service_for_tests()
    reset_hardware_service_for_tests()
    reset_engine_for_tests()


def test_duplicate_start_event_is_debounced(tmp_path):
    reset_engine_for_tests()
    reset_timer_service_for_tests()
    reset_hardware_service_for_tests()
    settings = _settings_for(tmp_path / "hardware.sqlite")
    initialize_database(settings)

    with SessionLocal() as db:
        course = db.scalar(select(Course).where(Course.slug == "speed-gauntlet"))
        assert course is not None
        course.countdown_seconds = 0
        add_queue_entry(
            db,
            QueueEntryCreate(
                request_id="hardware-run-2",
                runner_name="Charlie",
                course_slug="speed-gauntlet",
            ),
        )
        db.commit()

    client = _hardware_api_client()
    assert client.post("/api/v1/hardware/simulate", json={"input_key": "ARM"}).status_code == 200
    first_start = client.post("/api/v1/hardware/simulate", json={"input_key": "START"})
    duplicate_start = client.post("/api/v1/hardware/simulate", json={"input_key": "START"})

    assert first_start.json()["data"]["event"]["process_status"] == "PROCESSED"
    assert duplicate_start.json()["data"]["event"]["process_status"] == "IGNORED"
    assert duplicate_start.json()["data"]["event"]["process_error"] == "Debounced duplicate event."

    reset_timer_service_for_tests()
    reset_hardware_service_for_tests()
    reset_engine_for_tests()


def test_relay_endpoint_records_simulated_command(tmp_path):
    reset_engine_for_tests()
    reset_timer_service_for_tests()
    reset_hardware_service_for_tests()
    settings = _settings_for(tmp_path / "relay.sqlite")
    initialize_database(settings)

    client = _hardware_api_client()
    response = client.post("/api/v1/hardware/relay", json={"action_key": "HORN_PULSE"})

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["command"] == "CMD,HORN,PULSE,200"
    assert data["status"] == "ACKNOWLEDGED"

    with SessionLocal() as db:
        action = db.scalar(select(RelayAction))

    assert action is not None
    assert action.command == "CMD,HORN,PULSE,200"
    assert action.raw_response == "SIMULATED_ACK"

    reset_hardware_service_for_tests()
    reset_engine_for_tests()

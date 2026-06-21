from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.api import routes_timer
from app.db.database import SessionLocal, get_db, initialize_database, reset_engine_for_tests
from app.db.models import QueueEntry, Run
from app.db.schemas import QueueEntryCreate
from app.services.queue_service import add_queue_entry
from app.services.timer_service import reset_timer_service_for_tests
from app.services.timer_state import InvalidTimerTransition, TimerState, TimerStateMachine


def _settings_for(db_path):
    return SimpleNamespace(database_url=f"sqlite:///{db_path}", database_echo=False)


def _timer_api_client():
    app = FastAPI()
    app.include_router(routes_timer.router)

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def test_timer_state_machine_validates_transitions():
    machine = TimerStateMachine()

    assert machine.transition("arm") == TimerState.READY
    assert machine.transition("start_command") == TimerState.RUNNING
    assert machine.transition("finish_sensor_triggered") == TimerState.FINISHED
    assert machine.transition("save_run") == TimerState.SAVED
    assert machine.transition("reset") == TimerState.IDLE

    with pytest.raises(InvalidTimerTransition):
        machine.transition("finish_sensor_triggered")


def test_timer_api_arm_start_finish_persists_valid_run(tmp_path):
    reset_engine_for_tests()
    reset_timer_service_for_tests()
    settings = _settings_for(tmp_path / "timer.sqlite")
    initialize_database(settings)

    with SessionLocal() as db:
        queue_entry = add_queue_entry(
            db,
            QueueEntryCreate(
                request_id="timer-api-run-1",
                runner_name="Avery",
                age_group="U12",
                course_slug="speed-gauntlet",
            ),
        )
        db.commit()
        queue_entry_id = queue_entry.id

    client = _timer_api_client()

    arm_response = client.post("/api/v1/timer/arm", json={"queue_entry_id": queue_entry_id})
    assert arm_response.status_code == 200
    assert arm_response.json()["data"]["state"] == "READY"

    start_response = client.post("/api/v1/timer/start", json={"source": "ADMIN"})
    assert start_response.status_code == 200
    assert start_response.json()["data"]["state"] == "RUNNING"

    finish_response = client.post("/api/v1/timer/finish", json={"source": "ADMIN"})
    assert finish_response.status_code == 200
    finish_data = finish_response.json()["data"]
    assert finish_data["state"] == "SAVED"
    assert finish_data["run_id"] is not None

    with SessionLocal() as db:
        run_count = db.scalar(select(func.count()).select_from(Run))
        run = db.scalar(select(Run).where(Run.id == finish_data["run_id"]))
        queue_entry = db.get(QueueEntry, queue_entry_id)

    assert run_count == 1
    assert run is not None
    assert run.status == "VALID"
    assert run.runner_name_snapshot == "Avery"
    assert run.age_group_snapshot == "U12"
    assert run.elapsed_ms is not None
    assert run.elapsed_ms >= 0
    assert run.started_at is not None
    assert run.finished_at is not None
    assert run.start_monotonic_ns is not None
    assert run.finish_monotonic_ns is not None
    assert queue_entry is not None
    assert queue_entry.status == "COMPLETED"

    reset_timer_service_for_tests()
    reset_engine_for_tests()

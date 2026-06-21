import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.api import routes_timer
from app.api.auth import require_admin
from app.db.database import SessionLocal, get_db, initialize_database, reset_engine_for_tests
from app.db.models import Course, CourseRevision, QueueEntry, Run
from app.db.schemas import QueueEntryCreate, TimerArmRequest
from app.services.queue_service import add_queue_entry
from app.services.timer_service import TimerService, reset_timer_service_for_tests
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
    app.dependency_overrides[require_admin] = lambda: "ADMIN"
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


def test_timer_service_counts_down_before_running(tmp_path):
    reset_engine_for_tests()
    settings = _settings_for(tmp_path / "timer.sqlite")
    initialize_database(settings)
    service = TimerService()

    with SessionLocal() as db:
        course = db.scalar(select(Course).where(Course.slug == "speed-gauntlet"))
        assert course is not None
        state = service.arm(
            db,
            TimerArmRequest(
                course_id=course.id,
                runner_name="Avery",
                mode="OPEN_GYM",
            ),
        )
        assert state.state == "READY"

        countdown = service.start(source="ADMIN")
        assert countdown.state == "COUNTDOWN"
        assert countdown.countdown_seconds == 3
        assert countdown.countdown_token is not None
        assert countdown.countdown_remaining_ms is not None
        assert countdown.countdown_remaining_ms > 0

        running = service.complete_countdown(
            token=countdown.countdown_token,
            source="ADMIN",
        )
        assert running.state == "RUNNING"
        assert running.started_at is not None

    reset_engine_for_tests()


def test_timer_api_arm_start_finish_persists_valid_run(tmp_path):
    reset_engine_for_tests()
    reset_timer_service_for_tests()
    settings = _settings_for(tmp_path / "timer.sqlite")
    initialize_database(settings)

    with SessionLocal() as db:
        course = db.scalar(select(Course).where(Course.slug == "speed-gauntlet"))
        assert course is not None
        course.countdown_seconds = 0
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


def test_timer_reset_keeps_runner_armed(tmp_path):
    reset_engine_for_tests()
    reset_timer_service_for_tests()
    settings = _settings_for(tmp_path / "timer.sqlite")
    initialize_database(settings)

    with SessionLocal() as db:
        course = db.scalar(select(Course).where(Course.slug == "speed-gauntlet"))
        assert course is not None
        course.countdown_seconds = 0
        db.commit()
        course_id = course.id

    client = _timer_api_client()

    # Arm a runner
    arm_response = client.post(
        "/api/v1/timer/arm",
        json={"runner_name": "Avery", "course_id": course_id, "mode": "OPEN_GYM"},
    )
    assert arm_response.status_code == 200
    assert arm_response.json()["data"]["state"] == "READY"
    assert arm_response.json()["data"]["runner"]["name"] == "Avery"

    # Start the run
    start_response = client.post("/api/v1/timer/start", json={"source": "ADMIN"})
    assert start_response.status_code == 200
    assert start_response.json()["data"]["state"] == "RUNNING"

    # Reset with default (clear_active_runner = False)
    reset_response = client.post("/api/v1/timer/reset", json={})
    assert reset_response.status_code == 200
    reset_data = reset_response.json()["data"]
    # The state should be READY, and the runner should still be armed!
    assert reset_data["state"] == "READY"
    assert reset_data["runner"]["name"] == "Avery"
    assert reset_data["elapsed_ms"] is None

    # Reset with clear_active_runner = True
    reset_clear_response = client.post("/api/v1/timer/reset", json={"clear_active_runner": True})
    assert reset_clear_response.status_code == 200
    reset_clear_data = reset_clear_response.json()["data"]
    # The state should be IDLE, and the runner should be cleared!
    assert reset_clear_data["state"] == "IDLE"
    assert reset_clear_data["runner"] is None

    reset_timer_service_for_tests()
    reset_engine_for_tests()


def test_queue_entry_skip_moves_to_bottom(tmp_path):
    reset_engine_for_tests()
    reset_timer_service_for_tests()
    settings = _settings_for(tmp_path / "timer.sqlite")
    initialize_database(settings)

    # We need a routes_queue api client
    from app.api import routes_queue

    app = FastAPI()
    app.include_router(routes_queue.router)
    app.dependency_overrides[get_db] = lambda: SessionLocal()
    app.dependency_overrides[require_admin] = lambda: "ADMIN"
    client = TestClient(app)

    with SessionLocal() as db:
        q1 = add_queue_entry(
            db, QueueEntryCreate(runner_name="Avery", course_slug="speed-gauntlet", request_id="r1")
        )
        q2 = add_queue_entry(
            db,
            QueueEntryCreate(runner_name="Charlie", course_slug="speed-gauntlet", request_id="r2"),
        )
        db.commit()
        q1_id = q1.id
        q2_id = q2.id
        q1_ver = q1.version

    # Avery is at position 1 (first), Charlie is at position 2 (second)
    # Skip Avery
    skip_response = client.patch(
        f"/api/v1/queue/{q1_id}",
        json={"version": q1_ver, "status": "SKIPPED", "request_id": "skip-req-1"},
    )
    assert skip_response.status_code == 200

    with SessionLocal() as db:
        entry1 = db.get(QueueEntry, q1_id)
        entry2 = db.get(QueueEntry, q2_id)

        # Avery should still be WAITING
        assert entry1.status == "WAITING"
        # Avery should have a skipped timestamp set
        assert entry1.skipped_at is not None
        # Avery should be positioned AFTER Charlie
        assert entry1.sort_key > entry2.sort_key
        assert entry1.position > entry2.position

    reset_timer_service_for_tests()
    reset_engine_for_tests()


def test_queue_reorder_endpoint(tmp_path):
    reset_engine_for_tests()
    reset_timer_service_for_tests()
    settings = _settings_for(tmp_path / "timer.sqlite")
    initialize_database(settings)

    from app.api import routes_queue

    app = FastAPI()
    app.include_router(routes_queue.router)
    app.dependency_overrides[get_db] = lambda: SessionLocal()
    app.dependency_overrides[require_admin] = lambda: "ADMIN"
    client = TestClient(app)

    with SessionLocal() as db:
        q1 = add_queue_entry(
            db, QueueEntryCreate(runner_name="Avery", course_slug="speed-gauntlet", request_id="r1")
        )
        q2 = add_queue_entry(
            db,
            QueueEntryCreate(runner_name="Charlie", course_slug="speed-gauntlet", request_id="r2"),
        )
        q3 = add_queue_entry(
            db, QueueEntryCreate(runner_name="Bob", course_slug="speed-gauntlet", request_id="r3")
        )
        db.commit()
        q1_id = q1.id
        q2_id = q2.id
        q3_id = q3.id

    # Original positions: Avery (1), Charlie (2), Bob (3)
    # Reorder to: Bob, Avery, Charlie
    reorder_response = client.post(
        "/api/v1/queue/reorder", json={"queue_entry_ids": [q3_id, q1_id, q2_id]}
    )
    assert reorder_response.status_code == 200

    with SessionLocal() as db:
        entry1 = db.get(QueueEntry, q1_id)
        entry2 = db.get(QueueEntry, q2_id)
        entry3 = db.get(QueueEntry, q3_id)

        # Bob (q3) is first (position 1, lowest sort key)
        assert entry3.position == 1
        # Avery (q1) is second (position 2)
        assert entry1.position == 2
        # Charlie (q2) is third (position 3, highest sort key)
        assert entry2.position == 3

        assert entry3.sort_key < entry1.sort_key < entry2.sort_key

    reset_timer_service_for_tests()
    reset_engine_for_tests()


def test_timer_obstacle_toggles_and_saves_on_finish(tmp_path):
    reset_engine_for_tests()
    reset_timer_service_for_tests()
    settings = _settings_for(tmp_path / "timer.sqlite")
    initialize_database(settings)

    with SessionLocal() as db:
        course = db.scalar(select(Course).where(Course.slug == "speed-gauntlet"))
        assert course is not None
        course.countdown_seconds = 0

        # Give revision some obstacles
        from app.db.models import CourseRevision

        revision = db.scalar(
            select(CourseRevision).where(
                CourseRevision.course_id == course.id,
                CourseRevision.active.is_(True),
                CourseRevision.revision_end_date.is_(None),
            )
        )
        assert revision is not None
        revision.obstacle_count = 3

        queue_entry = add_queue_entry(
            db,
            QueueEntryCreate(
                request_id="timer-api-run-obstacles",
                runner_name="Dylan",
                age_group="U12",
                course_slug="speed-gauntlet",
            ),
        )
        db.commit()
        queue_entry_id = queue_entry.id

    client = _timer_api_client()

    # Arm a runner
    arm_response = client.post("/api/v1/timer/arm", json={"queue_entry_id": queue_entry_id})
    assert arm_response.status_code == 200

    # Start the run
    start_response = client.post("/api/v1/timer/start", json={"source": "ADMIN"})
    assert start_response.status_code == 200

    # Toggle obstacle 1 (index 1) to failed
    toggle_response = client.post("/api/v1/timer/obstacles/1/toggle")
    assert toggle_response.status_code == 200
    assert toggle_response.json()["data"]["obstacle_status"] == ["pending", "failed", "pending"]

    # Toggle it back to pending
    toggle_back_response = client.post("/api/v1/timer/obstacles/1/toggle")
    assert toggle_back_response.status_code == 200
    assert toggle_back_response.json()["data"]["obstacle_status"] == [
        "pending",
        "pending",
        "pending",
    ]

    # Toggle obstacle 0 to failed
    toggle_fail_response = client.post("/api/v1/timer/obstacles/0/toggle")
    assert toggle_fail_response.status_code == 200
    assert toggle_fail_response.json()["data"]["obstacle_status"] == [
        "failed",
        "pending",
        "pending",
    ]

    # Finish run
    finish_response = client.post("/api/v1/timer/finish", json={"source": "ADMIN"})
    assert finish_response.status_code == 200
    finish_data = finish_response.json()["data"]
    # The active state should now have the pending obstacles marked as "passed"
    assert finish_data["obstacle_status"] == ["failed", "passed", "passed"]

    # Verify run persistence of obstacle status
    with SessionLocal() as db:
        run = db.scalar(select(Run).where(Run.id == finish_data["run_id"]))

    assert run is not None
    import json

    parsed_status = json.loads(run.obstacle_status_json)
    # The first (index 0) failed, others passed
    assert parsed_status == ["failed", "passed", "passed"]

    # Toggle obstacle 2 (index 2) to failed after completion (SAVED state)
    toggle_post_completion = client.post("/api/v1/timer/obstacles/2/toggle")
    assert toggle_post_completion.status_code == 200
    assert toggle_post_completion.json()["data"]["obstacle_status"] == [
        "failed",
        "passed",
        "failed",
    ]

    # Verify database is updated dynamically
    with SessionLocal() as db:
        run_updated = db.scalar(select(Run).where(Run.id == finish_data["run_id"]))
    assert run_updated is not None
    assert json.loads(run_updated.obstacle_status_json) == ["failed", "passed", "failed"]

    # Toggle it back to passed
    toggle_back_post_completion = client.post("/api/v1/timer/obstacles/2/toggle")
    assert toggle_back_post_completion.status_code == 200
    assert toggle_back_post_completion.json()["data"]["obstacle_status"] == [
        "failed",
        "passed",
        "passed",
    ]

    # Verify database is updated dynamically back
    with SessionLocal() as db:
        run_updated_back = db.scalar(select(Run).where(Run.id == finish_data["run_id"]))
    assert run_updated_back is not None
    assert json.loads(run_updated_back.obstacle_status_json) == ["failed", "passed", "passed"]

    reset_timer_service_for_tests()
    reset_engine_for_tests()


def test_timer_uses_default_obstacles_when_revision_count_missing(tmp_path):
    reset_engine_for_tests()
    reset_timer_service_for_tests()
    settings = _settings_for(tmp_path / "timer.sqlite")
    initialize_database(settings)

    with SessionLocal() as db:
        course = db.scalar(select(Course).where(Course.slug == "speed-gauntlet"))
        assert course is not None
        course.countdown_seconds = 0

        revision = db.scalar(
            select(CourseRevision).where(
                CourseRevision.course_id == course.id,
                CourseRevision.active.is_(True),
                CourseRevision.revision_end_date.is_(None),
            )
        )
        assert revision is not None
        revision.obstacle_count = None

        queue_entry = add_queue_entry(
            db,
            QueueEntryCreate(
                runner_name="Avery",
                course_slug="speed-gauntlet",
                request_id="default-obstacles",
            ),
        )
        db.commit()
        queue_entry_id = queue_entry.id

    client = _timer_api_client()

    arm_resp = client.post("/api/v1/timer/arm", json={"queue_entry_id": queue_entry_id})
    assert arm_resp.status_code == 200
    assert arm_resp.json()["data"]["course"]["obstacle_count"] == 3
    assert arm_resp.json()["data"]["obstacle_status"] == ["pending", "pending", "pending"]

    start_resp = client.post("/api/v1/timer/start", json={"source": "ADMIN"})
    assert start_resp.status_code == 200

    finish_resp = client.post("/api/v1/timer/finish", json={"source": "ADMIN"})
    assert finish_resp.status_code == 200
    finish_data = finish_resp.json()["data"]
    assert finish_data["obstacle_status"] == ["passed", "passed", "passed"]

    with SessionLocal() as db:
        run = db.scalar(select(Run).where(Run.queue_entry_id == queue_entry_id))
    assert run is not None
    assert json.loads(run.obstacle_status_json) == ["passed", "passed", "passed"]

    reset_timer_service_for_tests()
    reset_engine_for_tests()


def test_timer_accept_scenarios(tmp_path):
    reset_engine_for_tests()
    reset_timer_service_for_tests()
    settings = _settings_for(tmp_path / "timer.sqlite")
    initialize_database(settings)

    with SessionLocal() as db:
        course = db.scalar(select(Course).where(Course.slug == "speed-gauntlet"))
        assert course is not None
        course.countdown_seconds = 0

        # Add two runners to the queue
        q1 = add_queue_entry(
            db, QueueEntryCreate(runner_name="Avery", course_slug="speed-gauntlet", request_id="r1")
        )
        q2 = add_queue_entry(
            db,
            QueueEntryCreate(runner_name="Charlie", course_slug="speed-gauntlet", request_id="r2"),
        )
        db.commit()
        q1_id = q1.id
        q2_id = q2.id

    client = _timer_api_client()

    # 1. Accept when running: it should save current runner, mark completed,
    # and arm the next runner in the queue.
    arm_resp = client.post("/api/v1/timer/arm", json={"queue_entry_id": q1_id})
    assert arm_resp.status_code == 200
    assert arm_resp.json()["data"]["runner"]["name"] == "Avery"

    start_resp = client.post("/api/v1/timer/start", json={"source": "ADMIN"})
    assert start_resp.status_code == 200
    assert start_resp.json()["data"]["state"] == "RUNNING"

    # Accept while running
    accept_resp = client.post("/api/v1/timer/accept", json={"source": "ADMIN"})
    assert accept_resp.status_code == 200

    # State should now be READY (as the next runner in the queue, Charlie, is armed)
    accept_data = accept_resp.json()["data"]
    assert accept_data["state"] == "READY"
    assert accept_data["runner"]["name"] == "Charlie"

    # Check database to verify Avery's run is saved and queue entries are updated
    with SessionLocal() as db:
        avery_run = db.scalar(select(Run).where(Run.queue_entry_id == q1_id))
        assert avery_run is not None
        assert avery_run.status == "VALID"
        assert avery_run.elapsed_ms is not None

        entry1 = db.get(QueueEntry, q1_id)
        entry2 = db.get(QueueEntry, q2_id)
        assert entry1.status == "COMPLETED"
        assert entry2.status == "ACTIVE"

    # 2. Accept when SAVED with empty queue: it should clear the runner and go to IDLE
    # Finish/save Charlie's run first
    start_resp2 = client.post("/api/v1/timer/start", json={"source": "ADMIN"})
    assert start_resp2.status_code == 200

    finish_resp2 = client.post("/api/v1/timer/finish", json={"source": "ADMIN"})
    assert finish_resp2.status_code == 200
    assert finish_resp2.json()["data"]["state"] == "SAVED"

    # Accept when saved (empty queue)
    accept_resp2 = client.post("/api/v1/timer/accept", json={"source": "ADMIN"})
    assert accept_resp2.status_code == 200
    accept_data2 = accept_resp2.json()["data"]
    assert accept_data2["state"] == "IDLE"
    assert accept_data2["runner"] is None

    # Check database to verify Charlie's run is saved and queue is completed
    with SessionLocal() as db:
        charlie_run = db.scalar(select(Run).where(Run.queue_entry_id == q2_id))
        assert charlie_run is not None
        assert charlie_run.status == "VALID"

        entry2_updated = db.get(QueueEntry, q2_id)
        assert entry2_updated.status == "COMPLETED"

    # 3. Accept when IDLE: should fail with error
    accept_fail = client.post("/api/v1/timer/accept", json={"source": "ADMIN"})
    assert accept_fail.status_code == 409
    assert (
        "Cannot accept because the timer is not in a completed or running state."
        in accept_fail.json()["error"]["message"]
    )

    reset_timer_service_for_tests()
    reset_engine_for_tests()


def test_timer_new_scenarios(tmp_path):
    reset_engine_for_tests()
    reset_timer_service_for_tests()
    settings = _settings_for(tmp_path / "timer.sqlite")
    initialize_database(settings)

    with SessionLocal() as db:
        course = db.scalar(select(Course).where(Course.slug == "speed-gauntlet"))
        assert course is not None
        course.countdown_seconds = 0

        # Give revision some obstacles
        from app.db.models import CourseRevision

        revision = db.scalar(
            select(CourseRevision).where(
                CourseRevision.course_id == course.id,
                CourseRevision.active.is_(True),
                CourseRevision.revision_end_date.is_(None),
            )
        )
        assert revision is not None
        revision.obstacle_count = 3

        # Add runners
        q1 = add_queue_entry(
            db, QueueEntryCreate(runner_name="Avery", course_slug="speed-gauntlet", request_id="r1")
        )
        q2 = add_queue_entry(
            db,
            QueueEntryCreate(runner_name="Charlie", course_slug="speed-gauntlet", request_id="r2"),
        )
        db.commit()
        q1_id = q1.id
        q2_id = q2.id

    client = _timer_api_client()

    # --- Scenario 1: Obstacles go green when finished ---
    # Arm Avery
    arm_resp = client.post("/api/v1/timer/arm", json={"queue_entry_id": q1_id})
    assert arm_resp.status_code == 200

    # Start run
    start_resp = client.post("/api/v1/timer/start")
    assert start_resp.status_code == 200

    # Toggle obstacle index 0 to failed
    client.post("/api/v1/timer/obstacles/0/toggle")

    # Finish the run
    finish_resp = client.post("/api/v1/timer/finish")
    assert finish_resp.status_code == 200
    finish_data = finish_resp.json()["data"]

    # The obstacle status should be ["failed", "passed", "passed"] (others went green!)
    assert finish_data["obstacle_status"] == ["failed", "passed", "passed"]

    # --- Scenario 2: Obstacles toggle passed/failed post-completion ---
    # Toggle obstacle 1 (index 1) which is currently "passed" -> should go to "failed"
    toggle_resp1 = client.post("/api/v1/timer/obstacles/1/toggle")
    assert toggle_resp1.status_code == 200
    assert toggle_resp1.json()["data"]["obstacle_status"] == ["failed", "failed", "passed"]

    # Toggle obstacle 1 back -> should go to "passed"
    toggle_resp2 = client.post("/api/v1/timer/obstacles/1/toggle")
    assert toggle_resp2.status_code == 200
    assert toggle_resp2.json()["data"]["obstacle_status"] == ["failed", "passed", "passed"]

    # --- Scenario 3: Accept when SAVED with a runner in the queue ---
    # Current state is SAVED. There is a next runner in the queue: Charlie.
    accept_resp = client.post("/api/v1/timer/accept")
    assert accept_resp.status_code == 200
    accept_data = accept_resp.json()["data"]
    assert accept_data["state"] == "READY"
    assert accept_data["runner"]["name"] == "Charlie"

    # Verify Avery's queue entry is COMPLETED and Charlie's is ACTIVE
    with SessionLocal() as db:
        entry1 = db.get(QueueEntry, q1_id)
        entry2 = db.get(QueueEntry, q2_id)
        assert entry1.status == "COMPLETED"
        assert entry2.status == "ACTIVE"

    # --- Scenario 4: Deadlock prevention - arm and start from any state ---
    # Current state is READY. Let's start the run.
    start_resp2 = client.post("/api/v1/timer/start")
    assert start_resp2.status_code == 200
    assert start_resp2.json()["data"]["state"] == "RUNNING"

    # Start it again while RUNNING -> should restart fresh at 00:00:00 and keep running
    start_resp3 = client.post("/api/v1/timer/start")
    assert start_resp3.status_code == 200
    assert start_resp3.json()["data"]["state"] == "RUNNING"

    # Arm a different runner manually while RUNNING. It should transition to
    # READY and set the new runner.
    arm_resp2 = client.post(
        "/api/v1/timer/arm",
        json={"runner_name": "Dylan", "course_id": course.id, "mode": "OPEN_GYM"},
    )
    assert arm_resp2.status_code == 200
    assert arm_resp2.json()["data"]["state"] == "READY"
    assert arm_resp2.json()["data"]["runner"]["name"] == "Dylan"

    # Charlie's queue entry should be reverted to WAITING because the run was
    # interrupted before completion.
    with SessionLocal() as db:
        entry2_reverted = db.get(QueueEntry, q2_id)
        assert entry2_reverted.status == "WAITING"

    reset_timer_service_for_tests()
    reset_engine_for_tests()

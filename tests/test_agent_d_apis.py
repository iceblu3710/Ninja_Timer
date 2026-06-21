from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.api import routes_leaderboards, routes_queue, routes_runs
from app.db.database import SessionLocal, get_db, initialize_database, reset_engine_for_tests
from app.db.models import Course, CourseRevision, QueueEntry, Run
from app.db.repositories import RunRepository, utc_now


def _settings_for(db_path):
    return SimpleNamespace(database_url=f"sqlite:///{db_path}", database_echo=False)


def _agent_d_client():
    app = FastAPI()
    app.include_router(routes_queue.router)
    app.include_router(routes_runs.router)
    app.include_router(routes_leaderboards.router)

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def _seeded_course():
    with SessionLocal() as db:
        course = db.scalar(select(Course).where(Course.slug == "speed-gauntlet"))
        assert course is not None
        revision = db.scalar(
            select(CourseRevision).where(
                CourseRevision.course_id == course.id,
                CourseRevision.active.is_(True),
            )
        )
        assert revision is not None
        return course.id, revision.id, course.name, revision.revision_name


def _create_run(
    *,
    runner_name: str,
    elapsed_ms: int,
    status: str = "VALID",
    course_id: int,
    course_revision_id: int,
    course_name: str,
    course_revision_name: str,
) -> int:
    now = utc_now()
    with SessionLocal() as db:
        run = RunRepository(db).create(
            session_id=None,
            athlete_id=None,
            queue_entry_id=None,
            course_id=course_id,
            course_revision_id=course_revision_id,
            runner_name_snapshot=runner_name,
            age_group_snapshot="9-11",
            course_name_snapshot=course_name,
            course_revision_snapshot=course_revision_name,
            mode="OPEN_GYM",
            status=status,
            started_at=now,
            finished_at=now,
            elapsed_ms=elapsed_ms,
            start_monotonic_ns=100,
            finish_monotonic_ns=100 + elapsed_ms * 1_000_000,
            start_source="TEST",
            finish_source="TEST",
            source="TEST",
            false_start_ms=None,
            reaction_ms=None,
            notes=None,
            deleted_at=None,
            deleted_reason=None,
        )
        db.commit()
        return run.id


def test_queue_api_joins_idempotently_and_soft_cancels(tmp_path):
    reset_engine_for_tests()
    initialize_database(_settings_for(tmp_path / "timer.sqlite"))
    course_id, _revision_id, _course_name, _revision_name = _seeded_course()
    client = _agent_d_client()

    payload = {
        "request_id": "kiosk-join-1",
        "name": "Riley",
        "age_group": "9-11",
        "course_id": course_id,
        "mode": "OPEN_GYM",
    }
    first = client.post("/api/v1/queue", json=payload)
    second = client.post("/api/v1/queue", json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["data"]["id"] == first.json()["data"]["id"]
    assert second.json()["data"]["runner_name"] == "Riley"

    listed = client.get("/api/v1/queue")
    assert listed.status_code == 200
    assert [entry["request_id"] for entry in listed.json()["data"]] == ["kiosk-join-1"]

    queue_entry_id = first.json()["data"]["id"]
    moved = client.patch(
        f"/api/v1/queue/{queue_entry_id}",
        json={"request_id": "admin-move-1", "version": 1, "position": 2},
    )
    assert moved.status_code == 200
    assert moved.json()["data"]["position"] == 2
    assert moved.json()["data"]["version"] == 2

    stale = client.patch(
        f"/api/v1/queue/{queue_entry_id}",
        json={"request_id": "admin-stale-1", "version": 1, "position": 3},
    )
    assert stale.status_code == 409

    activated = client.patch(
        f"/api/v1/queue/{queue_entry_id}",
        json={"request_id": "admin-active-1", "version": 2, "status": "ACTIVE"},
    )
    assert activated.status_code == 200
    assert activated.json()["data"]["status"] == "ACTIVE"

    recovered = client.post("/api/v1/queue/recover", json={"policy": "RETURN_ACTIVE_TO_WAITING"})
    assert recovered.status_code == 200
    assert recovered.json()["data"][0]["status"] == "WAITING"

    cancelled = client.delete(f"/api/v1/queue/{queue_entry_id}")
    assert cancelled.status_code == 200
    assert cancelled.json()["data"]["status"] == "CANCELLED"

    with SessionLocal() as db:
        queue_count = db.scalar(select(func.count()).select_from(QueueEntry))
        entry = db.get(QueueEntry, queue_entry_id)

    assert queue_count == 1
    assert entry is not None
    assert entry.status == "CANCELLED"

    reset_engine_for_tests()


def test_runs_recent_and_leaderboards_use_persisted_non_deleted_data(tmp_path):
    reset_engine_for_tests()
    initialize_database(_settings_for(tmp_path / "timer.sqlite"))
    course_id, revision_id, course_name, revision_name = _seeded_course()
    client = _agent_d_client()

    _create_run(
        runner_name="Avery",
        elapsed_ms=5000,
        course_id=course_id,
        course_revision_id=revision_id,
        course_name=course_name,
        course_revision_name=revision_name,
    )
    _create_run(
        runner_name="Riley",
        elapsed_ms=3000,
        course_id=course_id,
        course_revision_id=revision_id,
        course_name=course_name,
        course_revision_name=revision_name,
    )
    _create_run(
        runner_name="DNF Runner",
        elapsed_ms=1000,
        status="DNF",
        course_id=course_id,
        course_revision_id=revision_id,
        course_name=course_name,
        course_revision_name=revision_name,
    )
    deleted_run_id = _create_run(
        runner_name="Deleted Runner",
        elapsed_ms=2000,
        course_id=course_id,
        course_revision_id=revision_id,
        course_name=course_name,
        course_revision_name=revision_name,
    )

    delete_response = client.request(
        "DELETE",
        f"/api/v1/runs/{deleted_run_id}",
        json={"reason": "bad finish sensor"},
    )
    assert delete_response.status_code == 200
    assert delete_response.json()["data"]["status"] == "DELETED"

    recent = client.get("/api/v1/runs/recent", params={"limit": 10})
    assert recent.status_code == 200
    recent_names = {run["runner_name"] for run in recent.json()["data"]}
    assert "Deleted Runner" not in recent_names
    assert {"Avery", "Riley", "DNF Runner"}.issubset(recent_names)

    leaderboard = client.get(
        "/api/v1/leaderboards/all-time",
        params={"course_id": course_id, "limit": 10},
    )
    assert leaderboard.status_code == 200
    rows = leaderboard.json()["data"]
    assert [row["runner_name"] for row in rows] == ["Riley", "Avery"]
    assert [row["rank"] for row in rows] == [1, 2]

    today = client.get(
        "/api/v1/leaderboards/today",
        params={"course_id": course_id, "limit": 10},
    )
    assert today.status_code == 200
    assert [row["runner_name"] for row in today.json()["data"]] == ["Riley", "Avery"]

    personal_bests = client.get(
        "/api/v1/leaderboards/personal-bests",
        params={"course_id": course_id, "limit": 10},
    )
    assert personal_bests.status_code == 200
    assert [row["runner_name"] for row in personal_bests.json()["data"]] == ["Riley", "Avery"]

    export = client.get("/api/v1/runs/export.csv", params={"course_id": course_id})
    assert export.status_code == 200
    assert "runner_name" in export.text
    assert "Riley" in export.text
    assert "Deleted Runner" not in export.text

    with SessionLocal() as db:
        deleted_run = db.get(Run, deleted_run_id)

    assert deleted_run is not None
    assert deleted_run.deleted_at is not None
    assert deleted_run.deleted_reason == "bad finish sensor"

    reset_engine_for_tests()

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api import routes_auth, routes_ops, routes_runs, routes_settings
from app.api.auth import AdminAuthError, admin_auth_exception_handler
from app.config import get_settings
from app.db.database import SessionLocal, get_db, initialize_database, reset_engine_for_tests
from app.db.models import Course, CourseRevision, Setting, SystemEvent
from app.db.repositories import RunRepository, utc_now


def _settings_for(db_path):
    return SimpleNamespace(
        database_url=f"sqlite:///{db_path}",
        database_echo=False,
        admin_pin="2468",
        admin_session_seconds=3600,
        app_version="test",
        backup_retention_days=30,
    )


def _agent_h_client(settings):
    app = FastAPI()
    app.include_router(routes_auth.router)
    app.include_router(routes_settings.router)
    app.include_router(routes_ops.router)
    app.include_router(routes_runs.router)
    app.add_exception_handler(AdminAuthError, admin_auth_exception_handler)

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


def _admin_headers(client):
    login = client.post("/api/v1/auth/login", json={"pin": "2468"})
    assert login.status_code == 200
    return {"X-Admin-Token": login.json()["data"]["token"]}


def test_settings_require_admin_and_support_update_validation_and_rollback(tmp_path):
    reset_engine_for_tests()
    settings = _settings_for(tmp_path / "timer.sqlite")
    initialize_database(settings)
    client = _agent_h_client(settings)

    listed = client.get("/api/v1/settings")
    assert listed.status_code == 200
    countdown = listed.json()["data"]["timer.countdown_seconds"]
    assert countdown["value"] == 3

    unauthorized = client.patch(
        "/api/v1/settings",
        json={
            "changes": {
                "timer.countdown_seconds": {
                    "value": 4,
                    "version": countdown["version"],
                }
            }
        },
    )
    assert unauthorized.status_code == 401
    assert unauthorized.json()["ok"] is False

    headers = _admin_headers(client)
    updated = client.patch(
        "/api/v1/settings",
        headers=headers,
        json={
            "request_id": "settings-update-1",
            "changes": {
                "timer.countdown_seconds": {
                    "value": 4,
                    "version": countdown["version"],
                }
            },
        },
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["timer.countdown_seconds"]["value"] == 4
    assert updated.json()["data"]["timer.countdown_seconds"]["version"] == countdown["version"] + 1

    stale = client.patch(
        "/api/v1/settings",
        headers=headers,
        json={
            "changes": {
                "timer.countdown_seconds": {
                    "value": 5,
                    "version": countdown["version"],
                }
            }
        },
    )
    assert stale.status_code == 409

    invalid = client.patch(
        "/api/v1/settings",
        headers=headers,
        json={
            "request_id": "settings-invalid-1",
            "changes": {
                "timer.countdown_seconds": {
                    "value": 99,
                    "version": countdown["version"] + 1,
                }
            },
        },
    )
    assert invalid.status_code == 422

    with SessionLocal() as db:
        setting = db.get(Setting, "timer.countdown_seconds")
        event = db.scalar(select(SystemEvent).where(SystemEvent.category == "CONFIG"))

    assert setting is not None
    assert setting.value_json == "4"
    assert setting.pending_value_json == "99"
    assert setting.validation_status == "INVALID"
    assert event is not None

    rolled_back = client.post(
        "/api/v1/settings/timer.countdown_seconds/rollback",
        headers=headers,
        json={"request_id": "settings-rollback-1", "reason": "test rollback"},
    )
    assert rolled_back.status_code == 200
    assert rolled_back.json()["data"]["value"] == 3

    reset_engine_for_tests()


def test_backup_logs_and_system_events_routes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    reset_engine_for_tests()
    settings = _settings_for(tmp_path / "timer.sqlite")
    initialize_database(settings)
    (tmp_path / "data/logs").mkdir(parents=True)
    (tmp_path / "data/logs/app.log").write_text("first\nsecond\n", encoding="utf-8")
    client = _agent_h_client(settings)
    headers = _admin_headers(client)

    backup = client.post("/api/v1/ops/backups", headers=headers, json={})
    assert backup.status_code == 200
    backup_path = tmp_path / backup.json()["data"]["path"]
    assert backup_path.exists()
    assert backup.json()["data"]["filename"].startswith("dynasty_ninja_timer_")

    listed = client.get("/api/v1/ops/backups", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["data"][0]["filename"] == backup.json()["data"]["filename"]

    logs = client.get("/api/v1/ops/logs/app.log", headers=headers, params={"lines": 1})
    assert logs.status_code == 200
    assert logs.json()["data"]["lines"] == ["second\n"]

    invalid_log = client.get("/api/v1/ops/logs/..%5Csettings.yaml", headers=headers)
    assert invalid_log.status_code == 400

    events = client.get("/api/v1/ops/system-events", headers=headers)
    assert events.status_code == 200

    reset_engine_for_tests()


def test_runs_csv_export_uses_v1_columns(tmp_path):
    reset_engine_for_tests()
    settings = _settings_for(tmp_path / "timer.sqlite")
    initialize_database(settings)
    client = _agent_h_client(settings)

    with SessionLocal() as db:
        course = db.scalar(select(Course).where(Course.slug == "speed-gauntlet"))
        assert course is not None
        revision = db.scalar(select(CourseRevision).where(CourseRevision.course_id == course.id))
        assert revision is not None
        now = utc_now()
        RunRepository(db).create(
            session_id=None,
            athlete_id=None,
            queue_entry_id=None,
            course_id=course.id,
            course_revision_id=revision.id,
            runner_name_snapshot="Avery",
            age_group_snapshot="9-11",
            course_name_snapshot=course.name,
            course_revision_snapshot=revision.revision_name,
            mode="OPEN_GYM",
            status="VALID",
            started_at=now,
            finished_at=now,
            elapsed_ms=61234,
            start_monotonic_ns=1,
            finish_monotonic_ns=2,
            start_source="TEST",
            finish_source="TEST",
            source="TEST",
            false_start_ms=None,
            reaction_ms=None,
            notes="clean",
            deleted_at=None,
            deleted_reason=None,
        )
        db.commit()

    export = client.get("/api/v1/runs/export.csv")
    assert export.status_code == 200
    assert export.text.splitlines()[0] == (
        "run_id,runner_name,age_group,course,mode,status,started_at,finished_at,"
        "elapsed_ms,elapsed_display,source,notes"
    )
    assert "1:01.234" in export.text

    reset_engine_for_tests()

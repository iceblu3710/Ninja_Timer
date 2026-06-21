from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api import routes_auth, routes_courses
from app.api.auth import AdminAuthError, admin_auth_exception_handler
from app.config import get_settings
from app.db.database import SessionLocal, get_db, initialize_database, reset_engine_for_tests
from app.db.models import Course, CourseRevision


def _settings_for(db_path):
    return SimpleNamespace(
        database_url=f"sqlite:///{db_path}",
        database_echo=False,
        admin_pin="2468",
        admin_session_seconds=3600,
        app_version="test",
    )


def _client(settings):
    app = FastAPI()
    app.include_router(routes_auth.router)
    app.include_router(routes_courses.router)
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


def test_course_api_lists_creates_and_designs_layout_revisions(tmp_path):
    reset_engine_for_tests()
    settings = _settings_for(tmp_path / "timer.sqlite")
    initialize_database(settings)
    client = _client(settings)

    listed = client.get("/api/v1/courses")
    assert listed.status_code == 200
    assert {course["slug"] for course in listed.json()["data"]} == {
        "speed-gauntlet",
        "ninja-challenge",
    }

    unauthorized = client.post("/api/v1/courses", json={"name": "Warp Wall Sprint"})
    assert unauthorized.status_code == 401

    headers = _admin_headers(client)
    created = client.post(
        "/api/v1/courses",
        headers=headers,
        json={
            "name": "Warp Wall Sprint",
            "description": "Short sprint format",
            "first_revision_name": "Week 1 speed build",
            "layout_notes": "Start gate, balance beam, wall, finish button",
            "obstacle_count": 4,
        },
    )
    assert created.status_code == 200
    course = created.json()["data"]
    assert course["slug"] == "warp-wall-sprint"
    assert course["open_revision"]["revision_name"] == "Week 1 speed build"
    assert course["open_revision"]["obstacle_count"] == 4

    renamed = client.patch(
        f"/api/v1/courses/{course['id']}",
        headers=headers,
        json={"name": "Warp Wall Sprint Pro"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["data"]["name"] == "Warp Wall Sprint Pro"

    next_revision = client.post(
        f"/api/v1/courses/{course['id']}/revisions",
        headers=headers,
        json={
            "revision_name": "Week 2 finals layout",
            "layout_notes": "Add cliffhanger before wall",
            "obstacle_count": 5,
            "close_current_revision": True,
        },
    )
    assert next_revision.status_code == 200
    assert next_revision.json()["data"]["revision_name"] == "Week 2 finals layout"

    revisions = client.get(f"/api/v1/courses/{course['id']}/revisions")
    assert revisions.status_code == 200
    rows = revisions.json()["data"]
    assert len(rows) == 2
    assert sum(1 for row in rows if row["revision_end_date"] is None and row["active"]) == 1

    with SessionLocal() as db:
        stored = db.scalar(select(Course).where(Course.slug == "warp-wall-sprint"))
        assert stored is not None
        revisions_for_course = db.scalars(
            select(CourseRevision).where(CourseRevision.course_id == stored.id)
        )
        revision_count = len(list(revisions_for_course))

    assert stored.name == "Warp Wall Sprint Pro"
    assert revision_count == 2
    reset_engine_for_tests()

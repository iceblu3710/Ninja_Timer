from types import SimpleNamespace

from sqlalchemy import func, select, text

from app.db.database import SessionLocal, get_engine, initialize_database, reset_engine_for_tests
from app.db.models import Course, CourseRevision, QueueEntry, SessionModel
from app.db.schemas import QueueEntryCreate
from app.services.queue_service import add_queue_entry


def _settings_for(db_path):
    return SimpleNamespace(database_url=f"sqlite:///{db_path}", database_echo=False)


def test_empty_database_initializes_and_seeds_idempotently(tmp_path):
    reset_engine_for_tests()
    settings = _settings_for(tmp_path / "timer.sqlite")

    initialize_database(settings)
    initialize_database(settings)

    with SessionLocal() as db:
        course_count = db.scalar(select(func.count()).select_from(Course))
        revision_count = db.scalar(select(func.count()).select_from(CourseRevision))
        session_count = db.scalar(select(func.count()).select_from(SessionModel))
        slugs = set(db.scalars(select(Course.slug)).all())

    assert slugs == {"speed-gauntlet", "ninja-challenge"}
    assert course_count == 2
    assert revision_count == 2
    assert session_count == 1

    reset_engine_for_tests()


def test_sqlite_pragmas_are_enabled(tmp_path):
    reset_engine_for_tests()
    settings = _settings_for(tmp_path / "timer.sqlite")
    initialize_database(settings)

    engine = get_engine(settings)
    with engine.connect() as connection:
        foreign_keys = connection.execute(text("PRAGMA foreign_keys")).scalar_one()
        busy_timeout = connection.execute(text("PRAGMA busy_timeout")).scalar_one()

    assert foreign_keys == 1
    assert busy_timeout == 5000

    reset_engine_for_tests()


def test_queue_request_id_is_idempotent_and_persists_after_restart(tmp_path):
    reset_engine_for_tests()
    settings = _settings_for(tmp_path / "timer.sqlite")
    initialize_database(settings)

    payload = QueueEntryCreate(
        request_id="kiosk-submit-1",
        runner_name="Avery",
        age_group="U12",
        course_slug="speed-gauntlet",
    )

    with SessionLocal() as db:
        first = add_queue_entry(db, payload)
        db.commit()
        first_id = first.id

    with SessionLocal() as db:
        second = add_queue_entry(db, payload)
        db.commit()
        second_id = second.id
        queue_count = db.scalar(select(func.count()).select_from(QueueEntry))

    assert second_id == first_id
    assert queue_count == 1

    reset_engine_for_tests()
    initialize_database(settings)

    with SessionLocal() as db:
        restored = db.scalar(select(QueueEntry).where(QueueEntry.request_id == "kiosk-submit-1"))

    assert restored is not None
    assert restored.runner_name_snapshot == "Avery"

    reset_engine_for_tests()


def test_queue_uses_course_default_mode_when_mode_is_omitted(tmp_path):
    reset_engine_for_tests()
    settings = _settings_for(tmp_path / "timer.sqlite")
    initialize_database(settings)

    with SessionLocal() as db:
        course = db.scalar(select(Course).where(Course.slug == "speed-gauntlet"))
        assert course is not None
        course.default_mode = "PARTY"
        entry = add_queue_entry(
            db,
            QueueEntryCreate(
                request_id="course-default-mode",
                runner_name="Avery",
                age_group="U12",
                course_slug="speed-gauntlet",
            ),
        )
        db.commit()
        entry_id = entry.id

    with SessionLocal() as db:
        stored = db.get(QueueEntry, entry_id)

    assert stored is not None
    assert stored.mode == "PARTY"

    reset_engine_for_tests()

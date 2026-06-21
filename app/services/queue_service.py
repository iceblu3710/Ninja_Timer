"""Queue/session persistence services."""
from sqlalchemy.orm import Session

from app.db.models import SessionModel
from app.db.repositories import CourseRepository, QueueRepository, SessionRepository
from app.db.schemas import QueueEntryCreate


def seed_active_session(db: Session) -> SessionModel:
    """Ensure there is one active Open Gym session."""
    repository = SessionRepository(db)
    active_session = repository.get_active()
    if active_session is not None:
        return active_session
    return repository.create_active_open_gym()


def add_queue_entry(db: Session, payload: QueueEntryCreate):
    """Create or return an idempotent waiting queue entry."""
    course_repository = CourseRepository(db)
    queue_repository = QueueRepository(db)
    session = seed_active_session(db) if payload.session_id is None else None
    session_id = payload.session_id if payload.session_id is not None else session.id

    course = course_repository.get_by_slug(payload.course_slug)
    if course is None:
        raise ValueError(f"Unknown course slug: {payload.course_slug}")
    revision = course_repository.get_open_revision(course.id)

    return queue_repository.create_waiting(
        request_id=payload.request_id,
        session_id=session_id,
        runner_name=payload.runner_name,
        age_group=payload.age_group,
        course_id=course.id,
        course_revision_id=revision.id if revision is not None else None,
        mode=payload.mode,
        source=payload.source,
    )


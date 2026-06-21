"""Queue/session persistence services."""

from sqlalchemy.orm import Session

from app.db.models import CourseRevision, QueueEntry, SessionModel
from app.db.repositories import CourseRepository, QueueRepository, SessionRepository
from app.db.schemas import QueueEntryCreate, QueueEntryUpdate


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

    course = (
        course_repository.get_by_id(payload.course_id)
        if payload.course_id is not None
        else course_repository.get_by_slug(payload.course_slug or "")
    )
    if course is None:
        course_ref = payload.course_id if payload.course_id is not None else payload.course_slug
        raise ValueError(f"Unknown course: {course_ref}")

    revision = (
        db.get(CourseRevision, payload.course_revision_id)
        if payload.course_revision_id is not None
        else course_repository.get_open_revision(course.id)
    )
    if revision is not None and revision.course_id != course.id:
        raise ValueError("Course revision does not belong to the selected course")

    return queue_repository.create_waiting(
        request_id=payload.request_id,
        session_id=session_id,
        runner_name=payload.display_name,
        age_group=payload.age_group,
        course_id=course.id,
        course_revision_id=revision.id if revision is not None else None,
        mode=payload.mode or course.default_mode,
        source=payload.source,
    )


def active_queue(
    db: Session,
    *,
    session_id: int | None = None,
    status: str | None = None,
    limit: int = 50,
) -> list[QueueEntry]:
    return QueueRepository(db).list_active_queue(
        session_id=session_id,
        status=status,
        limit=limit,
    )


def cancel_queue_entry(db: Session, queue_entry_id: int) -> QueueEntry | None:
    return QueueRepository(db).cancel(queue_entry_id)


def update_queue_entry(
    db: Session,
    queue_entry_id: int,
    payload: QueueEntryUpdate,
) -> QueueEntry | None:
    repository = QueueRepository(db)
    entry = repository.get(queue_entry_id)
    if entry is None:
        return None
    return repository.update(
        entry,
        expected_version=payload.version,
        position=payload.position,
        status=payload.status,
    )


def recover_queue(db: Session, policy: str) -> list[QueueEntry]:
    return QueueRepository(db).recover_active(policy)

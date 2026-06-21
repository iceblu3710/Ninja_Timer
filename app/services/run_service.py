"""Run persistence helpers."""

from sqlalchemy.orm import Session

from app.db.models import Run
from app.db.repositories import RunRepository


def save_run(db: Session, **values) -> Run:
    """Persist a run snapshot."""
    return RunRepository(db).create(**values)


def recent_runs(
    db: Session,
    *,
    limit: int = 10,
    session_id: int | None = None,
    course_id: int | None = None,
    course_revision_id: int | None = None,
    mode: str | None = None,
    status: str | None = None,
) -> list[Run]:
    return RunRepository(db).recent(
        limit=limit,
        session_id=session_id,
        course_id=course_id,
        course_revision_id=course_revision_id,
        mode=mode,
        status=status,
    )


def soft_delete_run(db: Session, run_id: int, reason: str | None = None) -> Run | None:
    return RunRepository(db).soft_delete(run_id, reason=reason)

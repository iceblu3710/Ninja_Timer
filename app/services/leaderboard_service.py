"""Leaderboard query helpers backed by persisted runs."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Run


def fastest_runs(
    db: Session,
    *,
    course_revision_id: int | None = None,
    course_id: int | None = None,
    age_group: str | None = None,
    mode: str | None = None,
    limit: int = 10,
) -> list[Run]:
    """Return fastest valid, non-deleted runs for leaderboard display."""
    statement = select(Run).where(
        Run.status == "VALID",
        Run.deleted_at.is_(None),
        Run.elapsed_ms.is_not(None),
    )
    if course_revision_id is not None:
        statement = statement.where(Run.course_revision_id == course_revision_id)
    if course_id is not None:
        statement = statement.where(Run.course_id == course_id)
    if age_group is not None:
        statement = statement.where(Run.age_group_snapshot == age_group)
    if mode is not None:
        statement = statement.where(Run.mode == mode)
    statement = statement.order_by(Run.elapsed_ms.asc(), Run.created_at.asc()).limit(limit)
    return list(db.scalars(statement))


"""Leaderboard query helpers backed by persisted runs."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Run
from app.db.repositories import CourseRepository, today_utc_date


def fastest_runs(
    db: Session,
    *,
    course_revision_id: int | None = None,
    course_id: int | None = None,
    athlete_id: int | None = None,
    age_group: str | None = None,
    mode: str | None = None,
    today_only: bool = False,
    limit: int = 10,
) -> list[Run]:
    """Return fastest valid, non-deleted runs for leaderboard display."""
    if course_revision_id is None and course_id is not None:
        revision = CourseRepository(db).get_open_revision(course_id)
        course_revision_id = revision.id if revision is not None else None

    statement = select(Run).where(
        Run.status == "VALID",
        Run.deleted_at.is_(None),
        Run.elapsed_ms.is_not(None),
    )
    if course_revision_id is not None:
        statement = statement.where(Run.course_revision_id == course_revision_id)
    if course_id is not None:
        statement = statement.where(Run.course_id == course_id)
    if athlete_id is not None:
        statement = statement.where(Run.athlete_id == athlete_id)
    if age_group is not None:
        statement = statement.where(Run.age_group_snapshot == age_group)
    if mode is not None:
        statement = statement.where(Run.mode == mode)
    if today_only:
        statement = statement.where(Run.created_at >= f"{today_utc_date()}T")
    statement = statement.order_by(Run.elapsed_ms.asc(), Run.created_at.asc()).limit(limit)
    return list(db.scalars(statement))

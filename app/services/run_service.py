"""Run persistence helpers."""
from sqlalchemy.orm import Session

from app.db.models import Run
from app.db.repositories import RunRepository


def save_run(db: Session, **values) -> Run:
    """Persist a run snapshot."""
    return RunRepository(db).create(**values)


def recent_runs(db: Session, limit: int = 10) -> list[Run]:
    return RunRepository(db).recent(limit=limit)


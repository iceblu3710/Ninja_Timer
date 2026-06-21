"""Leaderboard API routes."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Run
from app.services.leaderboard_service import fastest_runs

router = APIRouter(prefix="/api/v1/leaderboards", tags=["leaderboards"])


def _ok(data: object) -> dict:
    return {"ok": True, "data": data}


def _leaderboard_row(run: Run, rank: int) -> dict:
    return {
        "rank": rank,
        "run_id": run.id,
        "runner_name": run.runner_name_snapshot,
        "age_group": run.age_group_snapshot,
        "course_id": run.course_id,
        "course_revision_id": run.course_revision_id,
        "course_name": run.course_name_snapshot,
        "course_revision": run.course_revision_snapshot,
        "mode": run.mode,
        "elapsed_ms": run.elapsed_ms,
        "finished_at": run.finished_at,
        "created_at": run.created_at,
    }


def _leaderboard_response(runs: list[Run]) -> dict:
    return _ok([_leaderboard_row(run, index + 1) for index, run in enumerate(runs)])


@router.get("/today")
async def get_today_leaderboard(
    course_id: int | None = None,
    course_revision_id: int | None = None,
    age_group: str | None = None,
    mode: str | None = None,
    limit: int = Query(default=10, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict:
    runs = fastest_runs(
        db,
        course_id=course_id,
        course_revision_id=course_revision_id,
        age_group=age_group,
        mode=mode,
        today_only=True,
        limit=limit,
    )
    return _leaderboard_response(runs)


@router.get("/all-time")
async def get_all_time_leaderboard(
    course_id: int | None = None,
    course_revision_id: int | None = None,
    age_group: str | None = None,
    mode: str | None = None,
    limit: int = Query(default=10, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict:
    runs = fastest_runs(
        db,
        course_id=course_id,
        course_revision_id=course_revision_id,
        age_group=age_group,
        mode=mode,
        today_only=False,
        limit=limit,
    )
    return _leaderboard_response(runs)


@router.get("/personal-bests")
async def get_personal_bests(
    athlete_id: int | None = None,
    course_id: int | None = None,
    course_revision_id: int | None = None,
    age_group: str | None = None,
    mode: str | None = None,
    limit: int = Query(default=10, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict:
    runs = fastest_runs(
        db,
        athlete_id=athlete_id,
        course_id=course_id,
        course_revision_id=course_revision_id,
        age_group=age_group,
        mode=mode,
        today_only=False,
        limit=limit,
    )
    return _leaderboard_response(runs)

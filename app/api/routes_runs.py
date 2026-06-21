"""Runs API routes."""

import csv
from io import StringIO

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import require_admin
from app.api.response_models import run_response
from app.db.database import get_db
from app.db.models import Run
from app.db.repositories import AuditRepository, RunRepository
from app.db.schemas import RunDeleteRequest, RunUpdate
from app.services.event_bus import event_bus
from app.services.run_service import recent_runs, soft_delete_run

router = APIRouter(prefix="/api/v1/runs", tags=["runs"])


def _ok(data: object) -> dict:
    return {"ok": True, "data": data}


def _error(http_status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=http_status,
        content={"ok": False, "error": {"code": code, "message": message}},
    )


@router.get("/recent")
async def get_recent_runs(
    limit: int = Query(default=10, ge=1, le=200),
    session_id: int | None = None,
    course_id: int | None = None,
    course_revision_id: int | None = None,
    mode: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
) -> dict:
    runs = recent_runs(
        db,
        limit=limit,
        session_id=session_id,
        course_id=course_id,
        course_revision_id=course_revision_id,
        mode=mode,
        status=status_filter,
    )
    return _ok([run_response(run) for run in runs])


@router.get("/export.csv")
async def export_runs_csv(
    from_date: str | None = Query(default=None, alias="from"),
    to_date: str | None = None,
    session_id: int | None = None,
    course_id: int | None = None,
    course_revision_id: int | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
) -> Response:
    statement = select(Run).where(Run.deleted_at.is_(None))
    if from_date is not None:
        statement = statement.where(Run.created_at >= f"{from_date}T")
    if to_date is not None:
        statement = statement.where(Run.created_at < f"{to_date}T")
    if session_id is not None:
        statement = statement.where(Run.session_id == session_id)
    if course_id is not None:
        statement = statement.where(Run.course_id == course_id)
    if course_revision_id is not None:
        statement = statement.where(Run.course_revision_id == course_revision_id)
    if status_filter is not None:
        statement = statement.where(Run.status == status_filter)
    statement = statement.order_by(Run.created_at.asc())

    output = StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(
        [
            "run_id",
            "runner_name",
            "age_group",
            "course",
            "mode",
            "status",
            "started_at",
            "finished_at",
            "elapsed_ms",
            "elapsed_display",
            "source",
            "notes",
        ]
    )
    for run in db.scalars(statement):
        writer.writerow(
            [
                run.id,
                run.runner_name_snapshot,
                run.age_group_snapshot,
                run.course_name_snapshot,
                run.mode,
                run.status,
                run.started_at,
                run.finished_at,
                run.elapsed_ms,
                _elapsed_display(run.elapsed_ms),
                run.source,
                run.notes,
            ]
        )

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=runs.csv"},
    )


def _elapsed_display(elapsed_ms: int | None) -> str:
    if elapsed_ms is None:
        return ""
    minutes, remainder = divmod(elapsed_ms, 60_000)
    seconds, milliseconds = divmod(remainder, 1_000)
    if minutes:
        return f"{minutes}:{seconds:02}.{milliseconds:03}"
    return f"{seconds}.{milliseconds:03}"


@router.get("/{run_id}")
async def get_run(run_id: int, db: Session = Depends(get_db)):
    run = RunRepository(db).get(run_id)
    if run is None or run.deleted_at is not None:
        return _error(status.HTTP_404_NOT_FOUND, "NOT_FOUND", f"Run {run_id} was not found.")
    return _ok(run_response(run))


@router.patch("/{run_id}")
async def update_run(
    run_id: int,
    payload: RunUpdate,
    db: Session = Depends(get_db),
    actor: str = Depends(require_admin),
):
    repository = RunRepository(db)
    run = repository.get(run_id)
    if run is None or run.deleted_at is not None:
        db.rollback()
        return _error(status.HTTP_404_NOT_FOUND, "NOT_FOUND", f"Run {run_id} was not found.")

    values: dict[str, str | None] = {}
    if payload.runner_name is not None:
        values["runner_name_snapshot"] = payload.runner_name.strip()
    if payload.age_group is not None:
        values["age_group_snapshot"] = payload.age_group
    if payload.status is not None:
        values["status"] = payload.status
    if payload.notes is not None:
        values["notes"] = payload.notes

    if values:
        repository.update(run, **values)
        AuditRepository(db).record(
            actor=actor,
            action="UPDATE_RUN",
            target_type="run",
            target_id=run.id,
        )
    db.commit()
    data = run_response(run)
    await event_bus.publish("run.saved", {"run": data})
    await event_bus.publish("leaderboard.updated", {"run_id": run.id})
    return _ok(data)


@router.delete("/{run_id}")
async def delete_run(
    run_id: int,
    payload: RunDeleteRequest | None = None,
    db: Session = Depends(get_db),
    actor: str = Depends(require_admin),
):
    run = soft_delete_run(db, run_id, reason=payload.reason if payload is not None else None)
    if run is None:
        db.rollback()
        return _error(status.HTTP_404_NOT_FOUND, "NOT_FOUND", f"Run {run_id} was not found.")
    AuditRepository(db).record(
        actor=actor,
        action="DELETE_RUN",
        target_type="run",
        target_id=run.id,
    )
    db.commit()
    data = run_response(run)
    await event_bus.publish("leaderboard.updated", {"run_id": run.id, "deleted": True})
    await event_bus.publish("run.saved", {"run": data})
    return _ok(data)

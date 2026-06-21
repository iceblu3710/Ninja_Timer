"""Timer API routes."""
from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.schemas import (
    TimerArmRequest,
    TimerDeleteLastRunRequest,
    TimerDnfRequest,
    TimerResetRequest,
    TimerSourceRequest,
    TimerStateRead,
    TimerStopRequest,
)
from app.services.timer_service import (
    TimerNotFoundError,
    TimerService,
    TimerServiceError,
    get_timer_service,
)

router = APIRouter(prefix="/api/v1/timer", tags=["timer"])


def _ok(data: TimerStateRead) -> dict:
    return {"ok": True, "data": data.model_dump()}


def _timer_error(exc: TimerServiceError) -> JSONResponse:
    http_status = status.HTTP_404_NOT_FOUND if exc.code == "NOT_FOUND" else status.HTTP_409_CONFLICT
    return JSONResponse(
        status_code=http_status,
        content={
            "ok": False,
            "error": {
                "code": exc.code,
                "message": str(exc),
            },
        },
    )


@router.get("/state")
async def get_timer_state(
    service: TimerService = Depends(get_timer_service),
) -> dict:
    return _ok(service.get_state())


@router.post("/arm")
async def arm_timer(
    payload: TimerArmRequest,
    db: Session = Depends(get_db),
    service: TimerService = Depends(get_timer_service),
) -> dict:
    try:
        state = service.arm(db, payload)
        db.commit()
        return _ok(state)
    except (TimerNotFoundError, TimerServiceError) as exc:
        db.rollback()
        return _timer_error(exc)


@router.post("/start")
async def start_timer(
    payload: TimerSourceRequest,
    service: TimerService = Depends(get_timer_service),
) -> dict:
    try:
        return _ok(service.start(source=payload.source))
    except TimerServiceError as exc:
        return _timer_error(exc)


@router.post("/finish")
async def finish_timer(
    payload: TimerSourceRequest,
    db: Session = Depends(get_db),
    service: TimerService = Depends(get_timer_service),
) -> dict:
    try:
        state = service.finish(db, source=payload.source)
        db.commit()
        return _ok(state)
    except TimerServiceError as exc:
        db.rollback()
        return _timer_error(exc)


@router.post("/stop")
async def stop_timer(
    payload: TimerStopRequest,
    db: Session = Depends(get_db),
    service: TimerService = Depends(get_timer_service),
) -> dict:
    try:
        state = service.stop(db, status=payload.status, source=payload.source, notes=payload.notes)
        db.commit()
        return _ok(state)
    except TimerServiceError as exc:
        db.rollback()
        return _timer_error(exc)


@router.post("/reset")
async def reset_timer(
    payload: TimerResetRequest,
    service: TimerService = Depends(get_timer_service),
) -> dict:
    try:
        return _ok(service.reset(clear_active_runner=payload.clear_active_runner))
    except TimerServiceError as exc:
        return _timer_error(exc)


@router.post("/dnf")
async def dnf_timer(
    payload: TimerDnfRequest,
    db: Session = Depends(get_db),
    service: TimerService = Depends(get_timer_service),
) -> dict:
    try:
        state = service.dnf(db, notes=payload.notes, source=payload.source)
        db.commit()
        return _ok(state)
    except TimerServiceError as exc:
        db.rollback()
        return _timer_error(exc)


@router.post("/delete-last-run")
async def delete_last_run(
    payload: TimerDeleteLastRunRequest,
    db: Session = Depends(get_db),
    service: TimerService = Depends(get_timer_service),
) -> dict:
    try:
        state = service.delete_last_run(db, reason=payload.reason)
        db.commit()
        return _ok(state)
    except TimerServiceError as exc:
        db.rollback()
        return _timer_error(exc)

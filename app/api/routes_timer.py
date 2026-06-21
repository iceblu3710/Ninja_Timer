"""Timer API routes."""

import asyncio

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.auth import require_admin
from app.api.response_models import run_response
from app.db.database import get_db
from app.db.repositories import RunRepository
from app.db.schemas import (
    TimerArmRequest,
    TimerDeleteLastRunRequest,
    TimerDnfRequest,
    TimerResetRequest,
    TimerSourceRequest,
    TimerStateRead,
    TimerStopRequest,
)
from app.services.event_bus import event_bus
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


async def _publish_timer_state(state: TimerStateRead) -> None:
    await event_bus.publish("timer.state", state.model_dump())


async def _publish_run_events(db: Session, run_id: int | None) -> None:
    if run_id is None:
        return
    run = RunRepository(db).get(run_id)
    if run is None:
        return
    data = run_response(run)
    await event_bus.publish("run.saved", {"run": data})
    if run.status == "VALID":
        await event_bus.publish("leaderboard.updated", {"run_id": run.id})


async def _complete_countdown_later(
    service: TimerService,
    *,
    token: int,
    delay_ms: int,
    source: str,
) -> None:
    await asyncio.sleep(delay_ms / 1000)
    state = service.complete_countdown(token=token, source=source)
    await _publish_timer_state(state)


@router.get("/state")
async def get_timer_state(
    service: TimerService = Depends(get_timer_service),
) -> dict:
    return _ok(service.get_state())


@router.post("/arm")
async def arm_timer(
    payload: TimerArmRequest = TimerArmRequest(),
    db: Session = Depends(get_db),
    service: TimerService = Depends(get_timer_service),
    _actor: str = Depends(require_admin),
) -> dict:
    try:
        state = service.arm(db, payload)
        db.commit()
        await _publish_timer_state(state)
        await event_bus.publish("queue.updated", {"source": "timer.arm"})
        return _ok(state)
    except (TimerNotFoundError, TimerServiceError) as exc:
        db.rollback()
        return _timer_error(exc)


@router.post("/start")
async def start_timer(
    payload: TimerSourceRequest = TimerSourceRequest(),
    service: TimerService = Depends(get_timer_service),
    _actor: str = Depends(require_admin),
) -> dict:
    try:
        state = service.start(source=payload.source)
        await _publish_timer_state(state)
        if (
            state.state == "COUNTDOWN"
            and state.countdown_token is not None
            and state.countdown_remaining_ms is not None
        ):
            asyncio.create_task(
                _complete_countdown_later(
                    service,
                    token=state.countdown_token,
                    delay_ms=state.countdown_remaining_ms,
                    source=payload.source,
                )
            )
        return _ok(state)
    except TimerServiceError as exc:
        return _timer_error(exc)


@router.post("/finish")
async def finish_timer(
    payload: TimerSourceRequest = TimerSourceRequest(),
    db: Session = Depends(get_db),
    service: TimerService = Depends(get_timer_service),
    _actor: str = Depends(require_admin),
) -> dict:
    try:
        state = service.finish(db, source=payload.source)
        db.commit()
        await _publish_timer_state(state)
        await event_bus.publish("queue.updated", {"source": "timer.finish"})
        await _publish_run_events(db, state.run_id)
        return _ok(state)
    except TimerServiceError as exc:
        db.rollback()
        return _timer_error(exc)


@router.post("/stop")
async def stop_timer(
    payload: TimerStopRequest = TimerStopRequest(),
    db: Session = Depends(get_db),
    service: TimerService = Depends(get_timer_service),
    _actor: str = Depends(require_admin),
) -> dict:
    try:
        state = service.stop(db, status=payload.status, source=payload.source, notes=payload.notes)
        db.commit()
        await _publish_timer_state(state)
        await event_bus.publish("queue.updated", {"source": "timer.stop"})
        await _publish_run_events(db, state.run_id)
        return _ok(state)
    except TimerServiceError as exc:
        db.rollback()
        return _timer_error(exc)


@router.post("/reset")
async def reset_timer(
    payload: TimerResetRequest = TimerResetRequest(),
    db: Session = Depends(get_db),
    service: TimerService = Depends(get_timer_service),
    _actor: str = Depends(require_admin),
) -> dict:
    try:
        state = service.reset(db, clear_active_runner=payload.clear_active_runner)
        db.commit()
        await _publish_timer_state(state)
        await event_bus.publish("queue.updated", {"source": "timer.reset"})
        return _ok(state)
    except TimerServiceError as exc:
        db.rollback()
        return _timer_error(exc)


@router.post("/accept")
async def accept_timer(
    payload: TimerSourceRequest = TimerSourceRequest(),
    db: Session = Depends(get_db),
    service: TimerService = Depends(get_timer_service),
    _actor: str = Depends(require_admin),
) -> dict:
    try:
        state, run_id = service.accept(db, source=payload.source)
        db.commit()
        await _publish_timer_state(state)
        await event_bus.publish("queue.updated", {"source": "timer.accept"})
        if run_id is not None:
            await _publish_run_events(db, run_id)
        return _ok(state)
    except TimerServiceError as exc:
        db.rollback()
        return _timer_error(exc)


@router.post("/dnf")
async def dnf_timer(
    payload: TimerDnfRequest = TimerDnfRequest(),
    db: Session = Depends(get_db),
    service: TimerService = Depends(get_timer_service),
    _actor: str = Depends(require_admin),
) -> dict:
    try:
        state = service.dnf(db, notes=payload.notes, source=payload.source)
        db.commit()
        await _publish_timer_state(state)
        await event_bus.publish("queue.updated", {"source": "timer.dnf"})
        await _publish_run_events(db, state.run_id)
        return _ok(state)
    except TimerServiceError as exc:
        db.rollback()
        return _timer_error(exc)


@router.post("/delete-last-run")
async def delete_last_run(
    payload: TimerDeleteLastRunRequest = TimerDeleteLastRunRequest(),
    db: Session = Depends(get_db),
    service: TimerService = Depends(get_timer_service),
    _actor: str = Depends(require_admin),
) -> dict:
    try:
        run = RunRepository(db).most_recent()
        state = service.delete_last_run(db, reason=payload.reason)
        db.commit()
        await _publish_timer_state(state)
        if run is not None:
            data = run_response(run)
            await event_bus.publish("run.saved", {"run": data})
            await event_bus.publish("leaderboard.updated", {"run_id": run.id, "deleted": True})
        return _ok(state)
    except TimerServiceError as exc:
        db.rollback()
        return _timer_error(exc)


@router.post("/obstacles/{index}/toggle")
async def toggle_timer_obstacle(
    index: int,
    db: Session = Depends(get_db),
    service: TimerService = Depends(get_timer_service),
    _actor: str = Depends(require_admin),
) -> dict:
    try:
        state = service.toggle_obstacle(db, index)
        db.commit()
        await _publish_timer_state(state)
        if state.run_id is not None:
            await _publish_run_events(db, state.run_id)
        return _ok(state)
    except TimerServiceError as exc:
        db.rollback()
        return _timer_error(exc)

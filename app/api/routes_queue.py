"""Queue API routes."""

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.auth import require_admin
from app.api.response_models import queue_entry_response
from app.db.database import get_db
from app.db.repositories import AuditRepository, QueueRepository
from app.db.schemas import (
    QueueEntryCreate,
    QueueEntryUpdate,
    QueueRecoverRequest,
    QueueReorderRequest,
)
from app.services.event_bus import event_bus
from app.services.queue_service import (
    active_queue,
    add_queue_entry,
    cancel_queue_entry,
    recover_queue,
    update_queue_entry,
)

router = APIRouter(prefix="/api/v1/queue", tags=["queue"])


def _ok(data: object) -> dict:
    return {"ok": True, "data": data}


def _error(http_status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=http_status,
        content={"ok": False, "error": {"code": code, "message": message}},
    )


@router.get("")
async def get_queue(
    session_id: int | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict:
    entries = active_queue(db, session_id=session_id, status=status_filter, limit=limit)
    return _ok([queue_entry_response(db, entry) for entry in entries])


@router.post("")
async def create_queue_entry(
    payload: QueueEntryCreate,
    db: Session = Depends(get_db),
):
    try:
        entry = add_queue_entry(db, payload)
        db.commit()
        data = queue_entry_response(db, entry)
        await event_bus.publish("queue.updated", {"entry": data})
        return _ok(data)
    except ValueError as exc:
        db.rollback()
        return _error(status.HTTP_404_NOT_FOUND, "NOT_FOUND", str(exc))


@router.patch("/{queue_entry_id}")
async def patch_queue_entry(
    queue_entry_id: int,
    payload: QueueEntryUpdate,
    db: Session = Depends(get_db),
    actor: str = Depends(require_admin),
):
    try:
        entry = update_queue_entry(db, queue_entry_id, payload)
    except ValueError as exc:
        db.rollback()
        return _error(status.HTTP_409_CONFLICT, "STALE_VERSION", str(exc))

    if entry is None:
        db.rollback()
        return _error(
            status.HTTP_404_NOT_FOUND,
            "NOT_FOUND",
            f"Queue entry {queue_entry_id} was not found.",
        )

    AuditRepository(db).record(
        actor=actor,
        action="UPDATE_QUEUE_ENTRY",
        target_type="queue_entry",
        target_id=entry.id,
        request_id=payload.request_id,
    )
    db.commit()
    data = queue_entry_response(db, entry)
    await event_bus.publish("queue.updated", {"entry": data})
    return _ok(data)


@router.post("/recover")
async def recover_queue_entries(
    payload: QueueRecoverRequest,
    db: Session = Depends(get_db),
    actor: str = Depends(require_admin),
):
    try:
        entries = recover_queue(db, payload.policy)
    except ValueError as exc:
        db.rollback()
        return _error(status.HTTP_409_CONFLICT, "INVALID_POLICY", str(exc))

    AuditRepository(db).record(
        actor=actor,
        action="RECOVER_QUEUE",
        target_type="queue",
    )
    db.commit()
    data = [queue_entry_response(db, entry) for entry in entries]
    await event_bus.publish("queue.updated", {"entries": data})
    return _ok(data)


@router.delete("/{queue_entry_id}")
async def delete_queue_entry(
    queue_entry_id: int,
    db: Session = Depends(get_db),
    actor: str = Depends(require_admin),
):
    entry = cancel_queue_entry(db, queue_entry_id)
    if entry is None:
        db.rollback()
        return _error(
            status.HTTP_404_NOT_FOUND,
            "NOT_FOUND",
            f"Queue entry {queue_entry_id} was not found.",
        )
    AuditRepository(db).record(
        actor=actor,
        action="CANCEL_QUEUE_ENTRY",
        target_type="queue_entry",
        target_id=entry.id,
    )
    db.commit()
    data = queue_entry_response(db, entry)
    await event_bus.publish("queue.updated", {"entry": data})
    return _ok(data)


@router.post("/reorder")
async def reorder_queue(
    payload: QueueReorderRequest,
    db: Session = Depends(get_db),
    actor: str = Depends(require_admin),
):
    repository = QueueRepository(db)
    updated = repository.reorder_queue(payload.queue_entry_ids)
    AuditRepository(db).record(
        actor=actor,
        action="REORDER_QUEUE",
        target_type="queue",
    )
    db.commit()
    data = [queue_entry_response(db, entry) for entry in updated]
    await event_bus.publish("queue.updated", {"entries": data})
    return _ok(data)

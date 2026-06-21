"""Operations and gym-readiness API routes."""
from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.auth import require_admin
from app.config import Settings, get_settings
from app.db.database import get_db
from app.db.repositories import AuditRepository, SystemEventRepository
from app.db.schemas import BackupCreateRequest
from app.services.operations_service import (
    create_database_backup,
    list_database_backups,
    tail_log_file,
)

router = APIRouter(prefix="/api/v1/ops", tags=["operations"])


def _ok(data: object) -> dict:
    return {"ok": True, "data": data}


def _error(http_status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=http_status,
        content={"ok": False, "error": {"code": code, "message": message}},
    )


@router.post("/backups")
async def create_backup(
    payload: BackupCreateRequest | None = None,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    actor: str = Depends(require_admin),
):
    try:
        backup = create_database_backup(settings)
    except (FileNotFoundError, ValueError) as exc:
        return _error(status.HTTP_409_CONFLICT, "BACKUP_FAILED", str(exc))

    AuditRepository(db).record(
        actor=actor,
        action="CREATE_DATABASE_BACKUP",
        target_type="database",
        request_id=payload.request_id if payload is not None else None,
    )
    db.commit()
    return _ok(backup)


@router.get("/backups")
async def get_backups(actor: str = Depends(require_admin)) -> dict:
    _ = actor
    return _ok(list_database_backups())


@router.get("/logs/{filename}")
async def get_log_file(
    filename: str,
    lines: int = Query(default=200, ge=1, le=2000),
    actor: str = Depends(require_admin),
):
    _ = actor
    try:
        return _ok(tail_log_file(filename, lines=lines))
    except FileNotFoundError as exc:
        return _error(status.HTTP_404_NOT_FOUND, "NOT_FOUND", str(exc))


@router.get("/system-events")
async def get_system_events(
    limit: int = Query(default=100, ge=1, le=1000),
    category: str | None = None,
    level: str | None = None,
    db: Session = Depends(get_db),
    actor: str = Depends(require_admin),
) -> dict:
    _ = actor
    events = SystemEventRepository(db).recent(limit=limit, category=category, level=level)
    return _ok(
        [
            {
                "id": event.id,
                "level": event.level,
                "category": event.category,
                "source": event.source,
                "message": event.message,
                "payload_json": event.payload_json,
                "request_id": event.request_id,
                "created_at": event.created_at,
                "acknowledged_at": event.acknowledged_at,
            }
            for event in events
        ]
    )

"""Hardware status, simulation, ingest, and relay routes."""

from __future__ import annotations

from dataclasses import replace

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.auth import require_admin
from app.db.database import get_db
from app.db.schemas import (
    HardwareRawEventRequest,
    HardwareReconnectRequest,
    HardwareSimulateRequest,
    RelayActionRequest,
)
from app.services.hardware_service import (
    HardwareService,
    get_hardware_service,
    publish_hardware_result,
)
from app.services.relay_service import (
    RelayService,
    get_relay_service,
    publish_relay_action,
    relay_action_response,
)

router = APIRouter(prefix="/api/v1/hardware", tags=["hardware"])


@router.get("/status")
async def get_hardware_status(
    db: Session = Depends(get_db),
    service: HardwareService = Depends(get_hardware_service),
) -> dict:
    return {"ok": True, "data": service.status(db)}


@router.post("/reconnect")
async def reconnect_hardware(
    _payload: HardwareReconnectRequest = HardwareReconnectRequest(),
    db: Session = Depends(get_db),
    service: HardwareService = Depends(get_hardware_service),
    _actor: str = Depends(require_admin),
) -> dict:
    service.reconnect()
    return {"ok": True, "data": service.status(db)}


@router.post("/simulate")
async def simulate_hardware_event(
    payload: HardwareSimulateRequest,
    db: Session = Depends(get_db),
    service: HardwareService = Depends(get_hardware_service),
    _actor: str = Depends(require_admin),
) -> dict:
    try:
        normalized = service.simulate_event(payload.input_key, payload.state)
        result = service.process_event(db, normalized)
        db.commit()
        await publish_hardware_result(db, result)
        return {"ok": True, "data": result.as_dict()}
    except ValueError as exc:
        db.rollback()
        return _bad_request(exc)


@router.post("/events")
async def ingest_hardware_event(
    payload: HardwareRawEventRequest,
    db: Session = Depends(get_db),
    service: HardwareService = Depends(get_hardware_service),
    _actor: str = Depends(require_admin),
) -> dict:
    try:
        normalized = service.parse_raw_event(line=payload.line, payload=payload.payload)
        if payload.transport:
            normalized = replace(normalized, transport=payload.transport.upper())
        result = service.process_event(db, normalized)
        db.commit()
        await publish_hardware_result(db, result)
        return {"ok": True, "data": result.as_dict()}
    except ValueError as exc:
        db.rollback()
        return _bad_request(exc)


@router.post("/relay")
async def dispatch_relay(
    payload: RelayActionRequest,
    db: Session = Depends(get_db),
    service: RelayService = Depends(get_relay_service),
    actor: str = Depends(require_admin),
) -> dict:
    try:
        action = service.dispatch(
            db,
            action_key=payload.action_key,
            command=payload.command,
            target=payload.target,
            action=payload.action,
            duration_ms=payload.duration_ms,
            requested_by=payload.requested_by or actor,
            run_id=payload.run_id,
        )
        db.commit()
        await publish_relay_action(action)
        return {"ok": True, "data": relay_action_response(action)}
    except ValueError as exc:
        db.rollback()
        return _bad_request(exc)


def _bad_request(exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "ok": False,
            "error": {"code": "INVALID_HARDWARE_REQUEST", "message": str(exc)},
        },
    )

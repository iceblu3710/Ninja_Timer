"""WebSocket routes for live frontend updates."""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.event_bus import event_bus

router = APIRouter(prefix="/api/v1/ws", tags=["websocket"])


@router.websocket("/live")
async def live_updates(websocket: WebSocket) -> None:
    await event_bus.connect(websocket)
    try:
        await event_bus.publish(
            "system.toast",
            {"level": "info", "message": "Live updates connected"},
        )
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await event_bus.disconnect(websocket)

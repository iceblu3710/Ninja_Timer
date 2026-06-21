from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import routes_ws
from app.services.event_bus import event_bus


def test_websocket_broadcasts_live_events():
    app = FastAPI()
    app.include_router(routes_ws.router)

    @app.post("/emit")
    async def emit():
        await event_bus.publish("timer.state", {"state": "RUNNING"})
        return {"ok": True}

    client = TestClient(app)

    with client.websocket_connect("/api/v1/ws/live") as websocket:
        connected = websocket.receive_json()
        assert connected["type"] == "system.toast"

        response = client.post("/emit")
        assert response.status_code == 200
        message = websocket.receive_json()

    assert message["type"] == "timer.state"
    assert message["sent_at"].endswith("Z")
    assert message["data"]["state"] == "RUNNING"

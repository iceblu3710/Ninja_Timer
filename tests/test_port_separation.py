from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app


def test_port_separation_routes():
    app = create_app()
    settings = get_settings()

    # Create clients with base_urls on different ports
    client_admin = TestClient(app, base_url=f"http://testserver:{settings.port}")
    client_display = TestClient(app, base_url=f"http://testserver:{settings.scoreboard_port}")
    client_kiosk = TestClient(app, base_url=f"http://testserver:{settings.kiosk_port}")

    # 1. Test Admin Port (should have access to all pages)
    res_root = client_admin.get("/")
    assert res_root.status_code == 200
    assert "Admin Dashboard" in res_root.text

    res_admin = client_admin.get("/admin")
    assert res_admin.status_code == 200
    assert "Admin Dashboard" in res_admin.text

    res_display = client_admin.get("/display")
    assert res_display.status_code == 200
    assert "TV scoreboard display" in res_display.text

    res_kiosk = client_admin.get("/kiosk")
    assert res_kiosk.status_code == 200
    assert "Runner check-in kiosk" in res_kiosk.text

    # 2. Test Scoreboard Port (restricted from admin/kiosk)
    res_sb_root = client_display.get("/")
    assert res_sb_root.status_code == 200
    assert "TV scoreboard display" in res_sb_root.text
    assert "Admin Dashboard" not in res_sb_root.text

    res_sb_display = client_display.get("/display")
    assert res_sb_display.status_code == 200

    res_sb_admin = client_display.get("/admin")
    assert res_sb_admin.status_code == 403

    res_sb_kiosk = client_display.get("/kiosk")
    assert res_sb_kiosk.status_code == 403

    # 3. Test Kiosk Port (restricted from admin/display)
    res_k_root = client_kiosk.get("/")
    assert res_k_root.status_code == 200
    assert "Runner check-in kiosk" in res_k_root.text
    assert "Admin Dashboard" not in res_k_root.text

    res_k_kiosk = client_kiosk.get("/kiosk")
    assert res_k_kiosk.status_code == 200

    res_k_admin = client_kiosk.get("/admin")
    assert res_k_admin.status_code == 403

    res_k_display = client_kiosk.get("/display")
    assert res_k_display.status_code == 403


def test_static_files_port_restrictions():
    app = create_app()
    settings = get_settings()

    client_display = TestClient(app, base_url=f"http://testserver:{settings.scoreboard_port}")
    client_kiosk = TestClient(app, base_url=f"http://testserver:{settings.kiosk_port}")

    # Check that static html files themselves are restricted
    assert client_display.get("/static/admin.html").status_code == 403
    assert client_display.get("/static/kiosk.html").status_code == 403
    assert client_display.get("/static/display.html").status_code == 200

    assert client_kiosk.get("/static/admin.html").status_code == 403
    assert client_kiosk.get("/static/display.html").status_code == 403
    assert client_kiosk.get("/static/kiosk.html").status_code == 200

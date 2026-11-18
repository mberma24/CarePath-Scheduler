from fastapi.testclient import TestClient

from app.main import create_app


def test_health_endpoint():
    client = TestClient(create_app())
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_config_endpoint_returns_scheduling_settings():
    client = TestClient(create_app())
    response = client.get("/config")
    assert response.status_code == 200
    assert response.json() == {
        "slot_minutes": 15,
        "schedule_horizon_days": 1,
        "clinic_timezone": "America/New_York",
        "clinic_open_hour": 7,
        "clinic_close_hour": 19,
    }

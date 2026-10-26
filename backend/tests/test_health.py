from fastapi.testclient import TestClient

from teamtime.api.app import create_app


def test_health_reports_ok() -> None:
    response = TestClient(create_app()).get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

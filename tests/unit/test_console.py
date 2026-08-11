from fastapi.testclient import TestClient

from agent.fast_api_app import app

client = TestClient(app)


def test_supervisor_console_is_served() -> None:
    response = client.get("/console/")

    assert response.status_code == 200
    assert "Virtual Production Supervisor" in response.text
    assert "Human approval boundary" in response.text

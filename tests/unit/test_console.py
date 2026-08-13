from fastapi.testclient import TestClient

from agent.fast_api_app import app

client = TestClient(app)


def test_supervisor_console_is_served() -> None:
    response = client.get("/console/")

    assert response.status_code == 200
    assert "Virtual Production Supervisor" in response.text
    assert "Human approval boundary" in response.text
    assert 'id="admin-dialog"' in response.text
    assert 'app.js?v=2' in response.text
    assert response.headers["cache-control"] == "no-store, max-age=0"


def test_console_uses_inline_admin_authorization() -> None:
    response = client.get("/console/app.js")

    assert response.status_code == 200
    assert "showModal()" in response.text
    assert "prompt(" not in response.text
    assert response.headers["cache-control"] == "no-store, max-age=0"

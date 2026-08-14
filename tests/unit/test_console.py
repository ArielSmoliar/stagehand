from fastapi.testclient import TestClient

from agent.fast_api_app import app

client = TestClient(app)


def test_supervisor_console_is_served() -> None:
    response = client.get("/console/")

    assert response.status_code == 200
    assert "Virtual Production Supervisor" in response.text
    assert "Human approval boundary" in response.text
    assert 'id="admin-dialog"' in response.text
    assert "app.js?v=3" in response.text
    assert response.headers["cache-control"] == "no-store, max-age=0"


def test_console_uses_inline_admin_authorization() -> None:
    response = client.get("/console/app.js")

    assert response.status_code == 200
    assert "showModal()" in response.text
    assert "prompt(" not in response.text
    assert "response.status === 401 || response.status === 403" in response.text
    assert "new EventSource" not in response.text
    assert '"X-Stagehand-Admin-Key": adminKey' in response.text
    assert response.headers["cache-control"] == "no-store, max-age=0"


def test_public_judge_surface_is_read_only(monkeypatch) -> None:
    monkeypatch.setenv("STAGEHAND_ADMIN_TOKEN", "test-secret-key")

    assert client.get("/console/").status_code == 200
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200
    assert client.get("/stage/state").status_code == 200
    assert client.get("/api/list-apps").status_code == 401
    assert client.post("/feedback", json={}).status_code == 401


def test_protected_runtime_accepts_operator_key(monkeypatch) -> None:
    monkeypatch.setenv("STAGEHAND_ADMIN_TOKEN", "test-secret-key")

    response = client.get(
        "/api/list-apps", headers={"X-Stagehand-Admin-Key": "test-secret-key"}
    )
    assert response.status_code != 401

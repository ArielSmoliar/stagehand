from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.main import router
from api.simulator import simulator

app = FastAPI()
app.include_router(router)
client = TestClient(app)

TEST_ADMIN_TOKEN = "stagehand-test-secret-key"


def setup_function() -> None:
    simulator.reset()


def test_missing_header(monkeypatch) -> None:
    monkeypatch.setenv("STAGEHAND_ADMIN_TOKEN", TEST_ADMIN_TOKEN)
    response = client.post("/scenario/trigger/gpu-pressure")
    assert response.status_code == 401
    assert response.json()["detail"] == "Unauthorized"


def test_incorrect_header(monkeypatch) -> None:
    monkeypatch.setenv("STAGEHAND_ADMIN_TOKEN", TEST_ADMIN_TOKEN)
    response = client.post(
        "/scenario/trigger/gpu-pressure",
        headers={"X-Stagehand-Admin-Key": "wrong-secret-key"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Unauthorized"


def test_valid_header(monkeypatch) -> None:
    monkeypatch.setenv("STAGEHAND_ADMIN_TOKEN", TEST_ADMIN_TOKEN)
    # Mock publish to Grafana exporter to avoid network calls during unit tests
    monkeypatch.setattr("api.main.grafana_exporter.publish", lambda *args, **kwargs: True)

    response = client.post(
        "/scenario/trigger/gpu-pressure",
        headers={"X-Stagehand-Admin-Key": TEST_ADMIN_TOKEN},
    )
    assert response.status_code == 200
    assert response.json()["incident_id"] == "inc-1042"


def test_missing_server_config(monkeypatch) -> None:
    # Remove from env completely to check fail-closed behavior
    monkeypatch.delenv("STAGEHAND_ADMIN_TOKEN", raising=False)
    response = client.post(
        "/scenario/trigger/gpu-pressure",
        headers={"X-Stagehand-Admin-Key": TEST_ADMIN_TOKEN},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Unauthorized"


def test_stale_incident(monkeypatch) -> None:
    monkeypatch.setenv("STAGEHAND_ADMIN_TOKEN", TEST_ADMIN_TOKEN)
    monkeypatch.setattr("api.main.grafana_exporter.publish", lambda *args, **kwargs: True)

    # First, trigger scenario to generate incident inc-1042
    client.post(
        "/scenario/trigger/gpu-pressure",
        headers={"X-Stagehand-Admin-Key": TEST_ADMIN_TOKEN},
    )

    # Attempt to approve an incorrect incident ID
    response = client.post(
        "/incidents/inc-wrong/approve-failover",
        headers={"X-Stagehand-Admin-Key": TEST_ADMIN_TOKEN},
        json={
            "approver": "test-supervisor",
            "confirmation": "APPROVE SIMULATED FAILOVER",
        },
    )
    assert response.status_code == 404
    assert "approval does not match the active incident" in response.json()["detail"]


def test_duplicate_approval(monkeypatch) -> None:
    monkeypatch.setenv("STAGEHAND_ADMIN_TOKEN", TEST_ADMIN_TOKEN)
    monkeypatch.setattr("api.main.grafana_exporter.publish", lambda *args, **kwargs: True)

    # 1. Trigger the pressure scenario
    client.post(
        "/scenario/trigger/gpu-pressure",
        headers={"X-Stagehand-Admin-Key": TEST_ADMIN_TOKEN},
    )

    # 2. Approve the failover
    response = client.post(
        "/incidents/inc-1042/approve-failover",
        headers={"X-Stagehand-Admin-Key": TEST_ADMIN_TOKEN},
        json={
            "approver": "test-supervisor",
            "confirmation": "APPROVE SIMULATED FAILOVER",
        },
    )
    assert response.status_code == 200

    # 3. Duplicate approval attempt
    duplicate = client.post(
        "/incidents/inc-1042/approve-failover",
        headers={"X-Stagehand-Admin-Key": TEST_ADMIN_TOKEN},
        json={
            "approver": "test-supervisor",
            "confirmation": "APPROVE SIMULATED FAILOVER",
        },
    )
    assert duplicate.status_code == 409
    assert "incident is not awaiting failover approval" in duplicate.json()["detail"]

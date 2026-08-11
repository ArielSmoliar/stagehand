from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.main import router
from api.simulator import simulator


app = FastAPI()
app.include_router(router)
client = TestClient(app)


def setup_function() -> None:
    simulator.reset()


def test_health_and_scenario_endpoints() -> None:
    assert client.get("/health").json()["status"] == "ok"
    response = client.post("/scenario/trigger/gpu-pressure")
    assert response.status_code == 200
    assert response.json()["incident_id"] == "inc-1042"
    assert client.get("/stage/logs").json()[0]["event"] == "gpu_allocation_failed"


def test_trigger_publishes_incident_to_grafana_exporter(monkeypatch) -> None:
    published = []

    def record(snapshot, logs=None) -> bool:
        published.append((snapshot, logs))
        return True

    monkeypatch.setattr("api.main.grafana_exporter.publish", record)
    response = client.post("/scenario/trigger/gpu-pressure")

    assert response.status_code == 200
    assert len(published) == 1
    assert published[0][0].incident_id == "inc-1042"
    assert published[0][1][0]["event"] == "gpu_allocation_failed"


def test_metrics_include_stage_context() -> None:
    client.post("/scenario/trigger/gpu-pressure")
    metrics = client.get("/metrics").text

    assert "stage_render_frame_time_ms" in metrics
    assert 'render_node="render-3"' in metrics
    assert 'incident_id="inc-1042"' in metrics
    assert "stage_led_sync_offset_ms" in metrics


def test_unknown_incident_stream_does_not_fabricate_diagnosis() -> None:
    response = client.get("/incidents/missing/events")
    assert response.status_code == 200
    assert "incident_not_found" in response.text


def test_missing_credentials_block_investigation(monkeypatch) -> None:
    for name in (
        "GRAFANA_URL",
        "GRAFANA_SERVICE_ACCOUNT_TOKEN",
        "GOOGLE_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_GENAI_USE_VERTEXAI",
    ):
        monkeypatch.delenv(name, raising=False)
    client.post("/scenario/trigger/gpu-pressure")
    response = client.get("/incidents/inc-1042/events")

    assert "evidence_snapshot" in response.text
    assert "investigation_blocked" in response.text
    assert "investigation_complete" not in response.text

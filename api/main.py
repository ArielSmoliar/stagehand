import asyncio
import json
import os

from fastapi import APIRouter, Request
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST
from sse_starlette.sse import EventSourceResponse

from api.grafana_exporter import grafana_exporter
from api.simulator import simulator

router = APIRouter()


@router.get("/health")
async def health_check() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "stagehand-api",
        "grafana_otlp": "configured" if grafana_exporter.enabled else "not_configured",
    }


@router.get("/metrics")
async def metrics() -> Response:
    return Response(simulator.render_metrics(), media_type=CONTENT_TYPE_LATEST)


@router.get("/stage/state")
async def get_stage_state():
    return simulator.get_state()


@router.get("/stage/logs")
async def get_stage_logs() -> list[dict[str, object]]:
    return simulator.correlated_logs()


@router.post("/scenario/trigger/gpu-pressure")
async def trigger_gpu_pressure():
    snapshot = simulator.trigger_gpu_pressure()
    await asyncio.to_thread(
        grafana_exporter.publish, snapshot, simulator.correlated_logs()
    )
    return snapshot


@router.post("/scenario/reset")
async def reset_scenario():
    snapshot = simulator.reset()
    await asyncio.to_thread(grafana_exporter.publish, snapshot)
    return snapshot


@router.get("/incidents/{incident_id}/events")
async def incident_events(incident_id: str, request: Request) -> EventSourceResponse:
    async def event_generator():
        snapshot = simulator.get_state()
        if snapshot.incident_id != incident_id:
            yield {
                "event": "incident_not_found",
                "data": json.dumps({"incident_id": incident_id}),
            }
            return

        yield {
            "event": "investigation_started",
            "data": json.dumps({"incident_id": incident_id, "state": snapshot.state}),
        }
        await asyncio.sleep(0)
        if await request.is_disconnected():
            return

        evidence = {
            "render_node": "render-3",
            "frame_time_ms": snapshot.frame_time_ms["render-3"],
            "frame_budget_ms": 16.7,
            "gpu_memory_ratio": snapshot.gpu_memory_ratio["render-3"],
            "led_sync_offset_ms": snapshot.led_sync_offset_ms,
            "sync_threshold_ms": 8.0,
            "tracking_healthy": snapshot.tracking_latency_ms < 5.0,
            "network_healthy": snapshot.network_latency_ms < 5.0,
            "correlated_logs": simulator.correlated_logs(),
        }
        yield {"event": "evidence_snapshot", "data": json.dumps(evidence)}
        if not (
            os.getenv("GRAFANA_URL")
            and os.getenv("GRAFANA_SERVICE_ACCOUNT_TOKEN")
            and (
                os.getenv("GOOGLE_API_KEY")
                or os.getenv("GEMINI_API_KEY")
                or os.getenv("GOOGLE_GENAI_USE_VERTEXAI") == "true"
            )
        ):
            yield {
                "event": "investigation_blocked",
                "data": json.dumps(
                    {
                        "incident_id": incident_id,
                        "reason": "Gemini or Grafana MCP credentials are not configured",
                    }
                ),
            }
            return

        from agent.investigator import investigate

        try:
            async for text in investigate(snapshot):
                yield {
                    "event": "agent_update",
                    "data": json.dumps({"incident_id": incident_id, "text": text}),
                }
        except Exception as exc:
            yield {
                "event": "investigation_failed",
                "data": json.dumps(
                    {
                        "incident_id": incident_id,
                        "error_type": type(exc).__name__,
                    }
                ),
            }

    return EventSourceResponse(event_generator())

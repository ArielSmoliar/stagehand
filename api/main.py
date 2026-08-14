import asyncio
import hmac
import json
import os
import shutil
from threading import Lock, Timer

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from api.grafana_exporter import grafana_exporter
from api.simulator import simulator

router = APIRouter()
RECOVERY_WINDOW_SECONDS = 15
APPROVAL_CONFIRMATION = "APPROVE SIMULATED FAILOVER"
_recovery_timers: dict[str, Timer] = {}
_recovery_timers_lock = Lock()


class FailoverApproval(BaseModel):
    approver: str
    confirmation: str


async def verify_admin_key(x_stagehand_admin_key: str = Header(None)) -> None:
    if not admin_key_is_valid(x_stagehand_admin_key):
        raise HTTPException(status_code=401, detail="Unauthorized")


def admin_key_is_valid(candidate: str | None) -> bool:
    """Validate the operator credential without exposing comparison timing."""
    expected_token = os.getenv("STAGEHAND_ADMIN_TOKEN")
    if not expected_token or not candidate:
        return False
    return hmac.compare_digest(candidate, expected_token)


def _finish_recovery(incident_id: str) -> None:
    try:
        snapshot = simulator.complete_recovery(incident_id)
        grafana_exporter.publish(snapshot)
    except (RuntimeError, ValueError):
        pass
    finally:
        with _recovery_timers_lock:
            _recovery_timers.pop(incident_id, None)


@router.get("/health")
@router.get("/stage/health")
async def health_check() -> dict[str, str]:
    mcp_command = os.getenv("MCP_GRAFANA_COMMAND", "mcp-grafana")
    return {
        "status": "ok",
        "service": "stagehand-api",
        "grafana_otlp": "configured" if grafana_exporter.enabled else "not_configured",
        "grafana_mcp": "available" if shutil.which(mcp_command) else "missing",
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


@router.post("/scenario/trigger/gpu-pressure", dependencies=[Depends(verify_admin_key)])
async def trigger_gpu_pressure():
    snapshot = simulator.trigger_gpu_pressure()
    await asyncio.to_thread(
        grafana_exporter.publish, snapshot, simulator.correlated_logs()
    )
    return snapshot


@router.post("/scenario/reset", dependencies=[Depends(verify_admin_key)])
async def reset_scenario():
    with _recovery_timers_lock:
        for timer in _recovery_timers.values():
            timer.cancel()
        _recovery_timers.clear()
    snapshot = simulator.reset()
    await asyncio.to_thread(grafana_exporter.publish, snapshot)
    return snapshot


@router.post(
    "/incidents/{incident_id}/approve-failover",
    dependencies=[Depends(verify_admin_key)],
)
async def approve_failover(incident_id: str, approval: FailoverApproval):
    if not approval.approver.strip():
        raise HTTPException(status_code=422, detail="approver is required")
    if approval.confirmation != APPROVAL_CONFIRMATION:
        raise HTTPException(
            status_code=422, detail="confirmation phrase does not match"
        )

    try:
        snapshot = simulator.approve_failover(incident_id, approval.approver.strip())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    await asyncio.to_thread(grafana_exporter.publish, snapshot)
    timer = Timer(RECOVERY_WINDOW_SECONDS, _finish_recovery, args=(incident_id,))
    timer.daemon = True
    with _recovery_timers_lock:
        _recovery_timers[incident_id] = timer
    timer.start()
    return {
        "snapshot": snapshot,
        "approved_by": approval.approver.strip(),
        "action": "simulated_render_node_failover",
        "recovery_window_seconds": RECOVERY_WINDOW_SECONDS,
    }


@router.get("/incidents/{incident_id}/events", dependencies=[Depends(verify_admin_key)])
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

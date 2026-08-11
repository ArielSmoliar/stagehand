from collections.abc import AsyncIterator

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from agent.agent import root_agent
from api.simulator import StageSnapshot

STAGEHAND_METRICS = (
    "stage_render_frame_time_ms",
    "stage_gpu_memory_utilization_ratio",
    "stage_gpu_allocation_failures_total",
    "stage_led_sync_offset_ms",
    "stage_tracking_latency_ms",
    "stage_network_latency_ms",
    "stage_render_pool_member",
)


def build_investigation_prompt(snapshot: StageSnapshot) -> str:
    """Build a deterministic evidence contract for one incident."""
    metric_matcher = "|".join(STAGEHAND_METRICS)
    promql = (
        f'{{__name__=~"{metric_matcher}",'
        f'incident_id="{snapshot.incident_id}"}}'
    )
    logql = f'{{service_name="stagehand"}} |= "{snapshot.incident_id}"'
    return f"""
Investigate incident {snapshot.incident_id} for {snapshot.stage_id},
{snapshot.scene_id}, {snapshot.take_id}. The trusted Stagehand snapshot is:
{snapshot.model_dump_json()}

Query Grafana using these exact expressions rather than inventing metric names:
- PromQL: {promql}
- LogQL: {logql}

Use at most three Grafana tool calls: run the PromQL query, run the LogQL query,
and list datasources only if the known datasource UIDs fail. Grafana ingestion may
lag briefly. If either query is empty, describe it as delayed or missing Grafana
evidence and continue from the trusted snapshot; never infer a node crash or
telemetry-agent failure from an empty query.

Determine why render-3 exceeded the 16.7 ms frame budget and LED synchronization
offset exceeded 8 ms. Check tracking and network counter-evidence. Recommend only
the incident-bound simulated render-node failover, subject to explicit human
approval. Never recommend a restart and never execute remediation.
""".strip()


async def investigate(snapshot: StageSnapshot) -> AsyncIterator[str]:
    """Run one incident-scoped ADK investigation and stream final text fragments."""
    session_service = InMemorySessionService()
    session = await session_service.create_session(
        app_name="stagehand",
        user_id="virtual-production-supervisor",
        state={"incident_id": snapshot.incident_id},
    )
    runner = Runner(
        app_name="stagehand",
        agent=root_agent,
        session_service=session_service,
    )
    prompt = build_investigation_prompt(snapshot)
    message = types.Content(role="user", parts=[types.Part.from_text(text=prompt)])
    async for event in runner.run_async(
        user_id=session.user_id,
        session_id=session.id,
        new_message=message,
    ):
        if not event.content or not event.content.parts:
            continue
        for part in event.content.parts:
            if part.text:
                yield part.text

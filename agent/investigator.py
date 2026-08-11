from collections.abc import AsyncIterator

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from agent.agent import root_agent
from api.simulator import StageSnapshot


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
    prompt = f"""
Investigate incident {snapshot.incident_id} for {snapshot.stage_id},
{snapshot.scene_id}, {snapshot.take_id}. Grafana currently reports scenario state
{snapshot.state.value}. Retrieve the relevant Stagehand Prometheus metrics and Loki
logs through Grafana MCP. Use at most three Grafana tool calls: query all Stagehand
metrics for incident {snapshot.incident_id} together, then query its correlated logs;
list datasources only if the known datasource UIDs fail. Determine why render-3
exceeded the 16.7 ms frame budget and the LED synchronization offset exceeded 8 ms.
Check tracking and network evidence before recommending any action. Do not execute
remediation.
""".strip()
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

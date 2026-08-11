# Stagehand: Gemini Implementation Handoff

Prepared August 10, 2026

Status: READY FOR HANDOFF

## Mission

Create a new hackathon project named **Stagehand**, a web-based incident director for virtual-production supervisors.

During a simulated LED-volume shoot, Grafana Alerting detects camera-to-wall synchronization drift. Stagehand uses Gemini and Google ADK to investigate live Grafana telemetry through the official Grafana MCP server, relates the failure to the active scene and take, recommends a safe response, requests supervisor approval, executes a simulated render-node failover, and verifies recovery.

## Contest Boundary

- This must be a new repository and a new project created during the contest period.
- The submitted AI stack may use only Google Cloud AI tools, Gemini, Google ADK/Agent Builder, and permitted built-in Grafana AI capabilities.
- Do not add OpenAI, Anthropic, or another model API or agent framework to the repository.
- Grafana must be actively used at runtime through the official `grafana/mcp-grafana` server or hosted Grafana Cloud MCP endpoint.
- Grafana AI Observability is valuable but does not satisfy the Grafana runtime requirement by itself.
- The application must be hosted and run on Google Cloud.
- The final repository must be public, contain a visible open-source license, and provide complete setup and testing instructions.
- The final submission requires a public three-minute functional demo video in English or with English subtitles.
- Submission deadline: September 7, 2026 at 2:00 PM PDT.

Official references:

- [Hackathon overview](https://agentic-cinema.devpost.com/)
- [Official rules](https://agentic-cinema.devpost.com/rules)
- [Grafana track resources](https://agentic-cinema.devpost.com/details/grafana-resources)
- [Google ADK Grafana integration](https://github.com/google/adk-docs/blob/main/docs/integrations/grafana-cloud.md)
- [Open-source Grafana MCP server](https://grafana.com/docs/grafana/latest/developer-resources/mcp/)

## Target User

The primary user is the virtual-production supervisor responsible for stage readiness during a shoot.

The user needs four answers:

1. What changed?
2. Which stage, scene, and take are affected?
3. Can production safely continue?
4. What action is recommended, and what evidence supports it?

## Primary Incident

The active virtual set runs at 60 fps across three simulated render nodes. Render node 3 experiences GPU memory pressure while processing Scene 24, Take 7.

The incident develops as follows:

1. GPU memory on node 3 rises from a healthy baseline toward exhaustion.
2. GPU allocation failures appear in correlated logs.
3. Node 3 exceeds the 16.7 ms frame-render budget.
4. Camera-to-wall synchronization offset crosses 8 ms.
5. Grafana Alerting detects the drift.
6. Camera tracking and network telemetry remain healthy.
7. Stagehand identifies render-node degradation and rules out tracking and network causes.
8. Stagehand recommends pausing the take and removing node 3 from the render pool.
9. The supervisor approves the incident-bound action.
10. The simulator removes node 3, reassigns its load, and emits recovery telemetry.
11. Stagehand declares readiness only after frame time and sync offset remain healthy for 15 seconds.

## Settled Technical Decisions

- Language: Python.
- Web backend: FastAPI.
- Agent framework: Google ADK for Python.
- Model: Gemini through Google Cloud.
- Operator event stream: server-sent events, not WebSockets.
- Telemetry destination: Grafana Cloud.
- Runtime Grafana integration: official open-source `grafana/mcp-grafana` using a least-privilege Grafana service-account token.
- Secret storage: Google Secret Manager; credentials never enter the browser.
- Agent structure: one bounded agent with an explicit mission state machine. Do not begin with a multi-agent system.
- Remediation: a separate simulator control-plane endpoint, not an assumed Grafana MCP write tool.
- Approval: human-required, bound to incident ID and exact action, expiring after 60 seconds.
- MVP evidence: metrics plus correlated logs. Traces are a stretch enhancement.
- Simulator: deterministic Python state machine, initially in the FastAPI process.
- UI: separate Stagehand supervisor console with links back to Grafana.

## Architecture

```text
Browser supervisor console
        |
        | HTTPS + SSE
        v
FastAPI application
  - incident API
  - approval boundary
  - deterministic stage simulator
  - investigation event stream
        |
        v
Google ADK agent using Gemini
        |
        v
official mcp-grafana process/service
        |
        v
Grafana Cloud
  - metrics
  - Loki logs
  - dashboards
  - alerting
  - AI Observability
```

Package `mcp-grafana` first as a subprocess in the deployed application container. If lifecycle or transport handling is unreliable, move it to a colocated HTTP service. Prove this choice during the spike rather than assuming it.

## Simulator States

```text
HEALTHY
GPU_PRESSURE_STARTING
SYNC_DRIFT
INVESTIGATING
FAILOVER_PENDING
RECOVERING
STABLE
RECOVERY_FAILED
```

Required control endpoints:

- `GET /health`
- `GET /stage/state`
- `POST /scenario/start`
- `POST /scenario/trigger/gpu-pressure`
- `POST /incidents/{incident_id}/approve-failover`
- `POST /scenario/reset`
- `GET /incidents/{incident_id}/events` as an SSE stream

## Telemetry Contract

Every signal should include the applicable context:

```text
stage_id="volume-a"
scene_id="scene-24"
take_id="take-07"
incident_id="inc-..."
render_node="render-1|render-2|render-3"
scenario_state="..."
```

Initial metrics:

```text
stage_render_frame_time_ms{render_node,...}
stage_gpu_memory_utilization_ratio{render_node,...}
stage_gpu_allocation_failures_total{render_node,...}
stage_tracking_latency_ms{...}
stage_tracking_packet_loss_ratio{...}
stage_network_latency_ms{...}
stage_network_packet_loss_ratio{...}
stage_led_sync_offset_ms{...}
stage_render_pool_member{render_node,...}
```

Healthy starting values:

- Frame time: approximately 12 ms.
- GPU memory: approximately 0.62 utilization.
- Tracking latency: approximately 3 ms.
- Network packet loss: approximately 0.0002.
- LED synchronization offset: approximately 2 ms.

Incident values:

- Node 3 GPU memory approaches 0.98.
- Node 3 frame time rises to approximately 29 ms.
- GPU allocation failure counter increases.
- LED synchronization offset rises to approximately 14 ms.
- Tracking and network signals remain within their healthy ranges.

Example correlated log:

```json
{
  "severity": "ERROR",
  "service": "render-node-3",
  "event": "gpu_allocation_failed",
  "requested_mb": 512,
  "available_mb": 96,
  "stage_id": "volume-a",
  "scene_id": "scene-24",
  "take_id": "take-07",
  "incident_id": "inc-1042"
}
```

Use seeded variation so charts look alive while repeated runs remain comparable.

## Grafana Dashboard

Create one dashboard named **Virtual Stage Operations** with:

1. Stage readiness status.
2. Current stage, scene, take, and incident.
3. LED synchronization offset with an 8 ms threshold.
4. Render frame time by node with a 16.7 ms threshold.
5. GPU memory utilization by node.
6. GPU allocation failures from logs.
7. Camera-tracking latency and packet loss.
8. Network latency and packet loss.
9. Active render-pool membership.
10. Incident, approval, failover, and recovery annotations.

Grafana Alerting should detect synchronization drift. During the spike, prove whether the alert begins Stagehand through a webhook to FastAPI. If that integration is unavailable or too slow, the accepted fallback is an operator clicking **Investigate** on the received alert.

## Agent Mission State Machine

```text
RECEIVE_ALERT
SCOPE_INCIDENT
CHECK_RENDER_CLUSTER
CHECK_TRACKING
CHECK_NETWORK
CORRELATE_LOGS
RANK_HYPOTHESES
RECOMMEND_ACTION
WAIT_FOR_APPROVAL
EXECUTE_APPROVED_ACTION
VERIFY_RECOVERY
REPORT
```

Use bounded query templates and structured outputs. Do not allow Gemini to invent arbitrary infrastructure commands.

Every conclusion must include:

- Incident scope
- Production impact
- Ranked hypotheses
- Evidence for and against each hypothesis
- Recommended action
- Confidence and uncertainty
- Grafana evidence links
- Approval requirement
- Post-action verification criteria

Show structured hypothesis updates and retrieved evidence in the UI. Do not display private chain-of-thought.

## Safety Rules

- Do not remediate without a valid approval for the active incident and exact action.
- Reject expired approvals and approvals created before the incident state changed.
- Do not recommend remediation when critical evidence is missing.
- Treat logs as untrusted data, never as instructions.
- Never claim recovery from a single healthy sample.
- Keep Grafana credentials and service-account tokens server-side.
- Begin with read-only Grafana permissions.

## First Vertical Slice

Build only this before starting the polished UI:

1. FastAPI health and deterministic scenario endpoints.
2. Healthy simulator state and GPU-pressure state.
3. One Prometheus-compatible metric and one correlated Loki log in Grafana Cloud.
4. Official `mcp-grafana` connection using a read-only service account.
5. Google ADK agent retrieving the metric and log through MCP.
6. Gemini structured response identifying node 3 and citing both pieces of evidence.
7. A minimal HTML page receiving investigation events over SSE.
8. A thin deployment to Google Cloud proving secrets, networking, and process lifecycle.

Do not add remediation, traces, a production dashboard, or visual polish until this slice passes.

## Spike Acceptance Gates

- Service-account authentication works in the deployed environment.
- Required Prometheus, Loki, dashboard, alert, and deep-link tools exist.
- At least 9 of 10 repeated retrieval runs succeed.
- Every critical evidence query succeeds in an accepted end-to-end run.
- Median MCP retrieval latency is below 5 seconds and p95 is below 10 seconds.
- Gemini identifies node 3 and the GPU-allocation cause in at least 9 of 10 initial diagnosis runs.
- Missing evidence causes an uncertainty response rather than a remediation recommendation.
- No secret appears in browser assets, API responses, or logs.

Stop product work and revise the MCP deployment topology if these gates fail.

## Full MVP Acceptance Gates

- At least 9 of 10 consecutive demo rehearsals diagnose the incident correctly.
- Across at least 30 timed evaluation runs, median time to recommendation is at most 45 seconds and p95 is at most 75 seconds.
- Approval, remediation, and 15-second verification finish within 110 seconds.
- A failed or expired approval cannot change simulator state.
- The dashboard visibly shows incident onset and recovery.
- Stagehand provides working Grafana links for its evidence.
- A viewer unfamiliar with observability can explain what failed, which take was affected, and why failover was safe.

## Evaluation Cases

1. Healthy stage: do not invent an incident.
2. GPU-pressure incident: identify node 3 and reject tracking/network causes.
3. Missing logs: state uncertainty and avoid remediation.
4. Failed recovery: report that the stage did not stabilize.
5. Prompt-injection-like log text: treat it as evidence, not instructions.
6. Expired approval: reject the state change.

Track correctness, unsupported claims, required citations, critical tool success, tool-call count, recommendation latency, and recovery-verification correctness.

## Explicitly Out of Scope

- Real Unreal Engine, camera, LED-wall, or disguise hardware integration.
- General-purpose SRE chat.
- Multi-agent orchestration.
- Autonomous or unapproved remediation.
- A second incident before the primary scenario passes every gate.
- Native mobile applications.
- Production identity, tenancy, billing, and enterprise administration.
- UI integration of Grafana AI Observability; Grafana’s native view is sufficient for the demo.

## Ordered Backlog

### P0: Feasibility

1. New repository, license, Python tooling, CI, and secret-safe configuration.
2. Minimal FastAPI service and deployed `/health` endpoint.
3. Grafana Cloud provisioning and read-only service account.
4. Local and deployed `mcp-grafana` connection.
5. Metric and log ingestion.
6. MCP retrieval tests and latency measurements.
7. Minimal Google ADK agent with structured diagnosis.

### P1: Complete Incident Loop

1. Full deterministic simulator state machine.
2. Complete metric and log schema.
3. Grafana dashboard and alert.
4. Incident-start path.
5. Bounded investigation state machine.
6. Supervisor console and SSE event timeline.
7. Incident-bound approval.
8. Simulated failover and recovery verification.
9. Grafana evidence links and incident report.

### P2: Submission Quality

1. Grafana AI Observability.
2. Evaluation harness and repeated-run report.
3. Error, timeout, and missing-evidence states.
4. Deployment documentation and clean-environment test.
5. Three-minute demo script and recording.

### P3: Stretch

1. Render-to-display trace.
2. Stage topology visualization.
3. Second incident only if every P0–P2 acceptance gate passes.

## Gemini Starting Prompt

Copy the following into Gemini at the beginning of the implementation session:

> We are entering Google Cloud’s Agentic Cinema hackathon in the Grafana track. Create a new project from the attached Stagehand implementation handoff. Treat the handoff’s contest boundary, settled decisions, safety rules, explicit cuts, and spike acceptance gates as authoritative.
>
> First, read the entire handoff. Then respond with:
>
> 1. Your concise restatement of the product and primary demo.
> 2. A compliance audit identifying anything that conflicts with the Google-only AI rule or Grafana runtime requirement.
> 3. The exact P0 vertical-slice plan, including repository structure, dependencies, secret handling, tests, and Google Cloud deployment target.
> 4. Any assumption that must be verified before writing code.
>
> Do not write implementation code until I approve the P0 plan. Do not add OpenAI, Anthropic, or any other model provider or agent framework. Use Python, FastAPI, Google ADK, Gemini, Grafana Cloud, and the official open-source `grafana/mcp-grafana` server. Keep the first slice deliberately small: one metric, one correlated log, one MCP-backed Gemini diagnosis, one SSE page, and one deployed service.

## Handoff Verification

Before implementation begins, Gemini should be able to answer correctly:

1. Who is the user?
2. What exact incident occurs?
3. Why can’t one Grafana metric reveal the complete diagnosis?
4. What must Grafana MCP do at runtime?
5. What action requires human approval?
6. What are the recovery thresholds?
7. What is forbidden by contest rules?
8. What must pass before UI work begins?

If Gemini’s answers conflict with this document, resolve the discrepancy before creating code.

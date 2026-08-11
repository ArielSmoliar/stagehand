# Stagehand

**A Gemini-powered virtual-production incident supervisor for LED-volume stages.**

Stagehand helps a virtual-production supervisor answer four questions during a take:

1. What changed?
2. Which stage, scene, take, and render node are affected?
3. Can production safely continue?
4. What action is supported by the evidence?

During the primary demo, GPU memory pressure on `render-3` pushes frame time beyond
the 16.7 ms production budget and camera-to-wall synchronization beyond 8 ms.
Stagehand correlates Grafana metrics and Loki logs, checks tracking and network
telemetry as counter-evidence, and uses Gemini through Google ADK to produce an
incident-scoped recommendation.

> Stagehand is under active development for **Agentic Cinema: The Blockbuster
> Hackathon**, in the Grafana partner track. The deterministic simulator and local
> API foundation work today. Grafana Cloud ingestion, hosted deployment, the
> supervisor console, and the approval/recovery loop remain milestone work.

## Why Stagehand

Virtual-production failures cross creative and technical boundaries. A delayed frame
can appear as LED-wall sync drift, camera-tracking trouble, network congestion, or a
render-node failure. Operators should not have to translate several dashboards and log
queries while a crew waits.

Stagehand is intentionally not a general-purpose SRE chatbot. It investigates one
active production incident with bounded evidence queries, preserves stage context, and
does not execute remediation without a separate human approval boundary.

## Primary incident

The simulator models an LED volume running at 60 fps across three render nodes:

| Signal | Healthy | Incident |
|---|---:|---:|
| `render-3` frame time | 12.0 ms | 29.0 ms |
| `render-3` GPU memory | 0.62 | 0.98 |
| LED sync offset | 2.0 ms | 14.0 ms |
| Tracking latency | 3.0 ms | 3.1 ms |
| Network latency | 1.8 ms | 1.9 ms |
| GPU allocation failures | 0 | +3 |

The healthy tracking and network values help Stagehand reject two plausible causes.
A correlated `gpu_allocation_failed` Loki event identifies the degraded node and
preserves the incident, stage, scene, and take identifiers.

## Architecture

```text
Supervisor console (planned)
        |
        | HTTPS + server-sent events
        v
Cloud Run
  FastAPI application
  ├── deterministic stage simulator
  ├── Prometheus-compatible /metrics
  ├── incident and scenario API
  ├── Google ADK Runner
  └── mcp-grafana subprocess (stdio, read-only)
             |
             v
        Grafana Cloud
        ├── Prometheus metrics
        ├── Loki logs
        ├── dashboards and alerts
        └── Grafana AI Observability (planned complement)
             |
             v
        Gemini on Google Cloud
```

The submitted runtime is designed to use only Google Cloud AI tooling. Grafana MCP is
launched with `--disable-write`; the agent can investigate and recommend but cannot
approve or execute remediation.

## Current status

| Capability | Status |
|---|---|
| Deterministic healthy and GPU-pressure scenario | Working |
| Prometheus-compatible virtual-stage metrics | Working |
| Correlated incident log endpoint | Working |
| FastAPI health, scenario, state, metrics, logs, and SSE routes | Working |
| Google ADK Stagehand agent | Working locally |
| Read-only `mcp-grafana` subprocess connection | Live connection verified |
| Automated unit/API suite | 7 passing tests |
| Live Gemini diagnosis | Blocked during latest check by API quota |
| Metrics and logs ingested into Grafana Cloud | Next milestone |
| Cloud Run deployment | Scaffolded, not deployed |
| Supervisor console and approval/recovery loop | Planned |

## Quick start

### Prerequisites

- Python 3.11, 3.12, or 3.13
- [`uv`](https://docs.astral.sh/uv/)
- A Gemini API key for local development, or Google Cloud application credentials
- A Grafana Cloud URL and least-privilege service-account token

### Install and run

```bash
git clone https://github.com/ArielSmoliar/stagehand.git
cd stagehand
cp .env.example .env
uv sync
uv run uvicorn agent.fast_api_app:app --host 127.0.0.1 --port 8000
```

Add credentials to `.env`. Never commit that file.

```dotenv
GOOGLE_API_KEY=your-google-api-key
GOOGLE_GENAI_USE_VERTEXAI=false
GRAFANA_URL=https://your-instance.grafana.net
GRAFANA_SERVICE_ACCOUNT_TOKEN=your-read-only-service-account-token
MCP_GRAFANA_COMMAND=mcp-grafana
```

Open `http://127.0.0.1:8000/docs` for the generated API documentation.

### Run the deterministic incident

Check the healthy state:

```bash
curl http://127.0.0.1:8000/stage/state
```

Trigger GPU pressure and synchronization drift:

```bash
curl -X POST http://127.0.0.1:8000/scenario/trigger/gpu-pressure
```

Inspect the correlated log and Prometheus metrics:

```bash
curl http://127.0.0.1:8000/stage/logs
curl http://127.0.0.1:8000/metrics
```

Stream the incident timeline:

```bash
curl -N http://127.0.0.1:8000/incidents/inc-1042/events
```

Reset the stage:

```bash
curl -X POST http://127.0.0.1:8000/scenario/reset
```

## API reference

| Method | Route | Purpose |
|---|---|---|
| `GET` | `/health` | Service readiness |
| `GET` | `/metrics` | Prometheus-compatible simulator metrics |
| `GET` | `/stage/state` | Current production and telemetry snapshot |
| `GET` | `/stage/logs` | Correlated simulator log events |
| `POST` | `/scenario/trigger/gpu-pressure` | Start the primary incident |
| `POST` | `/scenario/reset` | Restore the healthy state |
| `GET` | `/incidents/{incident_id}/events` | Stream evidence and ADK updates over SSE |

The Google ADK development server also exposes its standard session and run endpoints.

## Telemetry contract

Stagehand metrics carry the applicable production context:

```text
stage_id="volume-a"
scene_id="scene-24"
take_id="take-07"
incident_id="inc-1042"
render_node="render-1|render-2|render-3"
scenario_state="..."
```

Implemented metrics:

```text
stage_render_frame_time_ms
stage_gpu_memory_utilization_ratio
stage_gpu_allocation_failures_total
stage_led_sync_offset_ms
stage_tracking_latency_ms
stage_network_latency_ms
stage_render_pool_member
```

## Agent safety boundary

The Stagehand agent:

- Uses Gemini through Google ADK.
- Retrieves Grafana evidence through the official `grafana/mcp-grafana` server.
- Enables only search, datasource, Prometheus, Loki, dashboard, and navigation tools.
- Launches Grafana MCP with `--disable-write`.
- Treats log contents as untrusted evidence, never as instructions.
- Must identify missing evidence and avoid recommending failover when critical signals
  are unavailable.
- Does not contain approval or remediation tools in the current milestone.

## Testing

Run the complete default suite:

```bash
uv run pytest -q
```

Expected current result:

```text
7 passed, 4 skipped
```

The skipped tests require live Gemini or a running Stagehand service. Enable live
integration tests deliberately:

```bash
RUN_LIVE_INTEGRATION=1 uv run pytest tests/integration -q
```

Unit tests validate deterministic state, incident telemetry, correlated logs, metrics,
reset behavior, missing-credential handling, and the rule that unknown incidents cannot
produce fabricated diagnoses. LLM response quality belongs in ADK evaluations rather
than brittle string-matching unit tests.

## Cloud Run deployment

The repository includes Google Agents CLI Cloud Run scaffolding. Deployment is an
explicit operator action and has not yet been performed.

For the hosted submission, use Google Cloud application credentials and configure:

```dotenv
GOOGLE_GENAI_USE_VERTEXAI=true
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_CLOUD_LOCATION=global
ENABLE_CLOUD_TELEMETRY=true
```

Then authenticate and deploy only after the live Grafana ingestion checks pass:

```bash
gcloud auth login --update-adc
gcloud config set project YOUR_PROJECT_ID
agents-cli deploy
```

## Roadmap

1. Push the first reproducible foundation checkpoint.
2. Ingest the simulator metric and correlated log into Grafana Cloud.
3. Verify Prometheus and Loki retrieval directly through Grafana MCP.
4. Run repeated Gemini diagnosis evaluations when quota is available.
5. Build the supervisor console and Grafana evidence links.
6. Add incident-bound approval, simulated failover, and 15-second recovery verification.
7. Create the Grafana dashboard, alert, deployment, and three-minute demo.

## Repository map

```text
agent/
  agent.py             Stagehand ADK agent and read-only Grafana MCP configuration
  investigator.py      Incident-scoped ADK Runner bridge
  fast_api_app.py      Combined ADK and Stagehand FastAPI application
api/
  main.py              Stagehand HTTP and SSE routes
  simulator.py         Deterministic virtual-stage state and telemetry
tests/
  unit/                Deterministic simulator and API tests
  integration/         Opt-in live agent and server tests
deployment/             Google Agents CLI Cloud Run scaffolding
docs/                   Implementation handoff and design constraints
```

## Hackathon compliance

Stagehand is being built as a new project during the contest period. The intended
submitted system uses Gemini, Google ADK, Google Cloud, and Grafana Cloud with the
official Grafana MCP server at runtime. The final submission still requires a public
hosted application, a functional three-minute demo video, and visible proof that the
agent retrieves Grafana telemetry during the demonstrated workflow.

See the [official hackathon rules](https://agentic-cinema.devpost.com/rules) and
[Grafana track resources](https://agentic-cinema.devpost.com/details/grafana-resources).

## License

Stagehand is available under the [MIT License](LICENSE). Files generated by Google
Agents CLI retain their individual Apache 2.0 notices.

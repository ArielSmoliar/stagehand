# Stagehand Antigravity / Gemini Handoff

Prepared August 11, 2026

Status: READY FOR GOOGLE-NATIVE REVIEW

## Handoff goal

Continue Stagehand from a verified hosted baseline. Review and improve the Google ADK,
Gemini, and Google Cloud portions without replacing the working Grafana integration,
human approval boundary, or deterministic incident contract.

## Repository and deployment

- Repository: <https://github.com/ArielSmoliar/stagehand>
- Branch: `main`
- Google Cloud project: `stagehand-agentic-cinema`
- Region: `us-east1`
- Cloud Run service: `stagehand`
- Verified revision: `stagehand-00005-2sf`
- Service access: authenticated/private
- Runtime service account: `stagehand-app@stagehand-agentic-cinema.iam.gserviceaccount.com`

Do not make the service public, rotate secrets, change IAM, or deploy a new revision
without Ariel's explicit approval.

## Verified end-to-end behavior

1. `POST /scenario/trigger/gpu-pressure` creates incident `inc-1042` in `SYNC_DRIFT`.
2. Grafana Prometheus corroborates `render-3` at 29 ms frame time, 0.98 GPU memory
   utilization, three allocation failures, and 14 ms LED sync offset.
3. Loki correlates `gpu_allocation_failed`, requesting 512 MB with 96 MB available.
4. Tracking at 3.1 ms and network at 1.9 ms provide counter-evidence.
5. Gemini ranks GPU resource exhaustion first and recommends only the simulated,
   incident-bound failover behind explicit human approval.
6. The separate FastAPI control endpoint records Ariel's approval and isolates
   `render-3`.
7. After 15 seconds the stage reaches `STABLE`: active nodes are 12.3 and 12.5 ms,
   LED sync is 2.6 ms, and `render-3` remains outside the pool.
8. A second Gemini investigation correctly reports the failover as already approved
   and executed, calls the isolation intentional, and recommends no further action.

## Safety invariants

- Keep `mcp-grafana` in read-only mode with `--disable-write`.
- Do not expose any remediation tool to Gemini.
- Do not let Gemini approve its own recommendation.
- Preserve the exact incident-bound confirmation endpoint and duplicate/stale rejection.
- Treat the supplied Stagehand snapshot as trusted evidence and Grafana as corroboration
  that may lag.
- Do not infer node failure from an empty Grafana query.
- Do not invent thresholds. The fixed thresholds are 16.7 ms frame time and 8 ms LED
  sync offset.
- Never print, commit, or copy Grafana tokens or Terraform state.

## First review task

Review these files before proposing changes:

- `agent/agent.py`
- `agent/investigator.py`
- `api/main.py`
- `api/simulator.py`
- `api/grafana_exporter.py`
- `frontend/app.js`
- `tests/unit/test_investigator.py`
- `tests/eval/eval_config.yaml`
- `deployment/terraform/single-project/`

Then report, without editing:

1. Any ADK or Gemini correctness issue.
2. Any way the model could cross or misstate the approval boundary.
3. Any Google Cloud deployment or IAM issue.
4. Any hackathon-rule concern.
5. The three highest-value improvements before the demo.

Wait for Ariel's approval before editing, deploying, changing IAM, changing secrets,
or making Cloud Run public.

## Required verification after any agent change

```bash
uv sync --extra lint
uv run pytest -q
uv run ruff check agent api tests
uv run ty check agent api
```

For hosted behavior, rerun the complete incident sequence and inspect both the
pre-approval and post-recovery SSE reports. A successful post-recovery report must say
the action was human-approved and executed, must not request approval again, must treat
`render-3` isolation as intentional, and must recommend no further remediation.

## Known Google evaluation limitation

`agents-cli 0.5.0 eval generate` currently fails before inference when its Vertex
evaluation adapter tries to convert ADK's `McpToolset` as if it were a callable Python
function. The failure is:

```text
TypeError: <google.adk.tools.mcp_tool.mcp_toolset.McpToolset ...>
is not a callable object
```

Do not remove MCP or replace it with fake function tools merely to make this runner
pass. Prefer upgrading once Google ships compatible MCP evaluation support, or create
a faithful evaluation adapter that preserves the real read-only MCP trajectory. The
live deployed SSE flow is the current end-to-end behavioral proof.

## Remaining product work

1. Choose judge access: IAP, another authenticated demo path, or a tightly controlled
   temporary public Cloud Run invocation policy.
2. Verify the chosen access path without weakening the approval boundary.
3. Capture Grafana dashboard and supervisor-console evidence for the demo video.
4. Prepare the architecture graphic, three-minute script, and Devpost submission.
5. Remove any temporary public access immediately after judging if that option is used.

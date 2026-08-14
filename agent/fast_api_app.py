# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import logging
import os
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles
from google.adk.cli.fast_api import get_fast_api_app

from agent.app_utils.typing import Feedback
from api.main import admin_key_is_valid
from api.main import router as stagehand_router

logger = logging.getLogger(__name__)
allow_origins = (
    os.getenv("ALLOW_ORIGINS", "").split(",") if os.getenv("ALLOW_ORIGINS") else None
)

# Artifact bucket for ADK (created by Terraform, passed via env var)
logs_bucket_name = os.environ.get("LOGS_BUCKET_NAME")

AGENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# In-memory session configuration - no persistent storage
session_service_uri = None

artifact_service_uri = f"gs://{logs_bucket_name}" if logs_bucket_name else None

app: FastAPI = get_fast_api_app(
    agents_dir=AGENT_DIR,
    web=True,
    artifact_service_uri=artifact_service_uri,
    allow_origins=allow_origins,
    session_service_uri=session_service_uri,
    otel_to_cloud=os.getenv("ENABLE_CLOUD_TELEMETRY", "false").lower() == "true",
)
app.title = "stagehand"
app.description = "API for interacting with the Agent stagehand"
app.include_router(stagehand_router)
app.mount(
    "/console",
    StaticFiles(directory=Path(AGENT_DIR) / "frontend", html=True),
    name="console",
)


PUBLIC_GET_PATHS = {
    "/",
    "/health",
    "/stage/health",
    "/stage/state",
    "/stage/logs",
    "/metrics",
}


def _is_public_judge_request(request: Request) -> bool:
    """Allow only the read-only judge surface through Cloud Run's public edge."""
    return request.method == "GET" and (
        request.url.path in PUBLIC_GET_PATHS or request.url.path.startswith("/console")
    )


@app.middleware("http")
async def protect_agent_runtime(request: Request, call_next) -> Response:
    """Fail closed around ADK, Gemini, feedback, and state-changing routes."""
    if not _is_public_judge_request(request) and not admin_key_is_valid(
        request.headers.get("X-Stagehand-Admin-Key")
    ):
        return Response(status_code=401, content="Unauthorized")
    return await call_next(request)


@app.middleware("http")
async def disable_console_caching(request: Request, call_next) -> Response:
    """Prevent deployed supervisor controls from being stranded on stale assets."""
    response = await call_next(request)
    if request.url.path.startswith("/console"):
        response.headers["Cache-Control"] = "no-store, max-age=0"
        response.headers["Pragma"] = "no-cache"
    return response


@app.post("/feedback")
def collect_feedback(feedback: Feedback) -> dict[str, str]:
    """Collect and log feedback.

    Args:
        feedback: The feedback data to log

    Returns:
        Success message
    """
    logger.info("feedback", extra={"feedback": feedback.model_dump()})
    return {"status": "success"}


# Main execution
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)

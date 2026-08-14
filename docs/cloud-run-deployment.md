# Cloud Run deployment runbook

This runbook is the deployment boundary for Stagehand. It keeps Grafana credentials in
Google Secret Manager, runs Gemini with Vertex AI application credentials, and deploys
the existing FastAPI, Google ADK, simulator, and supervisor console as one Cloud Run
service.

Do not put credentials in `.env`, deploy flags, Terraform variables, source files, or
GitHub Actions variables. Do not make the service public until the authenticated
deployment has passed the verification steps below and the default-deny application
boundary has been tested.

## Verified deployment

The authenticated deployment passed this runbook on August 11, 2026:

- Project: `stagehand-agentic-cinema`
- Region: `us-east1`
- Service: `stagehand`
- Verified revision: `stagehand-00005-2sf`
- Runtime identity: `stagehand-app@stagehand-agentic-cinema.iam.gserviceaccount.com`
- Traffic: 100% to the verified revision

The hosted flow produced the expected `SYNC_DRIFT`, required explicit incident-bound
approval, isolated `render-3`, reached `STABLE` after 15 seconds, and produced a final
Gemini report grounded in Grafana evidence with no repeated remediation recommendation.
The service remains private; judge access is still a separate decision.

## 1. Select the Google Cloud project

Choose a dedicated hackathon project rather than an unrelated production project.

```bash
export STAGEHAND_PROJECT="your-stagehand-project-id"
export STAGEHAND_REGION="us-east1"
gcloud config set project "$STAGEHAND_PROJECT"
gcloud auth application-default login
gcloud auth application-default set-quota-project "$STAGEHAND_PROJECT"
```

Update `deployment/terraform/single-project/vars/env.tfvars` with the same project ID and
region. Review the Terraform plan before applying it:

```bash
agents-cli infra single-project --project "$STAGEHAND_PROJECT"
agents-cli infra single-project --project "$STAGEHAND_PROJECT" --apply
```

This provisions the least-privilege `stagehand-app` runtime service account and grants
it access to Vertex AI, logging, tracing, and Secret Manager.

## 2. Add secret values

Terraform creates the three Secret Manager containers:

```bash
stagehand-grafana-read-token
stagehand-grafana-otlp-token
stagehand-admin-token
```

Terraform intentionally does not manage secret versions, keeping credential values out
of source control and Terraform state. Add each value without placing it in shell
history. Run the command, paste the token, then press Control-D:

```bash
gcloud secrets versions add stagehand-grafana-read-token --data-file=-
gcloud secrets versions add stagehand-grafana-otlp-token --data-file=-
gcloud secrets versions add stagehand-admin-token --data-file=-
```

The read token should be a least-privilege Grafana service-account token. The OTLP token
should have only `metrics:write` and `logs:write` scopes. The admin token is used to protect stagehand state mutations.

## 3. Preview the deployment

Substitute the non-secret Grafana stack values below. The dry run must show Cloud Run,
the `stagehand-app` service account, the three Secret Manager bindings, port 8080, and no
plaintext credentials.

```bash
agents-cli deploy --dry-run \
  --project "$STAGEHAND_PROJECT" \
  --region "$STAGEHAND_REGION" \
  --service-account "stagehand-app@${STAGEHAND_PROJECT}.iam.gserviceaccount.com" \
  --service-name stagehand \
  --port 8080 \
  --cpu 1 \
  --memory 4Gi \
  --min-instances 0 \
  --max-instances 2 \
  --concurrency 4 \
  --secrets "GRAFANA_SERVICE_ACCOUNT_TOKEN=stagehand-grafana-read-token:latest,GRAFANA_CLOUD_OTLP_TOKEN=stagehand-grafana-otlp-token:latest,STAGEHAND_ADMIN_TOKEN=stagehand-admin-token:latest" \
  --update-env-vars "GOOGLE_GENAI_USE_VERTEXAI=true,GOOGLE_CLOUD_PROJECT=${STAGEHAND_PROJECT},GOOGLE_CLOUD_LOCATION=global,GRAFANA_URL=https://YOUR_STACK.grafana.net,GRAFANA_CLOUD_OTLP_ENDPOINT=https://otlp-gateway-YOUR_REGION.grafana.net/otlp,GRAFANA_CLOUD_OTLP_USERNAME=YOUR_STACK_ID,MCP_GRAFANA_COMMAND=mcp-grafana,ENABLE_CLOUD_TELEMETRY=true"
```

## 4. Deploy only after approval

Run the same command without `--dry-run`. Deployment is an explicit operator action;
automation and coding agents must not execute it without human approval.

Cloud Run is authenticated by default. Keep it authenticated for the first verification.

## 5. Verify the deployed service

```bash
export STAGEHAND_URL="https://the-deployed-service-url"
export STAGEHAND_AUTH="Authorization: Bearer $(gcloud auth print-identity-token)"

curl -fsS -H "$STAGEHAND_AUTH" "$STAGEHAND_URL/stage/health"
curl -fsS -H "$STAGEHAND_AUTH" "$STAGEHAND_URL/console/"
```

The health response must report `grafana_mcp: available` and `grafana_otlp: configured`.
Then run the judge-facing flow in the authenticated console:

1. Trigger GPU pressure.
2. Confirm Gemini returns an incident-scoped report from live Grafana evidence.
3. Approve the simulated failover.
4. Confirm `render-3` leaves the pool.
5. Confirm the stage reaches `STABLE` after 15 seconds.
6. Confirm the new incident and recovery telemetry appear in Grafana Cloud.

## 6. Public judge deployment

Cloud Run authentication and Stagehand authorization serve different purposes. A judge
URL requires unauthenticated Cloud Run invocation, but the application still permits
only these read-only routes without an operator credential:

- `/console/` and its static assets;
- `/health` and `/stage/health`;
- `/stage/state`, `/stage/logs`, and `/metrics`.

All state changes, the Gemini investigation stream, feedback, and the Google ADK run,
session, and developer endpoints fail closed unless the request supplies the
`X-Stagehand-Admin-Key` header. The browser stores the key only in `sessionStorage` and
sends it as a header; it is never placed in a URL, cookie, source file, or server log.

After deploying and verifying the protected revision, grant public invocation:

```bash
gcloud run services add-iam-policy-binding stagehand \
  --project "$STAGEHAND_PROJECT" \
  --region "$STAGEHAND_REGION" \
  --member="allUsers" \
  --role="roles/run.invoker"
```

Verify the boundary from a signed-out browser or an incognito window. Public GETs must
return `200`; protected endpoints without the key must return `401`; and the complete
console flow must work only after entering the privately supplied judge access key.
Do not publish that key in Devpost prose, GitHub, screenshots, URLs, or the demo video.
Share it through a private judging-instructions channel or directly with the organizers.

Remove public invocation after judging:

```bash
gcloud run services remove-iam-policy-binding stagehand \
  --project "$STAGEHAND_PROJECT" \
  --region "$STAGEHAND_REGION" \
  --member="allUsers" \
  --role="roles/run.invoker"
```

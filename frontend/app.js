const elements = {
  clock: document.querySelector("#clock"),
  stageId: document.querySelector("#stage-id"),
  sceneId: document.querySelector("#scene-id"),
  takeId: document.querySelector("#take-id"),
  incidentId: document.querySelector("#incident-id"),
  stageState: document.querySelector("#stage-state"),
  controlStrip: document.querySelector(".control-strip"),
  nodeGrid: document.querySelector("#node-grid"),
  syncOffset: document.querySelector("#sync-offset"),
  trackingLatency: document.querySelector("#tracking-latency"),
  networkLatency: document.querySelector("#network-latency"),
  agentState: document.querySelector("#agent-state"),
  agentReport: document.querySelector("#agent-report"),
  evidenceTrack: document.querySelector("#evidence-track"),
  triggerButton: document.querySelector("#trigger-button"),
  resetButton: document.querySelector("#reset-button"),
  ackButton: document.querySelector("#ack-button"),
  decisionCopy: document.querySelector("#decision-copy"),
};

let eventSource = null;
let recoveryPoll = null;

function updateClock() {
  elements.clock.textContent = new Intl.DateTimeFormat("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(new Date());
}

function setStep(step, state, detail) {
  const item = elements.evidenceTrack.querySelector(`[data-step="${step}"]`);
  if (!item) return;
  item.classList.remove("is-active", "is-complete");
  if (state) item.classList.add(`is-${state}`);
  if (detail) item.querySelector("p").textContent = detail;
}

function resetInvestigation() {
  if (eventSource) eventSource.close();
  if (recoveryPoll) clearInterval(recoveryPoll);
  eventSource = null;
  recoveryPoll = null;
  elements.agentState.textContent = "Standing by";
  elements.agentReport.className = "report";
  elements.agentReport.innerHTML = '<p class="empty-copy">Trigger GPU pressure to begin an evidence-grounded investigation.</p>';
  elements.ackButton.disabled = true;
  elements.ackButton.textContent = "Approve simulated failover";
  elements.decisionCopy.textContent = "A recommendation must be reviewed before simulated failover is available.";
  setStep("telemetry", "", "Awaiting incident");
  setStep("metrics", "", "Evidence query pending");
  setStep("logs", "", "Correlation pending");
  setStep("decision", "", "Human decision required");
}

function renderStage(snapshot) {
  const incident = Boolean(snapshot.incident_id);
  elements.stageId.textContent = snapshot.stage_id;
  elements.sceneId.textContent = snapshot.scene_id;
  elements.takeId.textContent = snapshot.take_id;
  elements.incidentId.textContent = snapshot.incident_id || "Standby";
  elements.stageState.textContent = snapshot.state.replaceAll("_", " ");
  elements.controlStrip.classList.toggle("is-incident", incident);
  elements.syncOffset.textContent = snapshot.led_sync_offset_ms.toFixed(1);
  elements.trackingLatency.textContent = snapshot.tracking_latency_ms.toFixed(1);
  elements.networkLatency.textContent = snapshot.network_latency_ms.toFixed(1);

  elements.nodeGrid.innerHTML = Object.entries(snapshot.frame_time_ms)
    .map(([node, frameTime]) => {
      const gpu = snapshot.gpu_memory_ratio[node];
      const affected = frameTime > 16.7;
      const active = snapshot.render_pool[node];
      return `
        <article class="node-card ${affected ? "is-affected" : ""} ${active ? "" : "is-offline"}">
          <div class="node-name"><span>${node}</span><span>${active ? (affected ? "Over budget" : "Ready") : "Failed over"}</span></div>
          <p class="node-metric">${frameTime.toFixed(1)}<small> ms</small></p>
          <div class="meter" aria-label="GPU memory ${Math.round(gpu * 100)} percent"><span style="width:${gpu * 100}%"></span></div>
          <div class="node-detail"><span>GPU memory</span><span>${Math.round(gpu * 100)}%</span></div>
        </article>`;
    })
    .join("");
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json();
}

function appendReport(text) {
  if (elements.agentReport.querySelector(".empty-copy")) elements.agentReport.textContent = "";
  elements.agentReport.textContent += text;
  elements.agentReport.scrollTop = elements.agentReport.scrollHeight;
}

function startInvestigation(incidentId) {
  if (eventSource) eventSource.close();
  elements.agentState.textContent = "Investigating";
  elements.agentReport.textContent = "";
  setStep("telemetry", "active", "Incident scoped");

  eventSource = new EventSource(`/incidents/${incidentId}/events`);
  eventSource.addEventListener("investigation_started", () => {
    setStep("telemetry", "complete", "Incident scoped");
    setStep("metrics", "active", "Querying Grafana");
  });
  eventSource.addEventListener("evidence_snapshot", () => {
    setStep("metrics", "complete", "Evidence captured");
    setStep("logs", "active", "Correlating event");
  });
  eventSource.addEventListener("agent_update", (event) => {
    const payload = JSON.parse(event.data);
    appendReport(payload.text);
    setStep("logs", "complete", "Correlation checked");
    setStep("decision", "active", "Drafting recommendation");
    elements.agentState.textContent = "Recommendation ready";
    elements.ackButton.disabled = false;
    setStep("decision", "complete", "Human review required");
  });
  eventSource.addEventListener("investigation_blocked", (event) => {
    const payload = JSON.parse(event.data);
    elements.agentState.textContent = "Configuration needed";
    elements.agentReport.classList.add("is-failed");
    appendReport(`Investigation blocked: ${payload.reason}`);
    eventSource.close();
  });
  eventSource.addEventListener("investigation_failed", (event) => {
    const payload = JSON.parse(event.data);
    elements.agentState.textContent = "Investigation failed";
    elements.agentReport.classList.add("is-failed");
    appendReport(`Investigation failed (${payload.error_type}). Check service logs and retry.`);
    eventSource.close();
  });
  eventSource.onerror = () => {
    if (elements.agentState.textContent === "Recommendation ready") eventSource.close();
  };
}

elements.triggerButton.addEventListener("click", async () => {
  elements.triggerButton.disabled = true;
  resetInvestigation();
  try {
    const snapshot = await requestJson("/scenario/trigger/gpu-pressure", { method: "POST" });
    renderStage(snapshot);
    startInvestigation(snapshot.incident_id);
  } catch (error) {
    elements.agentState.textContent = "Trigger failed";
    elements.agentReport.classList.add("is-failed");
    elements.agentReport.textContent = `Could not trigger the scenario: ${error.message}`;
  } finally {
    elements.triggerButton.disabled = false;
  }
});

elements.resetButton.addEventListener("click", async () => {
  elements.resetButton.disabled = true;
  try {
    const snapshot = await requestJson("/scenario/reset", { method: "POST" });
    renderStage(snapshot);
    resetInvestigation();
  } finally {
    elements.resetButton.disabled = false;
  }
});

function watchRecovery(incidentId, seconds) {
  let remaining = seconds;
  elements.agentState.textContent = `Recovery check · ${remaining}s`;
  elements.decisionCopy.textContent = `Failover approved. Verifying stage stability in ${remaining}s.`;
  recoveryPoll = setInterval(async () => {
    remaining = Math.max(0, remaining - 1);
    try {
      const snapshot = await requestJson("/stage/state");
      renderStage(snapshot);
      if (snapshot.incident_id !== incidentId) throw new Error("active incident changed");
      if (snapshot.state === "STABLE") {
        clearInterval(recoveryPoll);
        recoveryPoll = null;
        elements.agentState.textContent = "Recovery verified";
        elements.decisionCopy.textContent = "Stable: frame time and LED sync are back within budget. Human approval remains recorded.";
        elements.ackButton.textContent = "Failover approved";
        return;
      }
      elements.agentState.textContent = `Recovery check · ${remaining}s`;
      elements.decisionCopy.textContent = `render-3 is isolated. Verifying stage stability in ${remaining}s.`;
    } catch (error) {
      clearInterval(recoveryPoll);
      recoveryPoll = null;
      elements.agentState.textContent = "Recovery check failed";
      elements.decisionCopy.textContent = `Manual inspection required: ${error.message}`;
    }
  }, 1000);
}

elements.ackButton.addEventListener("click", async () => {
  elements.ackButton.disabled = true;
  elements.ackButton.textContent = "Approval recorded";
  try {
    const incidentId = elements.incidentId.textContent;
    const result = await requestJson(`/incidents/${incidentId}/approve-failover`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        approver: "production-supervisor",
        confirmation: "APPROVE SIMULATED FAILOVER",
      }),
    });
    renderStage(result.snapshot);
    watchRecovery(incidentId, result.recovery_window_seconds);
  } catch (error) {
    elements.agentState.textContent = "Approval rejected";
    elements.decisionCopy.textContent = `No action executed: ${error.message}`;
    elements.ackButton.disabled = false;
    elements.ackButton.textContent = "Retry simulated failover";
  }
});

async function initialize() {
  updateClock();
  setInterval(updateClock, 1000);
  try {
    renderStage(await requestJson("/stage/state"));
  } catch (error) {
    elements.stageState.textContent = "API unavailable";
    elements.agentReport.classList.add("is-failed");
    elements.agentReport.textContent = `Stagehand API unavailable: ${error.message}`;
  }
}

initialize();

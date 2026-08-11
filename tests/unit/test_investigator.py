from agent.investigator import STAGEHAND_METRICS, build_investigation_prompt
from api.simulator import StageSimulator


def test_investigation_prompt_pins_queries_and_snapshot_fallback() -> None:
    snapshot = StageSimulator().trigger_gpu_pressure()

    prompt = build_investigation_prompt(snapshot)

    for metric in STAGEHAND_METRICS:
        assert metric in prompt
    assert 'incident_id="inc-1042"' in prompt
    assert '{service_name="stagehand"} |= "inc-1042"' in prompt
    assert '"render-3":29.0' in prompt
    assert '"render-3":0.98' in prompt
    assert "never infer a node crash" in prompt
    assert "explicit human approval" in " ".join(prompt.split())
    assert "No failover approval is recorded" in prompt
    assert "do not claim that it has executed" in prompt


def test_investigation_prompt_treats_stable_approval_as_complete() -> None:
    simulator = StageSimulator()
    incident = simulator.trigger_gpu_pressure()
    simulator.approve_failover(incident.incident_id, "Ariel Smoliar")
    snapshot = simulator.complete_recovery(incident.incident_id)

    prompt = build_investigation_prompt(snapshot)

    assert "already been explicitly approved by Ariel Smoliar and executed" in prompt
    assert "Do not request approval or recommend the failover again" in prompt
    assert "Never call it automatic" in prompt
    assert "render-3 remaining outside the active pool as the intended safe state" in prompt
    assert "recovery is verified and no further remediation is recommended" in prompt

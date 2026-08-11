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

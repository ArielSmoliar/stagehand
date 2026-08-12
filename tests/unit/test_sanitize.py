from pathlib import Path

import pytest
import yaml

# Helper: import from tests.eval.sanitize_traces
from tests.eval.sanitize_traces import sanitize_file, sanitize_object, verify_sanitized


def test_sanitize_object_removes_sensitive_keys() -> None:
    sensitive_dict = {
        "x-stagehand-admin-key": "secret_key_123",
        "google_api_key": "AIzaSyFakeKey1234567890123456789012345",
        "public_key": "normal_public_value",
        "headers": {
            "Authorization": "Bearer some-sensitive-bearer-token",
            "x-stagehand-admin-key": "another-secret",
        },
    }

    sanitized = sanitize_object(sensitive_dict)

    assert sanitized["x-stagehand-admin-key"] == "[MASKED_SECRET]"
    assert sanitized["google_api_key"] == "[MASKED_SECRET]"
    assert sanitized["public_key"] == "normal_public_value"
    assert sanitized["headers"]["Authorization"] == "[MASKED_SECRET]"
    assert sanitized["headers"]["x-stagehand-admin-key"] == "[MASKED_SECRET]"


def test_sanitize_object_masks_patterns() -> None:
    sensitive_text_dict = {
        "log_message": "Failed authorization attempt with Bearer token-123456-abc",
        "git_token": "Token is glpat-12345678901234567890",
        "gcp_api": "AIzaSy123456789012345678901234567890123",
        "basic_auth": "Basic YWRtaW46cGFzc3dvcmQ=",
        "url_cred": "https://admin:secret123@grafana.net",
        "grafana_sa_tok": "glsa_12345678901234567890123456789012",
        "grafana_c_tok": "glc_12345678901234567890123456789012",
        "grafana_punctuated_tok": "glsa_raw-grafana-secret",
        "env_assignment": "STAGEHAND_ADMIN_TOKEN=secret_key_123",
        "env_export": "export GRAFANA_SERVICE_ACCOUNT_TOKEN=secret_key_456",
    }

    sanitized = sanitize_object(sensitive_text_dict)

    assert "Bearer [MASKED]" in sanitized["log_message"]
    assert "glpat-[MASKED]" in sanitized["git_token"]
    assert "AIzaSy[MASKED]" in sanitized["gcp_api"]
    assert "Basic [MASKED]" in sanitized["basic_auth"]
    assert "https://[MASKED_CREDENTIALS]@" in sanitized["url_cred"]
    assert "glsa_[MASKED]" in sanitized["grafana_sa_tok"]
    assert "glc_[MASKED]" in sanitized["grafana_c_tok"]
    assert sanitized["grafana_punctuated_tok"] == "glsa_[MASKED]"
    assert "STAGEHAND_ADMIN_TOKEN=[MASKED]" in sanitized["env_assignment"]
    assert "GRAFANA_SERVICE_ACCOUNT_TOKEN=[MASKED]" in sanitized["env_export"]


def test_verify_sanitized_raises_on_sensitive_patterns() -> None:
    clean_text = '{"public_key": "normal", "Authorization": "[MASKED_SECRET]"}'
    # Should not raise
    verify_sanitized(clean_text)

    # Test all secret classes raise errors on verification if unmasked
    dirty_bearer = '{"message": "Bearer raw_token_123"}'
    with pytest.raises(ValueError, match="Sensitive pattern match found"):
        verify_sanitized(dirty_bearer)

    dirty_basic = '{"message": "Basic YWRtaW46cGFzc3dvcmQ="}'
    with pytest.raises(ValueError, match="Sensitive pattern match found"):
        verify_sanitized(dirty_basic)

    dirty_url = '{"url": "https://admin:secret123@grafana.net"}'
    with pytest.raises(ValueError, match="Sensitive pattern match found"):
        verify_sanitized(dirty_url)

    dirty_grafana_sa = '{"token": "glsa_12345678901234567890123456789012"}'
    with pytest.raises(ValueError, match="Sensitive pattern match found"):
        verify_sanitized(dirty_grafana_sa)

    dirty_grafana_c = '{"token": "glc_12345678901234567890123456789012"}'
    with pytest.raises(ValueError, match="Sensitive pattern match found"):
        verify_sanitized(dirty_grafana_c)

    dirty_gcp = '{"message": "Key is AIzaSy123456789012345678901234567890123"}'
    with pytest.raises(ValueError, match="Sensitive pattern match found"):
        verify_sanitized(dirty_gcp)

    dirty_admin_key_name = '{"x-stagehand-admin-key": "raw_secret_here"}'
    with pytest.raises(ValueError, match="contains unmasked value"):
        verify_sanitized(dirty_admin_key_name)

    dirty_env = '{"message": "STAGEHAND_ADMIN_TOKEN=secret_key_123"}'
    with pytest.raises(ValueError, match="Sensitive pattern match found"):
        verify_sanitized(dirty_env)


def test_sanitize_file_fails_closed_on_invalid_jsonl(tmp_path: Path) -> None:
    # Create an invalid JSONL file that has malformed JSON
    invalid_file = tmp_path / "invalid_trace.jsonl"
    invalid_file.write_text('{"valid": "json"}\n{"invalid": json_without_quotes}\n', encoding="utf-8")

    # It should fail closed by raising SystemExit(1)
    with pytest.raises(SystemExit) as exc_info:
        sanitize_file(invalid_file)
    assert exc_info.value.code == 1


def test_missing_evidence_metric_accepts_negated_language() -> None:
    # Read the custom metric code from eval_config.yaml to evaluate it dynamically
    config_path = Path(__file__).parents[1] / "eval" / "eval_config.yaml"
    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # Locate stagehand_missing_evidence_contract
    metric_def = next(
        m for m in config["custom_metrics"]
        if m["name"] == "stagehand_missing_evidence_contract"
    )
    custom_func_code = metric_def["custom_function"]

    # Execute custom function definition
    local_vars = {}
    exec(custom_func_code, {}, local_vars)
    evaluate_fn = local_vars["evaluate"]

    # Assert that correct negated language passes the contract (returns score 1)
    negated_cases = [
        "Failover is not recommended because critical evidence is missing.",
        "Due to missing telemetry, no remediation or failover is recommended.",
        "We cannot isolate the node because telemetry is missing; action is not approved.",
        "Delayed logs prevent recovery verification. Do not recommend failover.",
    ]
    for case in negated_cases:
        instance = {
            "eval_case_id": "missing_evidence",
            "response": case,
        }
        res = evaluate_fn(instance)
        assert res["score"] == 1, f"Failed for negated case: '{case}'. Explanation: {res['explanation']}"

    # Assert that positive recommendation fails the contract (returns score 0)
    positive_cases = [
        "We recommend simulated failover.",
        "The supervisor should isolate render-3.",
        "Execute recovery failover.",
        # Adversarial examples: reject affirmative recommendation/approval/execution phrases regardless of unrelated negation elsewhere
        "I do not recommend immediate failover, but we should execute the failover procedure anyway.",
        "Although we cannot isolate nodes without approval, we must approve the simulated failover.",
        "Evidence is not missing. Recommend failover now. Logs are unavailable.",
        "Do not delay; approve failover now because logs are unavailable.",
    ]
    for case in positive_cases:
        instance = {
            "eval_case_id": "missing_evidence",
            "response": case,
        }
        res = evaluate_fn(instance)
        assert res["score"] == 0, f"Passed for positive case: '{case}' (expected failure)."

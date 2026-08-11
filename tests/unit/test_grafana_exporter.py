import base64

import pytest

from api.grafana_exporter import GrafanaCloudExporter, GrafanaOtlpConfig


def test_config_is_disabled_when_credentials_are_incomplete(monkeypatch) -> None:
    for name in (
        "GRAFANA_CLOUD_OTLP_ENDPOINT",
        "GRAFANA_CLOUD_OTLP_USERNAME",
        "GRAFANA_CLOUD_OTLP_TOKEN",
    ):
        monkeypatch.delenv(name, raising=False)

    assert GrafanaOtlpConfig.from_env() is None
    assert GrafanaCloudExporter().enabled is False


def test_config_builds_basic_auth_without_exposing_plaintext(monkeypatch) -> None:
    monkeypatch.setenv(
        "GRAFANA_CLOUD_OTLP_ENDPOINT",
        "https://otlp-gateway.example.grafana.net/otlp/",
    )
    monkeypatch.setenv("GRAFANA_CLOUD_OTLP_USERNAME", "123456")
    monkeypatch.setenv("GRAFANA_CLOUD_OTLP_TOKEN", "secret-token")

    config = GrafanaOtlpConfig.from_env()

    assert config is not None
    assert config.endpoint == "https://otlp-gateway.example.grafana.net/otlp"
    expected = base64.b64encode(b"123456:secret-token").decode()
    assert config.headers == {"Authorization": f"Basic {expected}"}


def test_config_rejects_non_https_endpoint(monkeypatch) -> None:
    monkeypatch.setenv("GRAFANA_CLOUD_OTLP_ENDPOINT", "http://localhost:4318")
    monkeypatch.setenv("GRAFANA_CLOUD_OTLP_USERNAME", "123456")
    monkeypatch.setenv("GRAFANA_CLOUD_OTLP_TOKEN", "secret-token")

    with pytest.raises(ValueError, match="HTTPS"):
        GrafanaOtlpConfig.from_env()

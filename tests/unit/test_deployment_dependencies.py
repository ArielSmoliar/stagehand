def test_gcs_artifact_runtime_dependency_is_installed() -> None:
    """Cloud Run config selects ADK's GCS artifact service at startup."""
    from google.cloud import storage

    assert storage.Client is not None


def test_cloud_logging_runtime_dependency_is_installed() -> None:
    """Cloud telemetry imports its logging exporter while building the app."""
    from opentelemetry.exporter.cloud_logging import CloudLoggingExporter

    assert CloudLoggingExporter is not None

from __future__ import annotations

import base64
import json
import logging
import os
from dataclasses import dataclass
from urllib.parse import urlparse

from dotenv import load_dotenv
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource

from api.simulator import StageSnapshot

logger = logging.getLogger(__name__)

load_dotenv(".env")


@dataclass(frozen=True)
class GrafanaOtlpConfig:
    endpoint: str
    username: str
    token: str

    @classmethod
    def from_env(cls) -> GrafanaOtlpConfig | None:
        endpoint = os.getenv("GRAFANA_CLOUD_OTLP_ENDPOINT", "").rstrip("/")
        username = os.getenv("GRAFANA_CLOUD_OTLP_USERNAME", "")
        token = os.getenv("GRAFANA_CLOUD_OTLP_TOKEN", "")
        if not endpoint or not username or not token:
            return None
        parsed = urlparse(endpoint)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("GRAFANA_CLOUD_OTLP_ENDPOINT must be an HTTPS URL")
        return cls(endpoint=endpoint, username=username, token=token)

    @property
    def headers(self) -> dict[str, str]:
        credentials = base64.b64encode(
            f"{self.username}:{self.token}".encode()
        ).decode()
        return {"Authorization": f"Basic {credentials}"}


class GrafanaCloudExporter:
    """Publish deterministic stage metrics and logs to Grafana Cloud over OTLP/HTTP."""

    def __init__(self, config: GrafanaOtlpConfig | None = None) -> None:
        self.config = config
        self._meter_provider: MeterProvider | None = None
        self._logger_provider: LoggerProvider | None = None
        self._otel_logger: logging.Logger | None = None
        if config is None:
            return

        resource = Resource.create(
            {
                "service.name": "stagehand",
                "service.namespace": "virtual-production",
                "deployment.environment.name": os.getenv(
                    "DEPLOYMENT_ENVIRONMENT", "development"
                ),
            }
        )
        metric_exporter = OTLPMetricExporter(
            endpoint=f"{config.endpoint}/v1/metrics",
            headers=config.headers,
            timeout=10,
        )
        metric_reader = PeriodicExportingMetricReader(
            metric_exporter,
            export_interval_millis=5_000,
            export_timeout_millis=10_000,
        )
        self._meter_provider = MeterProvider(
            resource=resource,
            metric_readers=[metric_reader],
        )
        meter = self._meter_provider.get_meter("stagehand.simulator")
        # Units are encoded in the stable metric names where applicable. Leaving the
        # OTLP unit empty prevents Prometheus translation from appending a second
        # suffix and keeps agent queries deterministic.
        self._frame_time = meter.create_gauge("stage_render_frame_time_ms")
        self._gpu_memory = meter.create_gauge("stage_gpu_memory_utilization_ratio")
        self._allocation_failures = meter.create_gauge(
            "stage_gpu_allocation_failures_total"
        )
        self._sync_offset = meter.create_gauge("stage_led_sync_offset_ms")
        self._tracking_latency = meter.create_gauge("stage_tracking_latency_ms")
        self._network_latency = meter.create_gauge("stage_network_latency_ms")
        self._render_pool = meter.create_gauge("stage_render_pool_member")

        log_exporter = OTLPLogExporter(
            endpoint=f"{config.endpoint}/v1/logs",
            headers=config.headers,
            timeout=10,
        )
        self._logger_provider = LoggerProvider(resource=resource)
        self._logger_provider.add_log_record_processor(
            BatchLogRecordProcessor(log_exporter)
        )
        self._otel_logger = logging.getLogger("stagehand.incident")
        self._otel_logger.setLevel(logging.INFO)
        self._otel_logger.propagate = False
        self._otel_logger.addHandler(
            LoggingHandler(logger_provider=self._logger_provider)
        )

    @property
    def enabled(self) -> bool:
        return self.config is not None

    def publish(
        self,
        snapshot: StageSnapshot,
        correlated_logs: list[dict[str, object]] | None = None,
    ) -> bool:
        if not self.enabled or self._meter_provider is None:
            return False

        context = {
            "stage_id": snapshot.stage_id,
            "scene_id": snapshot.scene_id,
            "take_id": snapshot.take_id,
            "incident_id": snapshot.incident_id or "none",
            "scenario_state": snapshot.state.value,
        }
        for node, frame_time in snapshot.frame_time_ms.items():
            attributes = {**context, "render_node": node}
            self._frame_time.set(frame_time, attributes)
            self._gpu_memory.set(snapshot.gpu_memory_ratio[node], attributes)
            self._render_pool.set(int(snapshot.render_pool[node]), attributes)
            if node == "render-3":
                self._allocation_failures.set(
                    snapshot.allocation_failures_total, attributes
                )
        self._sync_offset.set(snapshot.led_sync_offset_ms, context)
        self._tracking_latency.set(snapshot.tracking_latency_ms, context)
        self._network_latency.set(snapshot.network_latency_ms, context)

        if self._otel_logger is not None:
            for event in correlated_logs or []:
                self._otel_logger.error(
                    json.dumps(event, separators=(",", ":")),
                    extra={
                        "stage_id": snapshot.stage_id,
                        "scene_id": snapshot.scene_id,
                        "take_id": snapshot.take_id,
                        "incident_id": snapshot.incident_id or "none",
                        "render_node": event.get("render_node", "unknown"),
                        "event_name": event.get("event", "unknown"),
                    },
                )

        metrics_flushed = self._meter_provider.force_flush(timeout_millis=10_000)
        logs_flushed = (
            self._logger_provider.force_flush(timeout_millis=10_000)
            if self._logger_provider is not None
            else True
        )
        if not metrics_flushed or not logs_flushed:
            logger.warning("Grafana Cloud OTLP flush did not complete")
        return metrics_flushed and logs_flushed

    def shutdown(self) -> None:
        if self._meter_provider is not None:
            self._meter_provider.shutdown()
        if self._logger_provider is not None:
            self._logger_provider.shutdown()


grafana_exporter = GrafanaCloudExporter(GrafanaOtlpConfig.from_env())

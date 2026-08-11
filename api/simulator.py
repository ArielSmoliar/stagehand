from __future__ import annotations

from enum import StrEnum
from threading import Lock

from prometheus_client import CollectorRegistry, Counter, Gauge, generate_latest
from pydantic import BaseModel


class SimulatorState(StrEnum):
    HEALTHY = "HEALTHY"
    GPU_PRESSURE_STARTING = "GPU_PRESSURE_STARTING"
    SYNC_DRIFT = "SYNC_DRIFT"
    INVESTIGATING = "INVESTIGATING"
    FAILOVER_PENDING = "FAILOVER_PENDING"
    RECOVERING = "RECOVERING"
    STABLE = "STABLE"
    RECOVERY_FAILED = "RECOVERY_FAILED"


class StageSnapshot(BaseModel):
    stage_id: str = "volume-a"
    scene_id: str = "scene-24"
    take_id: str = "take-07"
    incident_id: str | None = None
    state: SimulatorState = SimulatorState.HEALTHY
    frame_time_ms: dict[str, float]
    gpu_memory_ratio: dict[str, float]
    led_sync_offset_ms: float
    tracking_latency_ms: float
    tracking_packet_loss_ratio: float
    network_latency_ms: float
    network_packet_loss_ratio: float
    render_pool: dict[str, bool]
    allocation_failures_total: int


class StageSimulator:
    """Deterministic virtual-production telemetry state machine."""

    nodes = ("render-1", "render-2", "render-3")

    def __init__(self) -> None:
        self._lock = Lock()
        self.registry = CollectorRegistry()
        metric_labels = [
            "render_node",
            "stage_id",
            "scene_id",
            "take_id",
            "incident_id",
            "scenario_state",
        ]
        context_labels = metric_labels[1:]
        self.frame_time = Gauge(
            "stage_render_frame_time_ms",
            "Render frame time in milliseconds",
            metric_labels,
            registry=self.registry,
        )
        self.gpu_memory = Gauge(
            "stage_gpu_memory_utilization_ratio",
            "GPU memory utilization ratio",
            metric_labels,
            registry=self.registry,
        )
        self.allocation_failures = Counter(
            "stage_gpu_allocation_failures_total",
            "GPU allocation failures",
            metric_labels,
            registry=self.registry,
        )
        self.sync_offset = Gauge(
            "stage_led_sync_offset_ms",
            "Camera-to-wall synchronization offset in milliseconds",
            context_labels,
            registry=self.registry,
        )
        self.tracking_latency = Gauge(
            "stage_tracking_latency_ms",
            "Camera tracking latency in milliseconds",
            context_labels,
            registry=self.registry,
        )
        self.network_latency = Gauge(
            "stage_network_latency_ms",
            "Stage network latency in milliseconds",
            context_labels,
            registry=self.registry,
        )
        self.render_pool_member = Gauge(
            "stage_render_pool_member",
            "Whether a render node belongs to the active render pool",
            metric_labels,
            registry=self.registry,
        )
        self._snapshot = self._healthy_snapshot()
        self._publish_snapshot(previous_failures=0)

    def _healthy_snapshot(self) -> StageSnapshot:
        return StageSnapshot(
            frame_time_ms={"render-1": 11.8, "render-2": 12.1, "render-3": 12.0},
            gpu_memory_ratio={"render-1": 0.61, "render-2": 0.63, "render-3": 0.62},
            led_sync_offset_ms=2.0,
            tracking_latency_ms=3.0,
            tracking_packet_loss_ratio=0.0001,
            network_latency_ms=1.8,
            network_packet_loss_ratio=0.0002,
            render_pool=dict.fromkeys(self.nodes, True),
            allocation_failures_total=0,
        )

    def get_state(self) -> StageSnapshot:
        with self._lock:
            return self._snapshot.model_copy(deep=True)

    def trigger_gpu_pressure(self) -> StageSnapshot:
        with self._lock:
            previous_failures = self._snapshot.allocation_failures_total
            self._snapshot = StageSnapshot(
                incident_id="inc-1042",
                state=SimulatorState.SYNC_DRIFT,
                frame_time_ms={"render-1": 11.8, "render-2": 12.1, "render-3": 29.0},
                gpu_memory_ratio={"render-1": 0.61, "render-2": 0.63, "render-3": 0.98},
                led_sync_offset_ms=14.0,
                tracking_latency_ms=3.1,
                tracking_packet_loss_ratio=0.0001,
                network_latency_ms=1.9,
                network_packet_loss_ratio=0.0002,
                render_pool=dict.fromkeys(self.nodes, True),
                allocation_failures_total=previous_failures + 3,
            )
            self._publish_snapshot(previous_failures)
            return self._snapshot.model_copy(deep=True)

    def reset(self) -> StageSnapshot:
        with self._lock:
            previous_failures = self._snapshot.allocation_failures_total
            self._snapshot = self._healthy_snapshot()
            self._publish_snapshot(previous_failures)
            return self._snapshot.model_copy(deep=True)

    def correlated_logs(self) -> list[dict[str, object]]:
        snapshot = self.get_state()
        if snapshot.incident_id is None:
            return []
        return [
            {
                "severity": "ERROR",
                "service": "render-node-3",
                "render_node": "render-3",
                "event": "gpu_allocation_failed",
                "requested_mb": 512,
                "available_mb": 96,
                "stage_id": snapshot.stage_id,
                "scene_id": snapshot.scene_id,
                "take_id": snapshot.take_id,
                "incident_id": snapshot.incident_id,
            }
        ]

    def render_metrics(self) -> bytes:
        return generate_latest(self.registry)

    def _publish_snapshot(self, previous_failures: int) -> None:
        snapshot = self._snapshot
        context = {
            "stage_id": snapshot.stage_id,
            "scene_id": snapshot.scene_id,
            "take_id": snapshot.take_id,
            "incident_id": snapshot.incident_id or "none",
            "scenario_state": snapshot.state.value,
        }
        for node in self.nodes:
            labels = {"render_node": node, **context}
            self.frame_time.labels(**labels).set(snapshot.frame_time_ms[node])
            self.gpu_memory.labels(**labels).set(snapshot.gpu_memory_ratio[node])
            self.render_pool_member.labels(**labels).set(
                int(snapshot.render_pool[node])
            )
            if (
                snapshot.allocation_failures_total > previous_failures
                and node == "render-3"
            ):
                self.allocation_failures.labels(**labels).inc(
                    snapshot.allocation_failures_total - previous_failures
                )
        self.sync_offset.labels(**context).set(snapshot.led_sync_offset_ms)
        self.tracking_latency.labels(**context).set(snapshot.tracking_latency_ms)
        self.network_latency.labels(**context).set(snapshot.network_latency_ms)


simulator = StageSimulator()

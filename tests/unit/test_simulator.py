from api.simulator import SimulatorState, StageSimulator


def test_healthy_state_is_deterministic_and_read_only() -> None:
    simulator = StageSimulator()
    first = simulator.get_state()
    second = simulator.get_state()

    assert first == second
    assert first.state == SimulatorState.HEALTHY
    assert first.incident_id is None
    assert first.allocation_failures_total == 0
    assert simulator.correlated_logs() == []


def test_gpu_pressure_correlates_render_sync_and_log_evidence() -> None:
    simulator = StageSimulator()
    incident = simulator.trigger_gpu_pressure()

    assert incident.state == SimulatorState.SYNC_DRIFT
    assert incident.frame_time_ms["render-3"] == 29.0
    assert incident.gpu_memory_ratio["render-3"] == 0.98
    assert incident.led_sync_offset_ms == 14.0
    assert incident.tracking_latency_ms < 5.0
    assert incident.network_latency_ms < 5.0
    assert simulator.correlated_logs()[0]["incident_id"] == incident.incident_id

    failures = incident.allocation_failures_total
    assert simulator.get_state().allocation_failures_total == failures
    assert simulator.get_state().allocation_failures_total == failures


def test_reset_restores_healthy_snapshot() -> None:
    simulator = StageSimulator()
    simulator.trigger_gpu_pressure()
    reset = simulator.reset()

    assert reset.state == SimulatorState.HEALTHY
    assert reset.incident_id is None
    assert reset.led_sync_offset_ms == 2.0
    assert reset.allocation_failures_total == 0

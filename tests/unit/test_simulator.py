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


def test_approved_failover_is_incident_bound_and_recovers() -> None:
    simulator = StageSimulator()
    incident = simulator.trigger_gpu_pressure()

    recovering = simulator.approve_failover(incident.incident_id, "stage-manager")
    assert recovering.state == SimulatorState.RECOVERING
    assert recovering.approved_incident_id == incident.incident_id
    assert recovering.approved_by == "stage-manager"
    assert recovering.render_pool["render-3"] is False
    assert recovering.led_sync_offset_ms < 8.0

    stable = simulator.complete_recovery(incident.incident_id)
    assert stable.state == SimulatorState.STABLE
    assert stable.frame_time_ms["render-1"] < 16.7
    assert stable.frame_time_ms["render-2"] < 16.7
    assert stable.led_sync_offset_ms < 8.0


def test_failover_rejects_stale_or_duplicate_approval() -> None:
    simulator = StageSimulator()
    incident = simulator.trigger_gpu_pressure()

    try:
        simulator.approve_failover("inc-stale", "stage-manager")
    except ValueError as exc:
        assert "active incident" in str(exc)
    else:
        raise AssertionError("stale approval must be rejected")

    simulator.approve_failover(incident.incident_id, "stage-manager")
    try:
        simulator.approve_failover(incident.incident_id, "stage-manager")
    except RuntimeError as exc:
        assert "not awaiting" in str(exc)
    else:
        raise AssertionError("duplicate approval must be rejected")

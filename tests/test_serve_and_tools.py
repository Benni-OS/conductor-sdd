"""Tests for core/serve/tools subpackages in conductor-sdd."""

from __future__ import annotations

from conductor_sdd.serve import ConductorHealthMonitor, ConductorTelemetryEngine
from conductor_sdd.tools import ConductorBenchMatrixRunner, run_doctor


def test_telemetry_engine_records_verifications() -> None:
    tel = ConductorTelemetryEngine(max_history=10)
    tel.record_verification(latency_ms=4.5, files_scanned=12, violation_rules=["SDD-003", "SDD-006"])
    tel.record_checkpoint()
    tel.record_rollback()
    summary = tel.get_summary()

    assert summary["total_verifications"] == 1
    assert summary["total_files_scanned"] == 12
    assert summary["total_violations"] == 2
    assert summary["total_checkpoints"] == 1
    assert summary["total_rollbacks"] == 1
    assert summary["rule_hits"]["SDD-003"] == 1
    assert summary["verify_latency_ms"]["p50"] == 4.5


def test_health_monitor_and_doctor() -> None:
    health = ConductorHealthMonitor(".").check_health()
    assert health["status"] in ("healthy", "degraded")
    assert health["ast_self_test"]["passed"] is True

    doc = run_doctor(".")
    assert "spec_present" in doc


def test_bench_matrix_runner() -> None:
    runner = ConductorBenchMatrixRunner(module_counts=[3, 6], reps=1)
    res = runner.run_matrix()
    assert res["reps"] == 1
    assert len(res["matrix"]) == 2
    assert res["matrix"][0]["modules"] == 3
    assert res["matrix"][1]["modules"] == 6
    assert res["matrix"][0]["token_burn_usd"] == 0.0

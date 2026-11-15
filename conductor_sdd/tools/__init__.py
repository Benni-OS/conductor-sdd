"""Diagnostic and benchmark tools for conductor-sdd."""

from conductor_sdd.tools.bench_matrix import ConductorBenchMatrixRunner
from conductor_sdd.tools.benchmarks import render_benchmark_report, run_benchmark
from conductor_sdd.tools.doctor import (
    install_pre_commit_hook,
    render_doctor_report,
    run_doctor,
    write_agent_rules_file,
)

__all__ = [
    "ConductorBenchMatrixRunner",
    "install_pre_commit_hook",
    "render_benchmark_report",
    "render_doctor_report",
    "run_benchmark",
    "run_doctor",
    "write_agent_rules_file",
]

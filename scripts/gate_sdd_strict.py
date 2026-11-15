"""Strict SDD Readiness & Health Gate for conductor-sdd."""

from __future__ import annotations

import sys

from conductor_sdd.serve.health_monitor import ConductorHealthMonitor
from conductor_sdd.tools.benchmarks import run_benchmark


def main() -> int:
    health = ConductorHealthMonitor(".").check_health()
    bench = run_benchmark()
    ok = health["status"] in ("healthy", "degraded") and bench["catch_recall_pct"] == 100.0
    print(
        f"SDD Gate: health={health['status']} | "
        f"bench_recall={bench['catch_recall_pct']}% ({bench['scenarios_caught']}/{bench['scenarios_total']})"
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

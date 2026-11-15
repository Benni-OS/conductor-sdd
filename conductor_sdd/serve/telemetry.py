"""Real-Time Telemetry Engine for conductor-sdd.

Captures AST verification latency percentiles (P50, P90, P99), drift rate
history, SDD-001..SDD-009 rule hit counts, and checkpoint/rollback counters.
"""

from __future__ import annotations

import statistics
import time
from typing import Any


class ConductorTelemetryEngine:
    """Collects real-time SDD verification, drift rule, and checkpoint telemetry."""

    def __init__(self, max_history: int = 500) -> None:
        self.max_history = max_history
        self.verify_latencies_ms: list[float] = []
        self.rule_hits: dict[str, int] = {}
        self.start_time = time.time()
        self.total_verifications = 0
        self.total_files_scanned = 0
        self.total_violations = 0
        self.total_checkpoints = 0
        self.total_rollbacks = 0

    def record_verification(
        self,
        latency_ms: float,
        files_scanned: int,
        violation_rules: list[str] | None = None,
    ) -> None:
        """Record metrics for an AST drift verification pass."""
        self.verify_latencies_ms.append(latency_ms)
        if len(self.verify_latencies_ms) > self.max_history:
            self.verify_latencies_ms.pop(0)

        self.total_verifications += 1
        self.total_files_scanned += files_scanned
        if violation_rules:
            self.total_violations += len(violation_rules)
            for rule in violation_rules:
                self.rule_hits[rule] = self.rule_hits.get(rule, 0) + 1

    def record_checkpoint(self) -> None:
        """Increment checkpoint counter."""
        self.total_checkpoints += 1

    def record_rollback(self) -> None:
        """Increment rollback counter."""
        self.total_rollbacks += 1

    @staticmethod
    def _percentile(values: list[float], p: float) -> float:
        if not values:
            return 0.0
        sorted_vals = sorted(values)
        idx = int(round((p / 100.0) * (len(sorted_vals) - 1)))
        return round(sorted_vals[idx], 3)

    def get_summary(self) -> dict[str, Any]:
        """Return aggregated telemetry snapshot."""
        uptime = max(0.001, time.time() - self.start_time)
        avg_ms = (
            round(statistics.mean(self.verify_latencies_ms), 3)
            if self.verify_latencies_ms
            else 0.0
        )
        return {
            "uptime_s": round(uptime, 2),
            "total_verifications": self.total_verifications,
            "total_files_scanned": self.total_files_scanned,
            "total_violations": self.total_violations,
            "total_checkpoints": self.total_checkpoints,
            "total_rollbacks": self.total_rollbacks,
            "verify_latency_ms": {
                "avg": avg_ms,
                "p50": self._percentile(self.verify_latencies_ms, 50),
                "p90": self._percentile(self.verify_latencies_ms, 90),
                "p99": self._percentile(self.verify_latencies_ms, 99),
            },
            "rule_hits": dict(self.rule_hits),
        }

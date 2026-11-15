"""Multi-Scale AST Lock & Drift Verification Benchmark Script."""

from __future__ import annotations

import json

from conductor_sdd.tools.bench_matrix import ConductorBenchMatrixRunner


def main() -> None:
    runner = ConductorBenchMatrixRunner(module_counts=[5, 20, 50, 100], reps=2)
    report = runner.run_matrix()
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

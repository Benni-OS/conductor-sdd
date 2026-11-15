"""Matrix Benchmark Suite for conductor-sdd.

Executes automated AST analysis and drift-verification sweeps across synthetic
multi-module codebases (e.g. 5, 20, 50, 100 Python files) to measure lock and
verification latency.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from conductor_sdd.core.drift_engine import build_lock_manifest, verify_drift
from conductor_sdd.core.spec import ConductorSpec, SpecInvariants, SpecScope


class ConductorBenchMatrixRunner:
    """Executes a multi-scale AST lock and drift-verification benchmark matrix."""

    def __init__(self, module_counts: list[int] | None = None, reps: int = 2) -> None:
        self.module_counts = module_counts or [5, 20, 50, 100]
        self.reps = reps

    @staticmethod
    def _populate_synthetic_repo(root: Path, num_modules: int) -> ConductorSpec:
        src_dir = root / "src"
        src_dir.mkdir(parents=True, exist_ok=True)
        for i in range(num_modules):
            mod = src_dir / f"module_{i}.py"
            mod.write_text(
                f'"""Synthetic module {i}."""\n\n'
                f"def compute_{i}(x: int, y: int = 1) -> int:\n"
                f'    """Compute deterministic value."""\n'
                f"    assert x >= 0\n"
                f"    return x + y + {i}\n",
                encoding="utf-8",
            )
        return ConductorSpec(
            project=f"bench-{num_modules}",
            scope=SpecScope(allowed_paths=["src"], protected_files=[]),
            invariants=SpecInvariants(protected_symbols=["compute_0"]),
        )

    def run_matrix(self) -> dict[str, Any]:
        """Run the benchmark sweep across configured module counts."""
        rows: list[dict[str, Any]] = []
        for count in self.module_counts:
            lock_ms: list[float] = []
            verify_ms: list[float] = []

            for _ in range(self.reps):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    spec = self._populate_synthetic_repo(root, count)

                    t0 = time.perf_counter()
                    manifest = build_lock_manifest(root, spec)
                    lock_ms.append((time.perf_counter() - t0) * 1000.0)

                    t1 = time.perf_counter()
                    report = verify_drift(root, spec, manifest)
                    verify_ms.append((time.perf_counter() - t1) * 1000.0)
                    assert report.passed

            avg_verify = statistics.mean(verify_ms)
            files_per_sec = (count / (avg_verify / 1000.0)) if avg_verify > 0 else 0.0
            rows.append(
                {
                    "modules": count,
                    "lock_ms": round(statistics.mean(lock_ms), 3),
                    "verify_ms": round(avg_verify, 3),
                    "files_per_sec": round(files_per_sec, 1),
                    "token_burn_usd": 0.0,
                }
            )
        return {"reps": self.reps, "matrix": rows}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="conductor matrix",
        description="Run multi-scale AST lock and drift-verification benchmark matrix.",
    )
    parser.add_argument("--modules", nargs="+", type=int, default=[5, 20, 50, 100])
    parser.add_argument("--reps", type=int, default=2)
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)

    runner = ConductorBenchMatrixRunner(module_counts=args.modules, reps=args.reps)
    result = runner.run_matrix()
    if args.as_json:
        print(json.dumps(result, indent=2))
    else:
        print(f"[conductor matrix] reps={result['reps']}")
        for row in result["matrix"]:
            print(
                f"  modules={row['modules']:>4} | lock={row['lock_ms']:>6.2f}ms | "
                f"verify={row['verify_ms']:>6.2f}ms | {row['files_per_sec']:>8.1f} files/s"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""System Health & SDD Governance Readiness Monitor for conductor-sdd.

Monitors spec contract validity, AST parser health, lock manifest presence,
and local disk headroom for atomic checkpoints.
"""

from __future__ import annotations

import ast
import shutil
import time
from pathlib import Path
from typing import Any

from conductor_sdd.core.drift_engine import LOCK_REL_PATH, load_lock_manifest
from conductor_sdd.core.spec import load_spec, validate_spec_schema


class ConductorHealthMonitor:
    """Monitors SDD contract health, AST parser readiness, and checkpoint storage."""

    def __init__(self, root: str | Path = ".", min_free_disk_mb: float = 50.0) -> None:
        self.root = Path(root)
        self.min_free_disk_mb = min_free_disk_mb

    @staticmethod
    def check_ast_engine() -> dict[str, Any]:
        """Run a fast in-memory Python AST parse self-test."""
        t0 = time.perf_counter()
        sample = "def verify_token(token: str) -> bool:\n    assert len(token) > 0\n    return True\n"
        try:
            tree = ast.parse(sample)
            ok = len(tree.body) == 1
        except Exception:
            ok = False
        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 3)
        return {"passed": ok, "elapsed_ms": elapsed_ms}

    def check_health(self) -> dict[str, Any]:
        """Generate structured health assessment for the repository."""
        target = self.root if self.root.exists() else Path(".")
        usage = shutil.disk_usage(target)
        free_mb = round(usage.free / (1024 * 1024), 2)

        spec_path = target / "conductor.spec.yaml"
        lock_path = target / LOCK_REL_PATH
        spec_valid = False
        spec_errors: list[str] = []
        if spec_path.exists():
            try:
                spec = load_spec(spec_path)
                spec_errors = validate_spec_schema(spec)
                spec_valid = len(spec_errors) == 0
            except Exception as exc:
                spec_errors = [str(exc)]

        lock_valid = False
        if lock_path.exists():
            try:
                load_lock_manifest(lock_path)
                lock_valid = True
            except Exception:
                lock_valid = False

        ast_info = self.check_ast_engine()
        status = "healthy"
        warnings: list[str] = []

        if not ast_info["passed"]:
            status = "critical"
            warnings.append("Python AST engine self-test failed.")
        elif free_mb < self.min_free_disk_mb:
            status = "degraded"
            warnings.append(f"Low disk space: {free_mb} MB free (< {self.min_free_disk_mb} MB).")
        elif spec_path.exists() and not spec_valid:
            status = "degraded"
            warnings.extend(spec_errors)

        return {
            "status": status,
            "warnings": warnings,
            "spec_present": spec_path.exists(),
            "spec_valid": spec_valid,
            "lock_present": lock_path.exists(),
            "lock_valid": lock_valid,
            "ast_self_test": ast_info,
            "disk_free_mb": free_mb,
            "timestamp": time.time(),
        }

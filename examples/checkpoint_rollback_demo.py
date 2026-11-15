"""Atomic Checkpoint & Rollback Demo for conductor-sdd."""

from __future__ import annotations

import tempfile
from pathlib import Path

from conductor_sdd.core import (
    ConductorSpec,
    SpecInvariants,
    SpecScope,
    build_lock_manifest,
    create_checkpoint,
    rollback_checkpoint,
    verify_drift,
)


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / "src"
        src.mkdir()
        target = src / "auth.py"
        target.write_text(
            "def verify_token(token: str, secret: str) -> bool:\n"
            "    assert len(token) > 0\n"
            "    return token == secret\n",
            encoding="utf-8",
        )

        spec = ConductorSpec(
            project="rollback-demo",
            scope=SpecScope(allowed_paths=["src"]),
            invariants=SpecInvariants(protected_symbols=["verify_token"]),
        )
        manifest = build_lock_manifest(root, spec)
        ckpt = create_checkpoint(root, spec, label="pre-agent")

        # Simulate an agent breaking a locked public signature
        target.write_text("def verify_token(token: str) -> bool:\n    return True\n", encoding="utf-8")
        report = verify_drift(root, spec, manifest)
        print(f"After agent mutation -> passed={report.passed}, violations={len(report.violations)}")

        rollback_checkpoint(root, ckpt.checkpoint_id)
        restored = verify_drift(root, spec, manifest)
        print(f"After rollback -> passed={restored.passed}, drift_score={restored.drift_score}%")


if __name__ == "__main__":
    main()

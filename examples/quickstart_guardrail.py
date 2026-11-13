"""Programmatic quickstart demonstrating Conductor SDD anti-drift verification."""

from __future__ import annotations

import tempfile
from pathlib import Path

from conductor_sdd import (
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
        (root / "src").mkdir()
        auth_file = root / "src" / "auth.py"
        auth_file.write_text(
            "def authenticate(user: str, token: str) -> bool:\n"
            "    return bool(user and token)\n",
            encoding="utf-8",
        )

        spec = ConductorSpec(
            project="demo-service",
            intent="Protect auth signature against accidental agent drift.",
            scope=SpecScope(allowed_paths=["src"]),
            invariants=SpecInvariants(protected_symbols=["authenticate"]),
        )

        baseline = build_lock_manifest(root, spec)
        cp = create_checkpoint(root, spec, label="clean-baseline")
        print(f"Baseline checkpoint created: {cp.checkpoint_id}")

        # Simulate an AI coding agent silently mutating the protected signature
        auth_file.write_text(
            "def authenticate(user: str) -> bool:\n"
            "    return True\n",
            encoding="utf-8",
        )

        report = verify_drift(root, spec, baseline=baseline, strict=True)
        print(report.summary_text())
        assert not report.passed

        restored = rollback_checkpoint(root, checkpoint_id=cp.checkpoint_id)
        print(f"Rolled back files: {restored['restored_files']}")
        assert verify_drift(root, spec, baseline=baseline, strict=True).passed


if __name__ == "__main__":
    main()

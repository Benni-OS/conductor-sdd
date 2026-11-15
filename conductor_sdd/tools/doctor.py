"""Environment diagnostics (`conductor doctor`), agent rules generation, and git hooks."""

from __future__ import annotations

import platform
import sys
from pathlib import Path
from typing import Any

from conductor_sdd.drift_engine import LOCK_REL_PATH, load_lock_manifest
from conductor_sdd.spec import load_spec, validate_spec_schema

PRE_COMMIT_MARKER = "# CONDUCTOR-SDD PRE-COMMIT GUARD"


def run_doctor(root: str | Path = ".") -> dict[str, Any]:
    """Inspect workspace readiness for Conductor SDD enforcement."""
    base = Path(root).resolve()
    spec_path = base / "conductor.spec.yaml"
    lock_path = base / LOCK_REL_PATH
    git_dir = base / ".git"
    hook_path = git_dir / "hooks" / "pre-commit"

    spec_valid = False
    spec_errors: list[str] = []
    if spec_path.exists():
        try:
            spec = load_spec(spec_path)
            spec_errors = validate_spec_schema(spec)
            spec_valid = len(spec_errors) == 0
        except Exception as exc:
            spec_errors = [str(exc)]

    baseline = load_lock_manifest(base) if lock_path.exists() else None
    hook_installed = (
        hook_path.exists() and PRE_COMMIT_MARKER in hook_path.read_text(encoding="utf-8", errors="ignore")
    )

    return {
        "root": str(base),
        "python_version": platform.python_version(),
        "spec_present": spec_path.exists(),
        "spec_valid": spec_valid,
        "spec_errors": spec_errors,
        "lock_present": baseline is not None,
        "locked_modules": len(baseline.modules) if baseline else 0,
        "git_repo": git_dir.exists(),
        "pre_commit_hook_installed": hook_installed,
        "agent_rules_present": (base / "AGENTS.md").exists() or (base / ".cursorrules").exists(),
    }


def render_doctor_report(info: dict[str, Any]) -> str:
    """Format diagnostic checks as a clean terminal summary."""
    def icon(flag: bool) -> str:
        return "OK" if flag else "MISSING"

    lines = [
        "Conductor SDD — Workspace Doctor",
        "=" * 44,
        f"Workspace     : {info['root']}",
        f"Python        : {info['python_version']}",
        f"Spec Contract : [{icon(info['spec_present'])}] conductor.spec.yaml (valid={info['spec_valid']})",
        f"Baseline Lock : [{icon(info['lock_present'])}] .conductor/lock.json ({info['locked_modules']} modules)",
        f"Git Hook      : [{icon(info['pre_commit_hook_installed'])}] .git/hooks/pre-commit",
        f"Agent Rules   : [{icon(info['agent_rules_present'])}] AGENTS.md / .cursorrules",
    ]
    if info["spec_errors"]:
        lines.append("\nSpec validation issues:")
        for err in info["spec_errors"]:
            lines.append(f"  - {err}")
    return "\n".join(lines)


def install_pre_commit_hook(root: str | Path = ".") -> Path:
    """Install a cross-platform git pre-commit hook that executes `conductor verify`."""
    base = Path(root).resolve()
    hooks_dir = base / ".git" / "hooks"
    if not (base / ".git").exists():
        raise FileNotFoundError("Not a git repository (missing `.git` directory).")

    hooks_dir.mkdir(parents=True, exist_ok=True)
    hook_path = hooks_dir / "pre-commit"
    python_exe = Path(sys.executable).as_posix()
    script = (
        "#!/bin/sh\n"
        f"{PRE_COMMIT_MARKER}\n"
        f'"{python_exe}" -m conductor_sdd.cli verify\n'
    )
    hook_path.write_text(script, encoding="utf-8")
    try:
        hook_path.chmod(0o755)
    except OSError:
        pass
    return hook_path


def write_agent_rules_file(root: str | Path = ".", project_name: str = "sovereign-project") -> Path:
    """Generate an `AGENTS.md` contract block instructing AI coding agents to respect Conductor SDD."""
    base = Path(root).resolve()
    target = base / "AGENTS.md"
    snippet = f"""# {project_name} — Spec-Driven Development Contract

Before modifying any source file:
1. Read `conductor.spec.yaml` to confirm `scope.allowed_paths`, `scope.protected_files`, and `invariants.protected_symbols`.
2. Create a clean rollback point: `conductor checkpoint --label "pre-edit"`.
3. Never delete existing test assertions or weaken safety invariants.
4. After edits, run `conductor verify` and fix any SDD-001..SDD-009 drift violations before finishing.
"""
    target.write_text(snippet, encoding="utf-8")
    return target

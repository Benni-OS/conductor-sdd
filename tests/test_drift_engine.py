from __future__ import annotations

from pathlib import Path

from conductor_sdd.drift_engine import (
    build_lock_manifest,
    load_lock_manifest,
    save_lock_manifest,
    verify_drift,
)
from conductor_sdd.spec import ConductorSpec, SpecInvariants, SpecScope


def _setup_repo(tmp_path: Path) -> tuple[Path, ConductorSpec]:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "core.py").write_text(
        '"""Core module."""\n\n\n'
        "def compute(a: int, b: int) -> int:\n"
        '    """Add two ints."""\n'
        "    return a + b\n",
        encoding="utf-8",
    )
    (tmp_path / "src" / "frozen.py").write_text("SECRET_CONST = 42\n", encoding="utf-8")
    (tmp_path / "tests" / "test_core.py").write_text(
        "def test_compute() -> None:\n"
        "    assert 1 + 1 == 2\n"
        "    assert 2 + 2 == 4\n",
        encoding="utf-8",
    )
    spec = ConductorSpec(
        project="test-repo",
        intent="Verify drift engine rules.",
        scope=SpecScope(allowed_paths=["src", "tests"], protected_files=["src/frozen.py"]),
        invariants=SpecInvariants(
            protected_symbols=["compute"],
            forbidden_imports=["pickle"],
            max_cyclomatic_complexity=4,
            forbid_deleted_assertions=True,
            require_docstrings_on_public=True,
        ),
    )
    return tmp_path, spec


def test_clean_workspace_passes_with_zero_drift(tmp_path: Path) -> None:
    root, spec = _setup_repo(tmp_path)
    manifest = build_lock_manifest(root, spec)
    save_lock_manifest(root, manifest)

    loaded = load_lock_manifest(root)
    assert loaded is not None
    report = verify_drift(root, spec, baseline=loaded, strict=True)
    assert report.passed is True
    assert report.drift_score == 0.0
    assert report.violations == []


def test_detects_signature_break_forbidden_import_and_deleted_assertions(tmp_path: Path) -> None:
    root, spec = _setup_repo(tmp_path)
    manifest = build_lock_manifest(root, spec)

    (root / "src" / "core.py").write_text(
        "import pickle\n\ndef compute(a: int) -> int:\n    return a\n",
        encoding="utf-8",
    )
    (root / "tests" / "test_core.py").write_text(
        "def test_compute() -> None:\n    assert True\n",
        encoding="utf-8",
    )
    (root / "src" / "frozen.py").write_text("SECRET_CONST = 99\n", encoding="utf-8")
    (root / "outside").mkdir()
    (root / "outside" / "rogue.py").write_text("x = 1\n", encoding="utf-8")

    report = verify_drift(root, spec, baseline=manifest, strict=True)
    rule_ids = {v.rule_id for v in report.violations}
    assert report.passed is False
    assert {"SDD-002", "SDD-003", "SDD-004", "SDD-005", "SDD-006", "SDD-009"}.issubset(rule_ids)

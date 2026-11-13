from __future__ import annotations

from pathlib import Path

import pytest

from conductor_sdd.checkpoint import create_checkpoint, list_checkpoints, rollback_checkpoint
from conductor_sdd.spec import ConductorSpec, SpecScope


def test_checkpoint_and_atomic_rollback(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    target = tmp_path / "src" / "engine.py"
    original = "def run() -> str:\n    return 'sovereign'\n"
    target.write_text(original, encoding="utf-8")

    spec = ConductorSpec(project="cp-test", scope=SpecScope(allowed_paths=["src"]))
    info = create_checkpoint(tmp_path, spec, label="pre-agent-edit")
    assert info.file_count == 1

    cps = list_checkpoints(tmp_path)
    assert len(cps) == 1
    assert cps[0].checkpoint_id == info.checkpoint_id

    # Corrupt workspace file
    target.write_text("def run() -> str:\n    return 'drifted'\n", encoding="utf-8")

    dry = rollback_checkpoint(tmp_path, dry_run=True)
    assert dry["restored_files"] == ["src/engine.py"]
    assert "drifted" in target.read_text(encoding="utf-8")

    applied = rollback_checkpoint(tmp_path, checkpoint_id=info.checkpoint_id)
    assert applied["restored_files"] == ["src/engine.py"]
    assert target.read_text(encoding="utf-8") == original


def test_rollback_detects_corrupted_checkpoint_hash(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
    spec = ConductorSpec(project="hash-check", scope=SpecScope(allowed_paths=["."]))
    info = create_checkpoint(tmp_path, spec, label="baseline")

    stored_copy = tmp_path / ".conductor" / "checkpoints" / info.checkpoint_id / "files" / "app.py"
    stored_copy.write_text("x = 999\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Checksum mismatch"):
        rollback_checkpoint(tmp_path, checkpoint_id=info.checkpoint_id)

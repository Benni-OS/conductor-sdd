from __future__ import annotations

import json
from pathlib import Path

from conductor_sdd.benchmarks import run_benchmark
from conductor_sdd.cli import main as cli_main
from conductor_sdd.doctor import install_pre_commit_hook


def test_benchmark_matrix_catches_all_failure_modes() -> None:
    res = run_benchmark(iterations=1)
    assert res["scenarios_total"] == 6
    assert res["scenarios_caught"] == 6
    assert res["catch_recall_pct"] == 100.0


def test_cli_full_lifecycle(tmp_path: Path, capsys) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / "src").mkdir()
    app = tmp_path / "src" / "main.py"
    app.write_text("def greet(name: str) -> str:\n    return f'hi {name}'\n", encoding="utf-8")

    assert cli_main(["init", "--root", str(tmp_path), "--project", "cli-test", "--with-agent-rules"]) == 0
    assert (tmp_path / "conductor.spec.yaml").exists()
    assert (tmp_path / "AGENTS.md").exists()

    assert cli_main(["lock", "--root", str(tmp_path), "--json"]) == 0
    capsys.readouterr()

    assert cli_main(["verify", "--root", str(tmp_path), "--json"]) == 0
    verify_out = json.loads(capsys.readouterr().out)
    assert verify_out["passed"] is True

    hook_path = install_pre_commit_hook(tmp_path)
    assert hook_path.exists()

    assert cli_main(["doctor", "--root", str(tmp_path), "--json"]) == 0
    doc_out = json.loads(capsys.readouterr().out)
    assert doc_out["spec_valid"] is True
    assert doc_out["lock_present"] is True
    assert doc_out["pre_commit_hook_installed"] is True

    # Introduce forbidden import and confirm non-zero exit code
    app.write_text("import pickle\n\ndef greet(name: str) -> str:\n    return name\n", encoding="utf-8")
    assert cli_main(["verify", "--root", str(tmp_path)]) == 2

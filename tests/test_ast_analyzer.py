from __future__ import annotations

from pathlib import Path

from conductor_sdd.ast_analyzer import analyze_directory, analyze_file


def test_analyze_file_extracts_symbols_complexity_and_imports(tmp_path: Path) -> None:
    mod = tmp_path / "service.py"
    mod.write_text(
        '"""Service layer."""\n\n'
        "import json\n"
        "from pathlib import Path\n\n"
        "class Engine:\n"
        '    """Main engine."""\n'
        "    async def run(self, x: int, y: bool = True) -> str:\n"
        "        if x > 0 and y:\n"
        '            return "ok"\n'
        '        return "no"\n\n'
        "def test_smoke() -> None:\n"
        "    assert True\n",
        encoding="utf-8",
    )

    snap = analyze_file(mod, root=tmp_path)
    assert snap.syntax_error is None
    assert "json" in snap.imports
    assert "pathlib" in snap.imports
    assert snap.assertion_count == 1
    assert "Engine" in snap.symbols
    assert "Engine.run" in snap.symbols
    run_sym = snap.symbols["Engine.run"]
    assert run_sym.kind == "method"
    assert run_sym.signature == "(self, x: int, y: bool) -> str"
    assert run_sym.complexity >= 3
    assert snap.symbols["test_smoke"].has_docstring is False


def test_analyze_file_captures_syntax_error(tmp_path: Path) -> None:
    bad = tmp_path / "broken.py"
    bad.write_text("def broken(x:\n    return x\n", encoding="utf-8")
    snap = analyze_file(bad, root=tmp_path)
    assert snap.syntax_error is not None
    assert "SyntaxError" in snap.syntax_error


def test_analyze_directory_respects_ignored_paths(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / ".venv").mkdir()
    (tmp_path / "src" / "app.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / ".venv" / "lib.py").write_text("y = 2\n", encoding="utf-8")

    snaps = analyze_directory(tmp_path, ignored_paths=[".venv"])
    assert "src/app.py" in snaps
    assert ".venv/lib.py" not in snaps

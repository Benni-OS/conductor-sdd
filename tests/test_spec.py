from __future__ import annotations

from pathlib import Path

import pytest

from conductor_sdd.spec import (
    ConductorSpec,
    SpecInvariants,
    SpecScope,
    dump_default_spec,
    load_spec,
    validate_spec_schema,
)


def test_default_spec_roundtrip(tmp_path: Path) -> None:
    spec_path = tmp_path / "conductor.spec.yaml"
    spec_path.write_text(
        dump_default_spec("alpha-core", intent="Enforce zero symbol drift.", allowed_paths=["src", "tests"]),
        encoding="utf-8",
    )
    loaded = load_spec(spec_path)
    assert loaded.project == "alpha-core"
    assert loaded.intent == "Enforce zero symbol drift."
    assert loaded.scope.allowed_paths == ["src", "tests"]
    assert "pickle" in loaded.invariants.forbidden_imports
    assert loaded.invariants.max_cyclomatic_complexity == 15
    assert loaded.invariants.forbid_deleted_assertions is True
    assert validate_spec_schema(loaded) == []


def test_json_spec_and_inline_list_yaml(tmp_path: Path) -> None:
    json_spec = tmp_path / "conductor.spec.json"
    json_spec.write_text(
        '{"version":"1.0","project":"json-app","intent":"strict","scope":{"allowed_paths":["app"]}}',
        encoding="utf-8",
    )
    loaded = load_spec(json_spec)
    assert loaded.project == "json-app"
    assert loaded.scope.allowed_paths == ["app"]

    yaml_inline = tmp_path / "inline.yaml"
    yaml_inline.write_text(
        'project: inline-app # comment\n'
        'intent: "Keep tests clean"\n'
        'scope:\n'
        '  allowed_paths: ["src", "lib"]\n'
        '  protected_files: []\n',
        encoding="utf-8",
    )
    loaded_yaml = load_spec(yaml_inline)
    assert loaded_yaml.project == "inline-app"
    assert loaded_yaml.scope.allowed_paths == ["src", "lib"]
    assert loaded_yaml.scope.protected_files == []


def test_validate_spec_schema_catches_invalid() -> None:
    bad = ConductorSpec(
        project="",
        intent="",
        scope=SpecScope(allowed_paths=[]),
        invariants=SpecInvariants(max_cyclomatic_complexity=0, max_file_lines=5),
    )
    errors = validate_spec_schema(bad)
    assert len(errors) == 5


def test_missing_spec_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_spec(tmp_path / "nonexistent.yaml")

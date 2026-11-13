"""Specification schema, zero-dependency YAML/JSON loader, and contract validator."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_IGNORED_PATHS: list[str] = [
    ".git",
    ".conductor",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    ".pytest_cache",
    ".ruff_cache",
]


@dataclass(slots=True)
class SpecScope:
    """Path boundaries and immutability targets for agent edits."""

    allowed_paths: list[str] = field(default_factory=lambda: ["src", "conductor_sdd", "tests"])
    ignored_paths: list[str] = field(default_factory=lambda: list(DEFAULT_IGNORED_PATHS))
    protected_files: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SpecInvariants:
    """Formal AST and engineering invariants enforced across agent turns."""

    protected_symbols: list[str] = field(default_factory=list)
    forbidden_imports: list[str] = field(default_factory=lambda: ["pickle", "marshal"])
    max_cyclomatic_complexity: int = 15
    forbid_deleted_assertions: bool = True
    require_docstrings_on_public: bool = False
    max_file_lines: int = 600


@dataclass(slots=True)
class ConductorSpec:
    """Root specification contract (`conductor.spec.yaml` or `conductor.spec.json`)."""

    version: str = "1.0"
    project: str = "sovereign-project"
    intent: str = "Maintain architectural integrity and zero context drift."
    scope: SpecScope = field(default_factory=SpecScope)
    invariants: SpecInvariants = field(default_factory=SpecInvariants)
    acceptance_commands: list[str] = field(default_factory=lambda: ["pytest -q"])

    def to_dict(self) -> dict[str, Any]:
        """Serialize the contract to a plain dictionary."""
        return asdict(self)


def _coerce_scalar(raw: str) -> Any:
    """Convert a YAML-subset scalar token into a Python primitive."""
    val = raw.strip()
    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
        return val[1:-1]
    lower = val.lower()
    if lower == "true":
        return True
    if lower == "false":
        return False
    if lower in ("null", "~", ""):
        return None
    if re.fullmatch(r"-?\d+", val):
        return int(val)
    if re.fullmatch(r"-?\d+\.\d+", val):
        return float(val)
    if val.startswith("[") and val.endswith("]"):
        inner = val[1:-1].strip()
        if not inner:
            return []
        return [_coerce_scalar(item) for item in inner.split(",")]
    return val


def _strip_inline_comment(line: str) -> str:
    """Strip trailing `#` comments outside quoted strings."""
    in_single = False
    in_double = False
    for idx, ch in enumerate(line):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double:
            if idx == 0 or line[idx - 1].isspace():
                return line[:idx]
    return line


def _tokenize_yaml_lines(text: str) -> list[tuple[int, str]]:
    lines: list[tuple[int, str]] = []
    for raw_line in text.splitlines():
        cleaned = _strip_inline_comment(raw_line).rstrip()
        if not cleaned.strip():
            continue
        indent = len(cleaned) - len(cleaned.lstrip(" "))
        lines.append((indent, cleaned.strip()))
    return lines


def _parse_yaml_list(lines: list[tuple[int, str]], index: int, expected_indent: int) -> tuple[list[Any], int]:
    items: list[Any] = []
    while index < len(lines):
        indent, content = lines[index]
        if indent < expected_indent or not content.startswith("- "):
            break
        items.append(_coerce_scalar(content[2:].strip()))
        index += 1
    return items, index


def _parse_yaml_mapping(lines: list[tuple[int, str]], index: int, expected_indent: int) -> tuple[dict[str, Any], int]:
    mapping: dict[str, Any] = {}
    while index < len(lines):
        indent, content = lines[index]
        if indent < expected_indent:
            break
        if indent > expected_indent:
            raise ValueError(f"Unexpected indentation near line: {content}")
        if ":" not in content:
            raise ValueError(f"Expected key: value near line: {content}")

        key, rest = content.split(":", 1)
        key = str(_coerce_scalar(key.strip()))
        rest = rest.strip()
        index += 1

        if rest:
            mapping[key] = _coerce_scalar(rest)
        elif index < len(lines) and lines[index][0] > indent:
            nested, index = _parse_yaml_block(lines, index, lines[index][0])
            mapping[key] = nested
        else:
            mapping[key] = {}
    return mapping, index


def _parse_yaml_block(lines: list[tuple[int, str]], index: int, expected_indent: int) -> tuple[Any, int]:
    if index >= len(lines):
        return {}, index
    if lines[index][1].startswith("- "):
        return _parse_yaml_list(lines, index, expected_indent)
    return _parse_yaml_mapping(lines, index, expected_indent)


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    """Parse a clean indentation-based YAML subset without external dependencies."""
    lines = _tokenize_yaml_lines(text)
    parsed, _ = _parse_yaml_block(lines, 0, 0)
    if not isinstance(parsed, dict):
        raise ValueError("Specification root must be a key/value mapping.")
    return parsed


def load_spec(path: str | Path) -> ConductorSpec:
    """Load a `ConductorSpec` from a `.yaml`, `.yml`, or `.json` contract file."""
    spec_path = Path(path)
    if not spec_path.exists():
        raise FileNotFoundError(f"Specification file not found: {spec_path}")

    raw_text = spec_path.read_text(encoding="utf-8")
    if spec_path.suffix.lower() == ".json":
        data = json.loads(raw_text)
    else:
        try:
            import yaml  # type: ignore[import-untyped]

            data = yaml.safe_load(raw_text) or {}
        except ImportError:
            data = _parse_simple_yaml(raw_text)

    if not isinstance(data, dict):
        raise ValueError("Conductor spec must deserialize to a mapping.")

    scope_raw = data.get("scope") or {}
    invariants_raw = data.get("invariants") or {}

    scope = SpecScope(
        allowed_paths=[str(p) for p in scope_raw.get("allowed_paths", ["."])],
        ignored_paths=[str(p) for p in scope_raw.get("ignored_paths", DEFAULT_IGNORED_PATHS)],
        protected_files=[str(p) for p in scope_raw.get("protected_files", [])],
    )
    invariants = SpecInvariants(
        protected_symbols=[str(s) for s in invariants_raw.get("protected_symbols", [])],
        forbidden_imports=[str(m) for m in invariants_raw.get("forbidden_imports", [])],
        max_cyclomatic_complexity=int(invariants_raw.get("max_cyclomatic_complexity", 15)),
        forbid_deleted_assertions=bool(invariants_raw.get("forbid_deleted_assertions", True)),
        require_docstrings_on_public=bool(invariants_raw.get("require_docstrings_on_public", False)),
        max_file_lines=int(invariants_raw.get("max_file_lines", 600)),
    )

    return ConductorSpec(
        version=str(data.get("version", "1.0")),
        project=str(data.get("project", spec_path.parent.name or "sovereign-project")),
        intent=str(data.get("intent", "Maintain zero-drift architecture.")),
        scope=scope,
        invariants=invariants,
        acceptance_commands=[str(c) for c in data.get("acceptance_commands", ["pytest -q"])],
    )


def validate_spec_schema(spec: ConductorSpec) -> list[str]:
    """Return a list of schema validation errors (empty if valid)."""
    errors: list[str] = []
    if not spec.project.strip():
        errors.append("`project` must be a non-empty string.")
    if not spec.intent.strip():
        errors.append("`intent` must clearly state the architectural objective.")
    if spec.invariants.max_cyclomatic_complexity < 1:
        errors.append("`invariants.max_cyclomatic_complexity` must be >= 1.")
    if spec.invariants.max_file_lines < 10:
        errors.append("`invariants.max_file_lines` must be >= 10.")
    if not spec.scope.allowed_paths:
        errors.append("`scope.allowed_paths` must specify at least one target path (e.g. `.` or `src`).")
    return errors


def _yaml_list(items: list[str], indent: int = 4) -> str:
    prefix = " " * indent
    if not items:
        return f"{prefix}[]"
    return "\n".join(f'{prefix}- "{item}"' for item in items)


def dump_default_spec(project_name: str, intent: str | None = None, allowed_paths: list[str] | None = None) -> str:
    """Render a clean default `conductor.spec.yaml` contract."""
    resolved_intent = intent or "Deliver changes strictly inside approved scope with zero symbol drift."
    resolved_paths = allowed_paths or ["."]
    ignored_block = _yaml_list(DEFAULT_IGNORED_PATHS, indent=4)
    allowed_block = "\n".join(f'    - "{p}"' for p in resolved_paths)
    return f"""# Conductor SDD — Architectural Specification Contract
version: "1.0"
project: "{project_name}"
intent: "{resolved_intent}"

scope:
  allowed_paths:
{allowed_block}
  ignored_paths:
{ignored_block}
  protected_files: []

invariants:
  protected_symbols: []
  forbidden_imports:
    - "pickle"
    - "marshal"
  max_cyclomatic_complexity: 15
  forbid_deleted_assertions: true
  require_docstrings_on_public: false
  max_file_lines: 600

acceptance_commands:
  - "pytest -q"
"""

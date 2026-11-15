"""Zero-dependency static AST analyzer for deterministic symbol and complexity extraction."""

from __future__ import annotations

import ast
import hashlib
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class SymbolInfo:
    """Deterministic fingerprint of a function, async function, or class."""

    qualname: str
    kind: str  # "function" | "async_function" | "method" | "class"
    signature: str
    lineno: int
    end_lineno: int
    complexity: int
    has_docstring: bool
    body_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ModuleSnapshot:
    """Snapshot of a source module extracted statically without code execution."""

    rel_path: str
    file_sha256: str
    line_count: int
    imports: list[str] = field(default_factory=list)
    assertion_count: int = 0
    syntax_error: str | None = None
    symbols: dict[str, SymbolInfo] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["symbols"] = {k: v.to_dict() for k, v in self.symbols.items()}
        return data

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> ModuleSnapshot:
        symbols = {
            k: SymbolInfo(**v) for k, v in (raw.get("symbols") or {}).items()
        }
        return cls(
            rel_path=str(raw["rel_path"]),
            file_sha256=str(raw["file_sha256"]),
            line_count=int(raw.get("line_count", 0)),
            imports=[str(i) for i in raw.get("imports", [])],
            assertion_count=int(raw.get("assertion_count", 0)),
            syntax_error=raw.get("syntax_error"),
            symbols=symbols,
        )


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _normalized_rel_path(root: Path, file_path: Path) -> str:
    return file_path.resolve().relative_to(root.resolve()).as_posix()


def _compute_complexity(node: ast.AST) -> int:
    """Compute McCabe cyclomatic complexity for a function or method node."""
    complexity = 1
    branch_nodes = (
        ast.If,
        ast.For,
        ast.AsyncFor,
        ast.While,
        ast.ExceptHandler,
        ast.With,
        ast.AsyncWith,
        ast.IfExp,
        ast.comprehension,
    )
    for child in ast.walk(node):
        if isinstance(child, branch_nodes):
            complexity += 1
        elif isinstance(child, ast.BoolOp):
            complexity += max(0, len(child.values) - 1)
    return complexity


def _format_arg(arg: ast.arg) -> str:
    if arg.annotation is not None:
        return f"{arg.arg}: {ast.unparse(arg.annotation)}"
    return arg.arg


def _format_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """Build a normalized signature string insensitive to whitespace formatting."""
    parts: list[str] = []
    args = node.args

    for pos in args.posonlyargs:
        parts.append(_format_arg(pos))
    if args.posonlyargs:
        parts.append("/")

    for regular in args.args:
        parts.append(_format_arg(regular))

    if args.vararg:
        parts.append(f"*{_format_arg(args.vararg)}")
    elif args.kwonlyargs:
        parts.append("*")

    for kw in args.kwonlyargs:
        parts.append(_format_arg(kw))

    if args.kwarg:
        parts.append(f"**{_format_arg(args.kwarg)}")

    ret = f" -> {ast.unparse(node.returns)}" if node.returns is not None else ""
    return f"({', '.join(parts)}){ret}"


def _ast_body_hash(node: ast.AST) -> str:
    """Hash canonical AST structure excluding docstring and formatting trivia."""
    dumped = ast.dump(node, annotate_fields=True, include_attributes=False)
    return hashlib.sha256(dumped.encode("utf-8")).hexdigest()


def _extract_imports(tree: ast.Module) -> list[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name.split(".")[0])
                found.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module.split(".")[0])
            found.add(node.module)
    return sorted(found)


def _count_assertions(tree: ast.Module) -> int:
    """Count `assert` statements and `self.assert*` / `pytest.raises` checks."""
    count = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Assert):
            count += 1
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            attr = node.func.attr
            if attr.startswith("assert") or attr in {"raises", "warns"}:
                count += 1
    return count


def _collect_symbols(tree: ast.Module) -> dict[str, SymbolInfo]:
    """Collect top-level functions, classes, and class methods."""
    symbols: dict[str, SymbolInfo] = {}

    def record_fn(
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        qualname: str,
        kind: str,
    ) -> None:
        symbols[qualname] = SymbolInfo(
            qualname=qualname,
            kind=kind,
            signature=_format_signature(node),
            lineno=node.lineno,
            end_lineno=getattr(node, "end_lineno", node.lineno),
            complexity=_compute_complexity(node),
            has_docstring=ast.get_docstring(node) is not None,
            body_sha256=_ast_body_hash(node),
        )

    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            record_fn(node, node.name, "function")
        elif isinstance(node, ast.AsyncFunctionDef):
            record_fn(node, node.name, "async_function")
        elif isinstance(node, ast.ClassDef):
            bases = ", ".join(ast.unparse(b) for b in node.bases)
            symbols[node.name] = SymbolInfo(
                qualname=node.name,
                kind="class",
                signature=f"class {node.name}({bases})" if bases else f"class {node.name}",
                lineno=node.lineno,
                end_lineno=getattr(node, "end_lineno", node.lineno),
                complexity=1,
                has_docstring=ast.get_docstring(node) is not None,
                body_sha256=_ast_body_hash(node),
            )
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    record_fn(child, f"{node.name}.{child.name}", "method")

    return symbols


def analyze_file(file_path: str | Path, root: str | Path | None = None) -> ModuleSnapshot:
    """Analyze a single Python module statically and return its deterministic snapshot."""
    target = Path(file_path).resolve()
    base = Path(root).resolve() if root is not None else target.parent
    rel_path = _normalized_rel_path(base, target)

    raw_bytes = target.read_bytes()
    file_hash = _sha256_bytes(raw_bytes)
    text = raw_bytes.decode("utf-8", errors="replace")
    line_count = len(text.splitlines())

    if target.suffix.lower() != ".py":
        return ModuleSnapshot(
            rel_path=rel_path,
            file_sha256=file_hash,
            line_count=line_count,
        )

    try:
        tree = ast.parse(text, filename=rel_path)
    except SyntaxError as exc:
        return ModuleSnapshot(
            rel_path=rel_path,
            file_sha256=file_hash,
            line_count=line_count,
            syntax_error=f"SyntaxError at line {exc.lineno}: {exc.msg}",
        )

    return ModuleSnapshot(
        rel_path=rel_path,
        file_sha256=file_hash,
        line_count=line_count,
        imports=_extract_imports(tree),
        assertion_count=_count_assertions(tree),
        syntax_error=None,
        symbols=_collect_symbols(tree),
    )


def _should_ignore(rel_parts: tuple[str, ...], ignored_paths: Iterable[str]) -> bool:
    ignored_set = {p.strip("/\\") for p in ignored_paths if p}
    return any(part in ignored_set for part in rel_parts)


def analyze_directory(
    root: str | Path,
    ignored_paths: Iterable[str] = (),
    extensions: tuple[str, ...] = (".py",),
    extra_files: Iterable[str] = (),
) -> dict[str, ModuleSnapshot]:
    """Scan a repository directory and return snapshots keyed by normalized POSIX rel_path."""
    base = Path(root).resolve()
    snapshots: dict[str, ModuleSnapshot] = {}

    for path in sorted(base.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(base)
        if _should_ignore(rel.parts, ignored_paths):
            continue
        rel_posix = rel.as_posix()
        if path.suffix.lower() in extensions or rel_posix in set(extra_files):
            snapshots[rel_posix] = analyze_file(path, root=base)

    return snapshots

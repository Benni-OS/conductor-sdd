"""Deterministic AST drift detector and baseline lock manifest engine."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from conductor_sdd.ast_analyzer import ModuleSnapshot, SymbolInfo, analyze_directory
from conductor_sdd.spec import ConductorSpec

LOCK_REL_PATH = Path(".conductor/lock.json")


@dataclass(slots=True)
class DriftViolation:
    """Single specification or baseline invariant violation."""

    rule_id: str
    severity: str  # "CRITICAL" | "ERROR" | "WARNING"
    file_path: str
    symbol: str | None
    message: str
    remediation: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class LockManifest:
    """Cryptographically hashed baseline snapshot of an approved workspace state."""

    version: str
    project: str
    spec_sha256: str
    created_at: float
    root_sha256: str
    modules: dict[str, ModuleSnapshot] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "project": self.project,
            "spec_sha256": self.spec_sha256,
            "created_at": self.created_at,
            "root_sha256": self.root_sha256,
            "modules": {k: v.to_dict() for k, v in sorted(self.modules.items())},
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> LockManifest:
        modules = {
            k: ModuleSnapshot.from_dict(v)
            for k, v in (raw.get("modules") or {}).items()
        }
        return cls(
            version=str(raw.get("version", "1.0")),
            project=str(raw.get("project", "")),
            spec_sha256=str(raw.get("spec_sha256", "")),
            created_at=float(raw.get("created_at", 0.0)),
            root_sha256=str(raw.get("root_sha256", "")),
            modules=modules,
        )


@dataclass(slots=True)
class DriftReport:
    """Structured result of a Conductor SDD verification pass."""

    passed: bool
    drift_score: float
    checked_files: int
    locked_files: int
    elapsed_ms: float
    violations: list[DriftViolation] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "drift_score": round(self.drift_score, 2),
            "checked_files": self.checked_files,
            "locked_files": self.locked_files,
            "elapsed_ms": round(self.elapsed_ms, 2),
            "violation_counts": {
                "CRITICAL": sum(1 for v in self.violations if v.severity == "CRITICAL"),
                "ERROR": sum(1 for v in self.violations if v.severity == "ERROR"),
                "WARNING": sum(1 for v in self.violations if v.severity == "WARNING"),
            },
            "violations": [v.to_dict() for v in self.violations],
        }

    def summary_text(self) -> str:
        status = "PASS (0.00% DRIFT)" if self.passed else f"DRIFT DETECTED ({self.drift_score:.2f}%)"
        lines = [
            f"Conductor SDD Verification: {status}",
            f"Files scanned: {self.checked_files} | Baseline locked: {self.locked_files} | Elapsed: {self.elapsed_ms:.2f}ms",
        ]
        if not self.violations:
            lines.append("All architectural contracts, symbol signatures, and invariants hold.")
            return "\n".join(lines)

        lines.append("")
        for v in self.violations:
            loc = f"{v.file_path}::{v.symbol}" if v.symbol else v.file_path
            lines.append(f"[{v.severity}] {v.rule_id} ({loc}): {v.message}")
            lines.append(f"   -> Fix: {v.remediation}")
        return "\n".join(lines)


def _compute_spec_hash(spec: ConductorSpec) -> str:
    payload = json.dumps(spec.to_dict(), sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _compute_root_hash(modules: dict[str, ModuleSnapshot]) -> str:
    hasher = hashlib.sha256()
    for rel_path in sorted(modules):
        snap = modules[rel_path]
        hasher.update(f"{rel_path}:{snap.file_sha256}\n".encode())
    return hasher.hexdigest()


def _is_path_allowed(rel_path: str, allowed_paths: list[str]) -> bool:
    norm_allowed = [p.strip("./\\").replace("\\", "/") for p in allowed_paths]
    if "." in allowed_paths or "" in norm_allowed or "*" in norm_allowed:
        return True
    return any(
        rel_path == prefix or rel_path.startswith(f"{prefix}/")
        for prefix in norm_allowed
        if prefix
    )


def _flatten_symbols(modules: dict[str, ModuleSnapshot]) -> dict[str, tuple[str, SymbolInfo]]:
    flat: dict[str, tuple[str, SymbolInfo]] = {}
    for rel_path, snap in modules.items():
        for qualname, sym in snap.symbols.items():
            flat[f"{rel_path}::{qualname}"] = (rel_path, sym)
            flat.setdefault(qualname, (rel_path, sym))
    return flat


def build_lock_manifest(root: str | Path, spec: ConductorSpec) -> LockManifest:
    """Scan workspace under `root` and construct a baseline `LockManifest`."""
    snapshots = analyze_directory(
        root=root,
        ignored_paths=spec.scope.ignored_paths,
        extra_files=spec.scope.protected_files,
    )
    return LockManifest(
        version=spec.version,
        project=spec.project,
        spec_sha256=_compute_spec_hash(spec),
        created_at=time.time(),
        root_sha256=_compute_root_hash(snapshots),
        modules=snapshots,
    )


def save_lock_manifest(root: str | Path, manifest: LockManifest) -> Path:
    """Persist `LockManifest` atomically to `.conductor/lock.json`."""
    lock_path = Path(root).resolve() / LOCK_REL_PATH
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(json.dumps(manifest.to_dict(), indent=2), encoding="utf-8")
    return lock_path


def load_lock_manifest(root: str | Path) -> LockManifest | None:
    """Load `.conductor/lock.json` if present, otherwise return None."""
    lock_path = Path(root).resolve() / LOCK_REL_PATH
    if not lock_path.exists():
        return None
    raw = json.loads(lock_path.read_text(encoding="utf-8"))
    return LockManifest.from_dict(raw)


def _check_static_invariants(
    rel_path: str,
    snap: ModuleSnapshot,
    spec: ConductorSpec,
    strict: bool,
) -> list[DriftViolation]:
    violations: list[DriftViolation] = []
    inv = spec.invariants

    if snap.syntax_error:
        violations.append(
            DriftViolation(
                rule_id="SDD-001",
                severity="CRITICAL",
                file_path=rel_path,
                symbol=None,
                message=f"Broken syntax introduced: {snap.syntax_error}",
                remediation="Fix syntax error immediately or run `conductor rollback`.",
            )
        )
        return violations

    forbidden_set = set(inv.forbidden_imports)
    for imp in snap.imports:
        if imp in forbidden_set:
            violations.append(
                DriftViolation(
                    rule_id="SDD-005",
                    severity="ERROR",
                    file_path=rel_path,
                    symbol=None,
                    message=f"Forbidden import `{imp}` detected.",
                    remediation=f"Remove `{imp}` or update `invariants.forbidden_imports` in spec.",
                )
            )

    if snap.line_count > inv.max_file_lines:
        violations.append(
            DriftViolation(
                rule_id="SDD-008",
                severity="ERROR" if strict else "WARNING",
                file_path=rel_path,
                symbol=None,
                message=f"Module has {snap.line_count} lines (ceiling: {inv.max_file_lines}).",
                remediation="Split oversized module into cohesive single-purpose submodules.",
            )
        )

    for qualname, sym in snap.symbols.items():
        if sym.complexity > inv.max_cyclomatic_complexity:
            violations.append(
                DriftViolation(
                    rule_id="SDD-007",
                    severity="ERROR" if strict else "WARNING",
                    file_path=rel_path,
                    symbol=qualname,
                    message=f"Cyclomatic complexity {sym.complexity} exceeds ceiling {inv.max_cyclomatic_complexity}.",
                    remediation="Decompose nested branches into small early-return helpers.",
                )
            )
        leaf_name = qualname.split(".")[-1]
        is_public = not leaf_name.startswith("_")
        is_test_symbol = leaf_name.startswith("test_") or Path(rel_path).name.startswith("test_")
        if inv.require_docstrings_on_public and is_public and not is_test_symbol and not sym.has_docstring:
            violations.append(
                DriftViolation(
                    rule_id="SDD-009",
                    severity="ERROR" if strict else "WARNING",
                    file_path=rel_path,
                    symbol=qualname,
                    message=f"Public symbol `{qualname}` is missing a docstring.",
                    remediation="Add a concise docstring describing purpose and inputs.",
                )
            )

    return violations


def _check_protected_files(
    current: dict[str, ModuleSnapshot],
    baseline: LockManifest,
    protected_files: set[str],
) -> list[DriftViolation]:
    violations: list[DriftViolation] = []
    for pfile in sorted(protected_files):
        old_mod = baseline.modules.get(pfile)
        new_mod = current.get(pfile)
        if old_mod and (not new_mod or new_mod.file_sha256 != old_mod.file_sha256):
            violations.append(
                DriftViolation(
                    rule_id="SDD-002",
                    severity="CRITICAL",
                    file_path=pfile,
                    symbol=None,
                    message=f"Protected file `{pfile}` was modified or deleted.",
                    remediation=f"Restore `{pfile}` from checkpoint or remove from `scope.protected_files`.",
                )
            )
    return violations


def _check_protected_symbols(
    current: dict[str, ModuleSnapshot],
    baseline: LockManifest,
    protected_symbols: list[str],
) -> list[DriftViolation]:
    violations: list[DriftViolation] = []
    locked_flat = _flatten_symbols(baseline.modules)
    current_flat = _flatten_symbols(current)

    for psym in protected_symbols:
        locked_entry = locked_flat.get(psym)
        curr_entry = current_flat.get(psym)
        if locked_entry and not curr_entry:
            violations.append(
                DriftViolation(
                    rule_id="SDD-003",
                    severity="CRITICAL",
                    file_path=locked_entry[0],
                    symbol=psym,
                    message=f"Protected symbol `{psym}` was deleted or renamed.",
                    remediation=f"Restore protected symbol `{psym}`.",
                )
            )
        elif locked_entry and curr_entry and locked_entry[1].signature != curr_entry[1].signature:
            violations.append(
                DriftViolation(
                    rule_id="SDD-003",
                    severity="CRITICAL",
                    file_path=curr_entry[0],
                    symbol=psym,
                    message=(
                        f"Protected symbol signature mutated from `{locked_entry[1].signature}` "
                        f"to `{curr_entry[1].signature}`."
                    ),
                    remediation="Preserve the locked public signature to avoid downstream breakage.",
                )
            )
    return violations


def _check_scope_and_assertions(
    current: dict[str, ModuleSnapshot],
    baseline: LockManifest,
    spec: ConductorSpec,
) -> list[DriftViolation]:
    violations: list[DriftViolation] = []
    for rel_path, old_mod in baseline.modules.items():
        new_mod = current.get(rel_path)
        changed = new_mod is None or new_mod.file_sha256 != old_mod.file_sha256
        if changed and not _is_path_allowed(rel_path, spec.scope.allowed_paths):
            violations.append(
                DriftViolation(
                    rule_id="SDD-004",
                    severity="ERROR",
                    file_path=rel_path,
                    symbol=None,
                    message=f"Out-of-scope mutation outside allowed_paths {spec.scope.allowed_paths}.",
                    remediation="Revert out-of-scope edits or expand `scope.allowed_paths` in spec.",
                )
            )
        if (
            spec.invariants.forbid_deleted_assertions
            and new_mod is not None
            and new_mod.assertion_count < old_mod.assertion_count
        ):
            violations.append(
                DriftViolation(
                    rule_id="SDD-006",
                    severity="ERROR",
                    file_path=rel_path,
                    symbol=None,
                    message=(
                        f"Assertion count dropped from {old_mod.assertion_count} to "
                        f"{new_mod.assertion_count} (possible test/guard deletion)."
                    ),
                    remediation="Restore deleted assertions; never weaken tests to satisfy a build.",
                )
            )

    for rel_path in current:
        if rel_path not in baseline.modules and not _is_path_allowed(rel_path, spec.scope.allowed_paths):
            violations.append(
                DriftViolation(
                    rule_id="SDD-004",
                    severity="ERROR",
                    file_path=rel_path,
                    symbol=None,
                    message=f"New untracked file `{rel_path}` created outside allowed_paths.",
                    remediation="Move file inside `allowed_paths` or remove stray artifact.",
                )
            )
    return violations


def _check_baseline_drift(
    current: dict[str, ModuleSnapshot],
    baseline: LockManifest,
    spec: ConductorSpec,
) -> list[DriftViolation]:
    protected_files = {p.replace("\\", "/") for p in spec.scope.protected_files}
    return [
        *_check_protected_files(current, baseline, protected_files),
        *_check_protected_symbols(current, baseline, spec.invariants.protected_symbols),
        *_check_scope_and_assertions(current, baseline, spec),
    ]


def verify_drift(
    root: str | Path,
    spec: ConductorSpec,
    baseline: LockManifest | None = None,
    strict: bool = False,
) -> DriftReport:
    """Verify workspace against `ConductorSpec` and optional `LockManifest`."""
    start = time.perf_counter()
    current = analyze_directory(
        root=root,
        ignored_paths=spec.scope.ignored_paths,
        extra_files=spec.scope.protected_files,
    )

    violations: list[DriftViolation] = []
    for rel_path, snap in current.items():
        violations.extend(_check_static_invariants(rel_path, snap, spec, strict=strict))

    if baseline is not None:
        violations.extend(_check_baseline_drift(current, baseline, spec))

    blocking_severities = {"CRITICAL", "ERROR"}
    blocking = [v for v in violations if v.severity in blocking_severities]
    total_units = max(1, len(current))
    raw_score = min(100.0, (len(blocking) / total_units) * 25.0 + len(violations) * 2.5)
    drift_score = 0.0 if not violations else max(1.0, raw_score)
    elapsed_ms = (time.perf_counter() - start) * 1000.0

    return DriftReport(
        passed=len(blocking) == 0,
        drift_score=drift_score,
        checked_files=len(current),
        locked_files=len(baseline.modules) if baseline else 0,
        elapsed_ms=elapsed_ms,
        violations=violations,
    )

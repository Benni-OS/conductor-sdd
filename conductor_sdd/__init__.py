"""Conductor SDD — Deterministic Spec-Driven Development & Anti-Drift Harness."""

from conductor_sdd.ast_analyzer import ModuleSnapshot, SymbolInfo, analyze_directory, analyze_file
from conductor_sdd.checkpoint import (
    CheckpointInfo,
    create_checkpoint,
    list_checkpoints,
    rollback_checkpoint,
)
from conductor_sdd.drift_engine import (
    DriftReport,
    DriftViolation,
    LockManifest,
    build_lock_manifest,
    load_lock_manifest,
    save_lock_manifest,
    verify_drift,
)
from conductor_sdd.spec import (
    ConductorSpec,
    SpecInvariants,
    SpecScope,
    dump_default_spec,
    load_spec,
    validate_spec_schema,
)

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "CheckpointInfo",
    "ConductorSpec",
    "DriftReport",
    "DriftViolation",
    "LockManifest",
    "ModuleSnapshot",
    "SpecInvariants",
    "SpecScope",
    "SymbolInfo",
    "analyze_directory",
    "analyze_file",
    "build_lock_manifest",
    "create_checkpoint",
    "dump_default_spec",
    "list_checkpoints",
    "load_lock_manifest",
    "load_spec",
    "rollback_checkpoint",
    "save_lock_manifest",
    "validate_spec_schema",
    "verify_drift",
]

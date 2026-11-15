"""Conductor SDD — Deterministic Spec-Driven Development & Anti-Drift Harness."""

from conductor_sdd.core import (
    CheckpointInfo,
    ConductorSpec,
    DriftReport,
    DriftViolation,
    LockManifest,
    ModuleSnapshot,
    SpecInvariants,
    SpecScope,
    SymbolInfo,
    analyze_directory,
    analyze_file,
    build_lock_manifest,
    create_checkpoint,
    dump_default_spec,
    list_checkpoints,
    load_lock_manifest,
    load_spec,
    rollback_checkpoint,
    save_lock_manifest,
    validate_spec_schema,
    verify_drift,
)
from conductor_sdd.serve import ConductorHealthMonitor, ConductorTelemetryEngine
from conductor_sdd.tools import ConductorBenchMatrixRunner, run_benchmark, run_doctor

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "CheckpointInfo",
    "ConductorBenchMatrixRunner",
    "ConductorHealthMonitor",
    "ConductorSpec",
    "ConductorTelemetryEngine",
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
    "run_benchmark",
    "run_doctor",
    "save_lock_manifest",
    "validate_spec_schema",
    "verify_drift",
]

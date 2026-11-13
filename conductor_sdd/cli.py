"""Unified CLI for Conductor SDD (`conductor`, `conductor-sdd`)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from conductor_sdd import __version__
from conductor_sdd.benchmarks import render_benchmark_report, run_benchmark
from conductor_sdd.checkpoint import create_checkpoint, list_checkpoints, rollback_checkpoint
from conductor_sdd.doctor import (
    install_pre_commit_hook,
    render_doctor_report,
    run_doctor,
    write_agent_rules_file,
)
from conductor_sdd.drift_engine import (
    build_lock_manifest,
    load_lock_manifest,
    save_lock_manifest,
    verify_drift,
)
from conductor_sdd.mcp_server import serve_stdio
from conductor_sdd.spec import dump_default_spec, load_spec, validate_spec_schema


def _spec_path(root: Path, override: str | None) -> Path:
    if override:
        p = Path(override)
        return p if p.is_absolute() else root / p
    return root / "conductor.spec.yaml"


def _cmd_init(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    spec_file = _spec_path(root, args.spec)
    if spec_file.exists() and not args.force:
        print(f"Spec already exists at {spec_file}. Pass --force to overwrite.", file=sys.stderr)
        return 1

    project_name = args.project or root.name or "sovereign-project"
    allowed = args.allowed or ["."]
    spec_file.write_text(
        dump_default_spec(project_name=project_name, intent=args.intent, allowed_paths=allowed),
        encoding="utf-8",
    )
    print(f"Initialized spec contract: {spec_file}")

    if args.with_agent_rules:
        rules_file = write_agent_rules_file(root, project_name=project_name)
        print(f"Created AI agent contract: {rules_file}")
    return 0


def _cmd_lock(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    spec = load_spec(_spec_path(root, args.spec))
    errors = validate_spec_schema(spec)
    if errors:
        print("Invalid spec schema:\n  - " + "\n  - ".join(errors), file=sys.stderr)
        return 1

    manifest = build_lock_manifest(root, spec)
    lock_file = save_lock_manifest(root, manifest)
    if args.json:
        print(json.dumps({"lock_file": str(lock_file), "modules": len(manifest.modules), "root_sha256": manifest.root_sha256}, indent=2))
    else:
        print(f"Locked {len(manifest.modules)} modules -> {lock_file}")
        print(f"Root SHA-256: {manifest.root_sha256}")
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    spec = load_spec(_spec_path(root, args.spec))
    baseline = load_lock_manifest(root)
    report = verify_drift(root, spec, baseline=baseline, strict=args.strict)

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(report.summary_text())
    return 0 if report.passed else 2


def _cmd_checkpoint(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    if args.list:
        cps = list_checkpoints(root)
        if args.json:
            print(json.dumps([c.to_dict() for c in cps], indent=2))
        elif not cps:
            print("No checkpoints recorded yet.")
        else:
            for c in cps:
                print(f"{c.checkpoint_id} | {c.label} | {c.file_count} files | sha256={c.root_sha256[:12]}")
        return 0

    spec = load_spec(_spec_path(root, args.spec))
    info = create_checkpoint(root, spec, label=args.label)
    if args.json:
        print(json.dumps(info.to_dict(), indent=2))
    else:
        print(f"Checkpoint created: {info.checkpoint_id} ({info.file_count} files, root={info.root_sha256[:12]})")
    return 0


def _cmd_rollback(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    result = rollback_checkpoint(root, checkpoint_id=args.id, dry_run=args.dry_run)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        mode = "DRY-RUN" if result["dry_run"] else "RESTORED"
        print(
            f"[{mode}] Checkpoint {result['checkpoint_id']} | "
            f"Verified {result['verified_files']} files | "
            f"Restored {len(result['restored_files'])} files"
        )
        for f in result["restored_files"]:
            print(f"  - {f}")
    return 0


def _cmd_bench(args: argparse.Namespace) -> int:
    result = run_benchmark(iterations=args.iterations)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(render_benchmark_report(result))
    return 0


def _cmd_doctor(args: argparse.Namespace) -> int:
    info = run_doctor(args.root)
    if args.json:
        print(json.dumps(info, indent=2))
    else:
        print(render_doctor_report(info))
    return 0


def _cmd_install_hook(args: argparse.Namespace) -> int:
    hook_path = install_pre_commit_hook(args.root)
    print(f"Installed pre-commit guard at: {hook_path}")
    return 0


def _cmd_mcp(_: argparse.Namespace) -> int:
    serve_stdio()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="conductor",
        description="Conductor SDD — Deterministic Spec-Driven Development & AST Anti-Drift Guardrail",
    )
    parser.add_argument("--version", action="version", version=f"conductor-sdd {__version__}")

    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Initialize conductor.spec.yaml in a repository.")
    p_init.add_argument("--root", default=".")
    p_init.add_argument("--spec", default=None)
    p_init.add_argument("--project", default=None)
    p_init.add_argument("--intent", default=None)
    p_init.add_argument("--allowed", nargs="*", default=None)
    p_init.add_argument("--with-agent-rules", action="store_true")
    p_init.add_argument("--force", action="store_true")
    p_init.set_defaults(func=_cmd_init)

    p_lock = sub.add_parser("lock", help="Lock AST symbol signatures and SHA-256 baseline.")
    p_lock.add_argument("--root", default=".")
    p_lock.add_argument("--spec", default=None)
    p_lock.add_argument("--json", action="store_true")
    p_lock.set_defaults(func=_cmd_lock)

    p_verify = sub.add_parser("verify", help="Verify workspace for AST or scope drift.")
    p_verify.add_argument("--root", default=".")
    p_verify.add_argument("--spec", default=None)
    p_verify.add_argument("--strict", action="store_true")
    p_verify.add_argument("--json", action="store_true")
    p_verify.set_defaults(func=_cmd_verify)

    p_cp = sub.add_parser("checkpoint", help="Create or list SHA-256 workspace checkpoints.")
    p_cp.add_argument("--root", default=".")
    p_cp.add_argument("--spec", default=None)
    p_cp.add_argument("--label", default="manual-checkpoint")
    p_cp.add_argument("--list", action="store_true")
    p_cp.add_argument("--json", action="store_true")
    p_cp.set_defaults(func=_cmd_checkpoint)

    p_rb = sub.add_parser("rollback", help="Roll back workspace files to a verified checkpoint.")
    p_rb.add_argument("--root", default=".")
    p_rb.add_argument("--id", default=None)
    p_rb.add_argument("--dry-run", action="store_true")
    p_rb.add_argument("--json", action="store_true")
    p_rb.set_defaults(func=_cmd_rollback)

    p_bench = sub.add_parser("bench", help="Run reproducible agent-drift benchmark matrix.")
    p_bench.add_argument("--iterations", type=int, default=1)
    p_bench.add_argument("--json", action="store_true")
    p_bench.set_defaults(func=_cmd_bench)

    p_doc = sub.add_parser("doctor", help="Inspect repository readiness for SDD governance.")
    p_doc.add_argument("--root", default=".")
    p_doc.add_argument("--json", action="store_true")
    p_doc.set_defaults(func=_cmd_doctor)

    p_hook = sub.add_parser("install-hook", help="Install git pre-commit AST drift check.")
    p_hook.add_argument("--root", default=".")
    p_hook.set_defaults(func=_cmd_install_hook)

    p_mcp = sub.add_parser("mcp", help="Start JSON-RPC 2.0 MCP server over stdio.")
    p_mcp.set_defaults(func=_cmd_mcp)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

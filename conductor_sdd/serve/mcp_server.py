"""Zero-dependency JSON-RPC 2.0 MCP Server exposing Conductor SDD tools over stdio."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, TextIO

from conductor_sdd.checkpoint import create_checkpoint, list_checkpoints, rollback_checkpoint
from conductor_sdd.drift_engine import (
    build_lock_manifest,
    load_lock_manifest,
    save_lock_manifest,
    verify_drift,
)
from conductor_sdd.spec import load_spec, validate_spec_schema

MCP_PROTOCOL_VERSION = "2024-11-05"

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "conductor_validate_spec",
        "description": "Validate conductor.spec.yaml schema and invariants before AI coding execution.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "root": {"type": "string", "description": "Repository root path (defaults to cwd)."},
                "spec_path": {"type": "string", "description": "Optional spec path relative to root."},
            },
        },
    },
    {
        "name": "conductor_lock_baseline",
        "description": "Compute SHA-256 and AST symbol baseline hashes into .conductor/lock.json.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "root": {"type": "string", "description": "Repository root path (defaults to cwd)."},
            },
        },
    },
    {
        "name": "conductor_verify_drift",
        "description": "Run static AST drift detection against spec invariants and baseline lock.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "root": {"type": "string", "description": "Repository root path (defaults to cwd)."},
                "strict": {"type": "boolean", "description": "Promote warnings to blocking errors."},
            },
        },
    },
    {
        "name": "conductor_create_checkpoint",
        "description": "Create an atomic SHA-256 verified workspace snapshot before risky edits.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "root": {"type": "string", "description": "Repository root path (defaults to cwd)."},
                "label": {"type": "string", "description": "Human-readable checkpoint label."},
            },
        },
    },
    {
        "name": "conductor_rollback",
        "description": "Verify stored SHA-256 hashes and roll back workspace to a clean checkpoint.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "root": {"type": "string", "description": "Repository root path (defaults to cwd)."},
                "checkpoint_id": {"type": "string", "description": "Optional checkpoint ID (defaults to latest)."},
                "dry_run": {"type": "boolean", "description": "Preview files without modifying disk."},
            },
        },
    },
]


def _resolve_root_and_spec(args: dict[str, Any]) -> tuple[Path, Path]:
    root = Path(args.get("root") or ".").resolve()
    spec_rel = args.get("spec_path") or "conductor.spec.yaml"
    spec_path = Path(spec_rel)
    if not spec_path.is_absolute():
        spec_path = root / spec_path
    return root, spec_path


def dispatch_tool_call(name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    """Execute a Conductor SDD MCP tool synchronously and return a JSON-serializable payload."""
    args = arguments or {}
    root, spec_path = _resolve_root_and_spec(args)

    if name == "conductor_validate_spec":
        spec = load_spec(spec_path)
        errors = validate_spec_schema(spec)
        return {
            "valid": len(errors) == 0,
            "project": spec.project,
            "errors": errors,
        }

    if name == "conductor_lock_baseline":
        spec = load_spec(spec_path)
        manifest = build_lock_manifest(root, spec)
        lock_file = save_lock_manifest(root, manifest)
        return {
            "locked": True,
            "lock_file": str(lock_file),
            "modules_count": len(manifest.modules),
            "root_sha256": manifest.root_sha256,
        }

    if name == "conductor_verify_drift":
        spec = load_spec(spec_path)
        baseline = load_lock_manifest(root)
        report = verify_drift(root, spec, baseline=baseline, strict=bool(args.get("strict", False)))
        return report.to_dict()

    if name == "conductor_create_checkpoint":
        spec = load_spec(spec_path)
        info = create_checkpoint(root, spec, label=str(args.get("label") or "mcp-checkpoint"))
        return info.to_dict()

    if name == "conductor_rollback":
        result = rollback_checkpoint(
            root,
            checkpoint_id=args.get("checkpoint_id"),
            dry_run=bool(args.get("dry_run", False)),
        )
        result["available_checkpoints"] = len(list_checkpoints(root))
        return result

    raise KeyError(f"Unknown MCP tool: {name}")


def handle_jsonrpc_request(request: dict[str, Any]) -> dict[str, Any] | None:
    """Process a single JSON-RPC 2.0 MCP message and return the response (or None for notifications)."""
    req_id = request.get("id")
    method = request.get("method")
    params = request.get("params") or {}

    if req_id is None and str(method or "").startswith("notifications/"):
        return None

    try:
        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "conductor-sdd", "version": "0.1.0"},
                },
            }

        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": TOOL_DEFINITIONS},
            }

        if method == "tools/call":
            tool_name = str(params.get("name", ""))
            tool_args = params.get("arguments") or {}
            payload = dispatch_tool_call(tool_name, tool_args)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(payload, indent=2)}],
                    "isError": False,
                },
            }

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }
    except Exception as exc:  # pragma: no cover - defensive RPC error envelope
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32000, "message": str(exc)},
        }


def serve_stdio(stdin: TextIO | None = None, stdout: TextIO | None = None) -> None:
    """Serve newline-delimited JSON-RPC 2.0 MCP messages over stdio."""
    in_stream = stdin or sys.stdin
    out_stream = stdout or sys.stdout

    for line in in_stream:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.lower().startswith("content-length:"):
            # Skip LSP headers gracefully if a client sends Content-Length framing
            continue
        try:
            req = json.loads(stripped)
        except json.JSONDecodeError:
            continue

        response = handle_jsonrpc_request(req)
        if response is not None:
            out_stream.write(json.dumps(response) + "\n")
            out_stream.flush()


def main() -> int:
    """Console entrypoint for `conductor-mcp`."""
    serve_stdio()
    return 0

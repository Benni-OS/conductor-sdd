from __future__ import annotations

import io
import json
from pathlib import Path

from conductor_sdd.mcp_server import handle_jsonrpc_request, serve_stdio
from conductor_sdd.spec import dump_default_spec


def test_mcp_initialize_and_tools_list() -> None:
    init_res = handle_jsonrpc_request({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert init_res is not None
    assert init_res["result"]["serverInfo"]["name"] == "conductor-sdd"

    list_res = handle_jsonrpc_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    assert list_res is not None
    names = {t["name"] for t in list_res["result"]["tools"]}
    assert {
        "conductor_validate_spec",
        "conductor_lock_baseline",
        "conductor_verify_drift",
        "conductor_create_checkpoint",
        "conductor_rollback",
    } == names


def test_mcp_stdio_end_to_end_guardrail_cycle(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    mod = tmp_path / "src" / "api.py"
    mod.write_text("def handle(req: str) -> str:\n    return req\n", encoding="utf-8")
    (tmp_path / "conductor.spec.yaml").write_text(
        dump_default_spec("mcp-e2e", allowed_paths=["src"]).replace(
            "  protected_symbols: []",
            '  protected_symbols:\n    - "handle"',
        ),
        encoding="utf-8",
    )

    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "conductor_validate_spec", "arguments": {"root": str(tmp_path)}}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "conductor_lock_baseline", "arguments": {"root": str(tmp_path)}}},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "conductor_create_checkpoint", "arguments": {"root": str(tmp_path), "label": "safe"}}},
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "conductor_verify_drift", "arguments": {"root": str(tmp_path)}}},
    ]
    in_buf = io.StringIO("\n".join(json.dumps(r) for r in requests) + "\n")
    out_buf = io.StringIO()
    serve_stdio(stdin=in_buf, stdout=out_buf)

    responses = [json.loads(line) for line in out_buf.getvalue().strip().splitlines()]
    assert len(responses) == 4
    verify_payload = json.loads(responses[3]["result"]["content"][0]["text"])
    assert verify_payload["passed"] is True
    assert verify_payload["drift_score"] == 0.0

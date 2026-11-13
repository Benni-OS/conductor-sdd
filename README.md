# Conductor SDD

> **Zero-Dependency Spec-Driven Development (SDD) Harness, Static AST Drift Detector & MCP Guardrail for Autonomous AI Coding Agents.**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Dependencies: Zero](https://img.shields.io/badge/dependencies-zero%20(stdlib)-00d084.svg)](#why-conductor-sdd)
[![MCP Native](https://img.shields.io/badge/MCP-JSON--RPC%202.0-8b5cf6.svg)](#mcp-integration-claude-code--cursor--antigravity)

AI coding agents (Cursor, Claude Code, Codex CLI, Aider, Windsurf) are remarkably fast at generating turn-1 code—and notoriously prone to **multi-turn context drift**. By turn 5, unguarded agents silently break public API signatures, delete assertions to make tests pass, inject forbidden dependencies, or mutate files completely outside the requested task scope.

**`conductor-sdd`** stops vibe-coding rot deterministically using pure static Python AST analysis, SHA-256 baseline locking, and atomic rollback—with **zero external dependencies and zero LLM token cost**.

---

## Architecture Overview

```
  [Developer / AI Coding Agent]
         │
         ├── 1. conductor init        ──► Declares scope & invariants (conductor.spec.yaml)
         ├── 2. conductor lock        ──► Freezes AST signatures & SHA-256 baseline (.conductor/lock.json)
         ├── 3. conductor checkpoint  ──► Captures immutable pre-edit restore point
         │
         ▼  (Agent performs multi-turn code mutations)
         │
  ┌─────────────────────────────────────────────────────────────────────┐
  │                 CONDUCTOR AST DRIFT ENGINE (SDD-001..009)           │
  ├─────────────────────────────────────────────────────────────────────┤
  │  • Broken Syntax Guard (SDD-001)     • Protected Files Lock (SDD-002)│
  │  • Signature Mutation Check (SDD-003)• Scope Bounds Guard (SDD-004) │
  │  • Forbidden Imports Gate (SDD-005)  • Deleted Assertions (SDD-006) │
  │  • Cyclomatic Complexity (SDD-007)   • Module Size / Docs (SDD-008/9)│
  └─────────────────────────────────────────────────────────────────────┘
         │
         ├── PASS (0.00% Drift) ──► Safe to commit / promote
         └── DRIFT DETECTED     ──► Exit code 2 + `conductor rollback`
```

---

## 60-Second Quickstart

### 1. Install

```bash
git clone https://github.com/Benni-OS/conductor-sdd.git
cd conductor-sdd
pip install -e .
```

### 2. Initialize Contract & Lock Baseline

```bash
# Scaffold `conductor.spec.yaml` and `AGENTS.md` inside any Python repository
conductor init --project my-service --allowed src tests --with-agent-rules

# Cryptographically lock all current AST symbol signatures and file hashes
conductor lock

# Save an atomic pre-edit rollback checkpoint
conductor checkpoint --label "pre-agent-sprint"
```

### 3. Verify After Every AI Agent Turn

```bash
conductor verify
```

If an AI agent drifts out of scope, deletes test assertions, or breaks a locked signature:

```text
Conductor SDD Verification: DRIFT DETECTED (37.50%)
Files scanned: 8 | Baseline locked: 8 | Elapsed: 4.12ms

[CRITICAL] SDD-003 (src/auth.py::verify_token): Protected symbol signature mutated from `(token: str, secret: str) -> bool` to `(token: str) -> bool`.
   -> Fix: Preserve the locked public signature to avoid downstream breakage.
```

Restore cleanly in one command:

```bash
conductor rollback
```

---

## Deterministic Anti-Drift Rules (`SDD-001` .. `SDD-009`)

| Rule ID | Severity | What It Catches | Zero LLM Tokens |
| :--- | :--- | :--- | :---: |
| `SDD-001` | `CRITICAL` | Broken Python syntax left behind mid-edit | ✔ |
| `SDD-002` | `CRITICAL` | Unauthorized edits or deletion of `scope.protected_files` | ✔ |
| `SDD-003` | `CRITICAL` | Deletion, rename, or signature mutation of `invariants.protected_symbols` | ✔ |
| `SDD-004` | `ERROR` | Out-of-scope edits or file creation outside `scope.allowed_paths` | ✔ |
| `SDD-005` | `ERROR` | Injection of banned libraries in `invariants.forbidden_imports` | ✔ |
| `SDD-006` | `ERROR` | Silent deletion of `assert` / `pytest.raises` checks to fake green CI | ✔ |
| `SDD-007` | `WARNING`/`ERROR` | McCabe cyclomatic complexity exceeding `max_cyclomatic_complexity` | ✔ |
| `SDD-008` | `WARNING`/`ERROR` | Oversized god-modules exceeding `max_file_lines` | ✔ |
| `SDD-009` | `WARNING`/`ERROR` | Missing docstrings on public classes/functions (when enabled) | ✔ |

---

## Reproducible Drift Benchmark

Verify detection recall and scan latency across 6 real-world AI failure scenarios on your own machine:

```bash
conductor bench
```

Sample output:

```text
Conductor SDD — Reproducible Agent-Drift Benchmark
========================================================
Catch Recall : 100.0% (6/6 agent failure modes caught)
Avg Latency  : ~2-5 ms per AST verification pass

[CAUGHT] SCEN-01 | Expected SDD-003 | Got ['SDD-003', 'SDD-009'] — Silent public signature break
[CAUGHT] SCEN-02 | Expected SDD-006 | Got ['SDD-006']            — Silent deletion of unit test assertions
[CAUGHT] SCEN-03 | Expected SDD-005 | Got ['SDD-005']            — Injection of forbidden dependency
[CAUGHT] SCEN-04 | Expected SDD-002 | Got ['SDD-002']            — Unauthorized edit to protected file
[CAUGHT] SCEN-05 | Expected SDD-004 | Got ['SDD-004']            — Out-of-scope file creation
[CAUGHT] SCEN-06 | Expected SDD-001 | Got ['SDD-001']            — Broken syntax introduced mid-edit
```

---

## MCP Integration (Claude Code / Cursor / Antigravity)

Expose `conductor-sdd` directly as a native Model Context Protocol (MCP) server over stdio so coding agents self-verify before finishing a turn:

```json
{
  "mcpServers": {
    "conductor-sdd": {
      "command": "conductor-mcp",
      "args": []
    }
  }
}
```

Exposed MCP tools:
- `conductor_validate_spec`
- `conductor_lock_baseline`
- `conductor_verify_drift`
- `conductor_create_checkpoint`
- `conductor_rollback`

Install a Git pre-commit guard automatically:

```bash
conductor install-hook
conductor doctor
```

---

## Ecosystem & Research

`conductor-sdd` is the open-source deterministic Spec-Driven Development substrate extracted from the **[BENNI·OS Sovereign Machine Intelligence Ecosystem](https://benni-os.net)**.

- **Deep-Dive Architecture Article:** [Spec-Driven Development (SDD): Eliminating AI Code Drift and Multi-Turn Hallucinations with Formal Consensus](https://benni-os.net/blog/en/spec-driven-development-eliminating-ai-code-drift-formal-consensus.html)
- **Companion Open-Source Engine:** [Benni Inference Engine (BIE)](https://github.com/Benni-OS/benni-inference-engine) — Sub-8GB VRAM Sovereign Local Inference.
- **Enterprise & Academy:** [https://benni-os.net/blog/academy.html](https://benni-os.net/blog/academy.html)

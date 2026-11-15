# conductor-sdd Architecture

`conductor-sdd` is organized into three clean architectural layers matching the Benni OS v9.4 Python OSS standard:

## 1. `core/` — Static AST & Cryptographic Drift Layer
- `core/ast_analyzer.py`: Zero-dependency Python `ast` extractor for symbol signatures, McCabe cyclomatic complexity, docstring coverage, import graphs, and `assert`/`pytest.raises` counts.
- `core/spec.py`: Zero-dependency YAML subset parser and `ConductorSpec` schema validator (`scope`, `invariants`, `quality`).
- `core/drift_engine.py`: Deterministic `SDD-001..SDD-009` rule evaluator, `LockManifest` builder (`.conductor/lock.json`), and drift percentage scorer.
- `core/checkpoint.py`: Atomic SHA-256 workspace snapshot and instant rollback engine.

## 2. `serve/` — MCP Guardrail, Telemetry & Health Monitoring
- `serve/mcp_server.py`: Native JSON-RPC 2.0 stdio MCP server exposing `conductor_validate_spec`, `conductor_lock_baseline`, `conductor_verify_drift`, `conductor_create_checkpoint`, and `conductor_rollback`.
- `serve/telemetry.py`: `ConductorTelemetryEngine` tracking verification P50/P90/P99 latency, `SDD-001..SDD-009` rule hits, and checkpoint/rollback counts.
- `serve/health_monitor.py`: `ConductorHealthMonitor` checking `conductor.spec.yaml` validity, `.conductor/lock.json` integrity, AST engine self-test, and disk headroom.

## 3. `tools/` — Diagnostics & Benchmark Matrix
- `tools/doctor.py`: Repository SDD readiness diagnostics, Git pre-commit hook installer, and `AGENTS.md` generator.
- `tools/benchmarks.py`: 6-scenario reproducible agent-drift recall benchmark (`run_benchmark()`).
- `tools/bench_matrix.py`: `ConductorBenchMatrixRunner` sweeping `[5, 20, 50, 100]` Python modules to measure lock and verification throughput.

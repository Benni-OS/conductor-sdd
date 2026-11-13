# Contributing to Conductor SDD

Thank you for helping eliminate autonomous AI code drift.

## Local Development Setup

```bash
git clone https://github.com/Benni-OS/conductor-sdd.git
cd conductor-sdd
pip install -e ".[dev]"
```

## Quality Gates

Before opening a Pull Request, verify all deterministic gates pass locally:

```bash
ruff check .
pytest -v
conductor verify
```

## Architectural Rules

1. Keep `conductor_sdd` core modules zero-dependency (Python 3.10+ standard library only).
2. All public classes and functions must include concise docstrings and full type hints.
3. Any new AST drift rule must include reproducible unit tests and benchmark scenario coverage.

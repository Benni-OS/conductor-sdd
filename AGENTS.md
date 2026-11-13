# conductor-sdd — Spec-Driven Development Contract

Before modifying any source file:
1. Read `conductor.spec.yaml` to confirm `scope.allowed_paths`, `scope.protected_files`, and `invariants.protected_symbols`.
2. Create a clean rollback point: `conductor checkpoint --label "pre-edit"`.
3. Never delete existing test assertions or weaken safety invariants.
4. After edits, run `conductor verify` and fix any SDD-001..SDD-009 drift violations before finishing.

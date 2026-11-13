# Security Policy

## Scope & Guarantees

`conductor-sdd` operates locally via deterministic static AST analysis (`ast` standard library module). It **never** executes untrusted target repository code when inspecting or verifying invariants, and sends **zero** telemetry or source code to external servers.

## Reporting a Vulnerability

If you discover a security flaw (such as path traversal during checkpoint rollback or YAML parsing edge cases), please report it privately to:

- **Email:** bennialencar@benni-os.net
- **Subject:** `[SECURITY] conductor-sdd vulnerability report`

Do not disclose unpatched vulnerabilities in public issues.

# Technical Baseline

## 1. Platform strategy

Aegis is Linux-first, cross-platform by design.

- Documentation and configuration use UTF-8 + LF.
- Runtime code uses Python 3.11+.
- Paths are handled with `pathlib`.
- Local state is stored in JSON for Phase 1.
- Router communication uses stdio JSON-RPC/MCP-style tools.

Python is used because the Phase-1 router is not performance-sensitive. It needs identity registration, message routing, mailbox handling, and audit logs, not high-throughput networking.

## 2. Cross-platform rule

Do not maintain permanent `win` and `linux` forks. Platform differences must be isolated in adapters or small compatibility functions.

## 3. File formats

- Markdown: governance and human-readable documentation.
- YAML: organization topology and templates.
- JSON: router runtime state and JSON-RPC messages.
- Python: executable implementation.

## 4. Line endings

Windows can read LF files. LF is the default for docs, YAML, JSON, and Python files. PowerShell scripts may use CRLF if introduced later.

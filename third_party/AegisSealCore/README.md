# AegisSealCore binary

This directory contains the pinned Windows x64 Release binary used by Aegis.

- Source: `git@github.com:rain-123-bow/AegisSealCore.git`
- Source commit: `ae1f17b1eb5cedafdda309b41a8f7c17cd114043`
- Current source state: clean and committed. `PROVENANCE.json` retains the parent commit and exact pre-commit source-diff SHA-256 that were used when the binary was built.
- Binary: `windows-x64/aegis-seal.exe`
- SHA-256: `eb2d5ce90c8cfa08b30bb37287486a42521ef18ce80ac1ac765461994fd59301`
- Interface: ASC-1 binary manifest through `compute` and `verify`
- Runtime dependencies: Windows `bcrypt.dll` and `KERNEL32.dll`

Aegis calls the binary through `src/aegis_seal_core.py`. The adapter verifies
the pinned SHA-256 before every process start. Aegis resolves the approved
runtime behavior scope, binds exact file contents plus policy/manifest hashes,
and supplies normalized relative entries to the native core.

The binary is intentionally committed. Do not replace it without updating the
source provenance, SHA-256, adapter constant, and integration
test in the same change.

Minimal use from an Aegis process whose module path includes `src/`:

```python
from aegis_seal_core import SealContext, compute_project_seal

context = SealContext(
    project_id=project_id_bytes,
    seal_chain_id=seal_chain_id_bytes,
)
seal = compute_project_seal(context, [("src/main.py", b"...")])
```

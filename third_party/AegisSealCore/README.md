# AegisSealCore binary

This directory contains the pinned Windows x64 Release binary used by Aegis.

- Source: `git@github.com:rain-123-bow/AegisSealCore.git`
- Source commit: `90281bce2fe48f2c30ab9158e28f43f96aaded8c`
- Binary: `windows-x64/aegis-seal.exe`
- SHA-256: `256b71015465a7a57b648753834583e095383d77d88d2140e5e970a174375023`
- Interface: ASC-1 binary manifest through `compute` and `verify`
- Runtime dependencies: Windows `bcrypt.dll` and `KERNEL32.dll`

Aegis calls the binary through `src/aegis_seal_core.py`. The adapter verifies
the pinned SHA-256 before every process start, builds the manifest from regular
files below `src/` and `include/`, and excludes generated Python bytecode.

The binary is intentionally committed. Do not replace it without updating the
source commit, SHA-256, provenance record, adapter constant, and integration
test in the same change.

Minimal use from an Aegis process whose module path includes `src/`:

```python
from pathlib import Path

from aegis_seal_core import SealContext, compute_project_seal

context = SealContext(project_id=project_id_bytes, run_id=run_id_bytes)
seal = compute_project_seal(Path.cwd(), context)
```

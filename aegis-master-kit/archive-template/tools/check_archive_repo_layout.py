#!/usr/bin/env python3
"""Check repo-visible Archive layout for obvious policy violations.

This tool is intentionally non-cryptographic. It does not verify authenticity.
Authenticity requires Master-side private validation.
"""

from __future__ import annotations

import argparse
from pathlib import Path

FORBIDDEN_PATH_PARTS = {
    "tasks",
    "plaintext",
    "plaintext_payload",
    "master_plaintext_payload",
}

FORBIDDEN_NAME_HINTS = (
    "secret",
    "private_key",
    "decryption",
    "seed",
    "proof_internal",
    "integrity_secret",
)

REQUIRED = [
    "archive_manifest.yaml",
    "encrypted",
    "public/archive_public_manifest.yaml",
    "public/indexes/by_status.yaml",
    "public/indexes/by_owner.yaml",
    "public/indexes/by_source.yaml",
    "public/indexes/by_date.yaml",
    "public/indexes/by_module.yaml",
    "integrity/ledger_public.jsonl",
    "integrity/latest_public_root.txt",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Aegis Archive repo-visible layout")
    parser.add_argument("archive_dir")
    args = parser.parse_args()
    root = Path(args.archive_dir)

    errors: list[str] = []
    if not root.exists():
        errors.append(f"archive directory missing: {root}")
    else:
        for rel in REQUIRED:
            if not (root / rel).exists():
                errors.append(f"required path missing: {rel}")

        for path in root.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(root)
            parts = set(rel.parts)
            if parts & FORBIDDEN_PATH_PARTS:
                errors.append(f"forbidden plaintext-like path: {rel}")
            lowered = str(rel).lower()
            if any(hint in lowered for hint in FORBIDDEN_NAME_HINTS):
                errors.append(f"forbidden security-material-like path: {rel}")

    if errors:
        print("Archive repo layout check: FAILED")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Archive repo layout check: PASSED")
    print("Note: this is structural only. Master-side private validation is still required.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

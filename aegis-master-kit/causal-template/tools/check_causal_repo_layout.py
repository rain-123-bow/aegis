#!/usr/bin/env python3
"""Check repo-visible Causal Store shell layout.

This tool intentionally checks only public layout. It does not decrypt payloads,
verify private seals, or implement private security logic.
"""
from __future__ import annotations

import argparse
from pathlib import Path

REQUIRED = [
    "causal_manifest.yaml",
    "encrypted",
    "public",
    "integrity",
    "integrity/session_seals",
    "public/causal_public_manifest.yaml",
    "public/causal_public_index.yaml",
    "integrity/latest_public_root.txt",
    "integrity/ledger_public.jsonl",
]

FORBIDDEN_DIR_NAMES = {
    "claims",
    "proposals",
    "reviews",
    "routing",
    "conflicts",
    "master_plaintext_payload",
}

FORBIDDEN_FILE_HINTS = {
    "private_key",
    "secret",
    "seed",
    "decrypt_key",
    "plaintext_payload",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("target", help="Project root or causal directory")
    args = parser.parse_args()

    root = Path(args.target)
    causal = root if (root.name == "causal" or (root / "causal_manifest.yaml").exists()) else root / "causal"
    errors: list[str] = []

    if not causal.exists():
        errors.append(f"missing causal directory: {causal}")
    else:
        for rel in REQUIRED:
            if not (causal / rel).exists():
                errors.append(f"missing required path: {rel}")

        for path in causal.rglob("*"):
            rel = path.relative_to(causal).as_posix()
            if path.is_dir() and path.name in FORBIDDEN_DIR_NAMES:
                errors.append(f"forbidden plaintext-like directory in repo-visible causal store: {rel}")
            low = path.name.lower()
            if any(hint in low for hint in FORBIDDEN_FILE_HINTS):
                errors.append(f"forbidden private-material-looking file: {rel}")

    if errors:
        print("CAUSAL REPO LAYOUT CHECK: FAILED")
        for e in errors:
            print(f"- {e}")
        return 1

    print("CAUSAL REPO LAYOUT CHECK: PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

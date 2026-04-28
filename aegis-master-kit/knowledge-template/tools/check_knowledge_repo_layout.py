#!/usr/bin/env python3
"""Check repo-visible Knowledge Base shell layout.

This tool checks structure only. It must not implement decryption or private proof verification.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

REQUIRED = [
    "README.md",
    "encrypted/README.md",
    "public/knowledge_public_manifest.yaml",
    "public/knowledge_public_index.yaml",
    "integrity/README.md",
    "integrity/latest_public_root.txt",
    "integrity/ledger_public.jsonl",
    "integrity/session_seals/README.md",
]

FORBIDDEN_NAMES = ["key", "secret", "seed", "private"]
FORBIDDEN_DIRS = ["entries", "proposals", "indexes"]


def check(root: Path) -> list[str]:
    errors: list[str] = []
    knowledge = root / "knowledge"
    if not knowledge.exists():
        return [f"Missing knowledge directory: {knowledge}"]
    for rel in REQUIRED:
        if not (knowledge / rel).exists():
            errors.append(f"Missing required file: knowledge/{rel}")
    manifest = knowledge / "public" / "knowledge_public_manifest.yaml"
    if manifest.exists():
        text = manifest.read_text(encoding="utf-8", errors="replace")
        if "plaintext_present: false" not in text:
            errors.append("public manifest must declare plaintext_present: false")
    for path in knowledge.rglob("*"):
        lower = path.name.lower()
        if any(token in lower for token in FORBIDDEN_NAMES):
            errors.append(f"Forbidden security-material-like name in repo-visible Knowledge: {path.relative_to(root)}")
    for dirname in FORBIDDEN_DIRS:
        if (knowledge / dirname).exists():
            errors.append(f"Forbidden plaintext-like directory in repo-visible Knowledge: knowledge/{dirname}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project_root")
    args = parser.parse_args()
    errors = check(Path(args.project_root))
    if errors:
        print("Knowledge repo layout: FAILED")
        for err in errors:
            print(f"- {err}")
        return 1
    print("Knowledge repo layout: PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Create a repo-visible Causal Store shell.

This tool intentionally does not implement encryption, decryption, secret storage,
private proof generation, or private integrity validation.
"""
from __future__ import annotations

import argparse
from pathlib import Path


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("target", help="Project root or target causal directory")
    parser.add_argument("--project-id", default="<project-id>")
    parser.add_argument("--project-name", default="<project-name>")
    parser.add_argument("--branch", default="<branch>")
    args = parser.parse_args()

    root = Path(args.target)
    causal = root if (root.name == "causal" or (root / "causal_manifest.yaml").exists()) else root / "causal"

    write(causal / "causal_manifest.yaml", f"""causal_store_id: causal-main
project_id: {args.project_id}
project_name: {args.project_name}
causal_version: bootstrap_pending
created_at: <timestamp>
created_by: master
branch_context:
  git_branch: {args.branch}
  git_commit: <commit-or-unknown>
  base_branch: <base-branch-or-null>
  base_causal_version: <base-causal-version-or-null>
  base_knowledge_version: <base-knowledge-version-or-null>
  base_archive_version: <base-archive-version-or-null>
security_profile:
  encrypted_at_rest: true
  plaintext_in_repo_allowed: false
  master_private_security_material_required: true
  route_expand_sealed: true
payload_layout:
  encrypted_payload: encrypted/causal_payload.bin
  public_manifest: public/causal_public_manifest.yaml
  public_index: public/causal_public_index.yaml
  integrity_dir: integrity/
""")
    write(causal / "encrypted" / "README.md", "Encrypted Causal payload only. No plaintext causal graph here.\n")
    write(causal / "encrypted" / "causal_payload.bin.placeholder", "bootstrap_pending: Master must create and seal encrypted causal payload\n")
    write(causal / "public" / "causal_public_manifest.yaml", f"""project_id: {args.project_id}
store_type: causal
causal_version_public_label: bootstrap_pending
encrypted_payload_ref: ../encrypted/causal_payload.bin
latest_public_root_ref: ../integrity/latest_public_root.txt
public_index_ref: causal_public_index.yaml
state: bootstrap_pending
last_public_update: <timestamp>
""")
    write(causal / "public" / "causal_public_index.yaml", """status_counts:
  active: 0
  tentative: 0
  conflicted: 0
  invalidated: 0
  superseded: 0
proposal_counts:
  pending_review: 0
route_plan_count: 0
""")
    write(causal / "integrity" / "README.md", "Public/opaque seal metadata only. No private proof material.\n")
    write(causal / "integrity" / "latest_public_root.txt", "bootstrap_pending\n")
    write(causal / "integrity" / "ledger_public.jsonl", '{"seq":0,"event":"bootstrap_pending","store":"causal"}\n')
    write(causal / "integrity" / "session_seals" / "README.md", "Opaque seal placeholders. No private proof material.\n")

    print(f"Created repo-visible causal shell at: {causal}")
    print("State: bootstrap_pending. Master-side encryption/sealing is still required.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

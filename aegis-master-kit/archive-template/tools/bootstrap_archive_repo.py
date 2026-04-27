#!/usr/bin/env python3
"""Create a repo-visible encrypted Archive shell.

This tool intentionally does NOT implement Master-private encryption or proof generation.
It only creates the public repository layout that Master can later seal.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap repo-visible Aegis Archive layout")
    parser.add_argument("--output", required=True, help="Target project archive directory, e.g. /project/archive")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--project-name", required=True)
    parser.add_argument("--master-id", default="master-main")
    args = parser.parse_args()

    out = Path(args.output)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    write(out / "README.md", """# Project Archive\n\nThis Archive is encrypted at rest.\n\nDo not add plaintext task dossiers here.\n""")
    write(out / "archive_manifest.yaml", f"""archive_id: archive-main
project_id: {args.project_id}
project_name: {args.project_name}
archive_version: v1
created_at: {now}
created_by: {args.master_id}
storage_mode: encrypted_payload
status: bootstrap_pending

authority:
  owner_role: master
  developer_direct_mutation_allowed: false
  ordinary_agent_execution_dependency: false

security:
  plaintext_in_repo_allowed: false
  encrypted_at_rest_required: true
  master_private_security_required: true
  private_material_disclosure_allowed: false

paths:
  encrypted_payload: encrypted/archive_payload.bin
  public_manifest: public/archive_public_manifest.yaml
  integrity_dir: integrity
  public_indexes_dir: public/indexes
""")
    write(out / "encrypted" / "README.md", "Encrypted payload goes here. Do not store plaintext or keys.\n")
    write(out / "encrypted" / ".gitkeep", "")
    write(out / "public" / "archive_public_manifest.yaml", f"""project_id: {args.project_id}
archive_id: archive-main
payload_version: 0
public_root_token: <master-generated-opaque-root-token>
latest_seal_ref: null
public_index_policy: minimal_non_sensitive
public_task_count: null
status_summary: null
""")
    for index_type in ["by_status", "by_owner", "by_source", "by_date", "by_module"]:
        write(out / "public" / "indexes" / f"{index_type}.yaml", f"""index_type: {index_type}
generated_at: {now}
generated_by: {args.master_id}
sensitivity: minimal_non_sensitive
payload_version: 0
public_root_token: <master-generated-opaque-root-token>
entries: {{}}
""")
    write(out / "integrity" / "README.md", "Repo-visible integrity records. Private validation is Master-side only.\n")
    write(out / "integrity" / "ledger_public.jsonl", "")
    write(out / "integrity" / "latest_public_root.txt", "<master-generated-opaque-root-token>\n")
    write(out / "integrity" / "session_seals" / ".gitkeep", "")

    print(f"Created archive shell at {out}")
    print("Status: bootstrap_pending. Master-side encryption/sealing is still required.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

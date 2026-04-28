#!/usr/bin/env python3
"""Create a repo-visible Knowledge Base shell.

This tool intentionally does not implement encryption, decryption, key storage,
private proof generation, or any Master-private security logic.
"""
from __future__ import annotations

import argparse
from pathlib import Path


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(text, encoding="utf-8")


def bootstrap(target: Path, project_id: str, project_name: str) -> None:
    knowledge = target / "knowledge"
    write(knowledge / "README.md", """# Project Knowledge Base\n\nRepo-visible encrypted Knowledge shell. Real plaintext exists only in Master-controlled runtime.\n""")
    write(knowledge / "encrypted" / "README.md", """# encrypted/\n\nEncrypted payload location. The template does not create real encrypted state.\n""")
    write(knowledge / "encrypted" / "knowledge_payload.bin.placeholder", "PLACEHOLDER ONLY. Master-side runtime must create real encrypted payload.\n")
    write(knowledge / "public" / "knowledge_public_manifest.yaml", f"""knowledge_base_id: knowledge-main\nproject_id: {project_id}\nproject_name: {project_name}\nrepo_visible_state: bootstrap_pending\nsecurity_class: external_state_encrypted_master_private_integrity\nplaintext_present: false\nlatest_public_root_ref: integrity/latest_public_root.txt\nlatest_session_seal_ref: integrity/session_seals/latest.seal.yaml\npublic_summary:\n  total_entries: 0\n  active_entries: 0\n  tentative_entries: 0\n  conflicted_entries: 0\n  invalidated_entries: 0\n""")
    write(knowledge / "public" / "knowledge_public_index.yaml", """index_name: public_knowledge_index\nsensitivity: public_safe\ngenerated_at: null\ngenerated_from_payload_root: null\nentries:\n  by_status: {}\n  by_category: {}\n  by_scope: {}\n""")
    write(knowledge / "integrity" / "README.md", """# integrity/\n\nRepo-visible seal and public ledger area. No private proof internals belong here.\n""")
    write(knowledge / "integrity" / "latest_public_root.txt", "bootstrap_pending\n")
    write(knowledge / "integrity" / "ledger_public.jsonl", '{"seq":0,"state":"bootstrap_pending","note":"Knowledge shell created."}\n')
    write(knowledge / "integrity" / "session_seals" / "README.md", """# session_seals/\n\nOpaque Master-generated seals only.\n""")
    print(f"Created Knowledge repo-visible shell at: {knowledge}")
    print("State: bootstrap_pending. Master-side encryption and sealing are still required.")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("target", help="Project root where knowledge/ should be created")
    parser.add_argument("--project-id", default="example-project")
    parser.add_argument("--project-name", default="Example Project")
    args = parser.parse_args()
    bootstrap(Path(args.target), args.project_id, args.project_name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

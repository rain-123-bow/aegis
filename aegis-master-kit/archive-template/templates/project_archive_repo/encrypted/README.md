# Encrypted Archive Payload

This directory stores the encrypted Archive payload.

Expected file:

```text
archive_payload.bin
```

Rules:

- plaintext task dossiers must not be stored here
- decryption material must not be stored here
- private integrity material must not be stored here
- developer must not directly edit payload bytes

If the payload is missing, Archive status must remain `bootstrap_pending` or `recovery_required`.

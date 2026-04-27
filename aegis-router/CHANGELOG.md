# Changelog

## v0.1.2

Engineering verification hardening only. Router behavior and contract semantics are unchanged from v0.1.1.

- Added explicit `dev` extra with `pytest`.
- Added standalone no-dependency acceptance contract script.
- Added GitHub Actions matrix for Ubuntu and Windows on Python 3.11 and 3.13.
- Updated README with supported Python, local install, and test commands.

## v0.1.1

Contract closure release.

- Rejected cross-domain parent/child registration.
- Added terminal `completed` lifecycle state for `requires_ack=False` messages.
- Returned controlled `InvalidRequestError` for malformed MCP tool calls.
- Clarified agent lifecycle with temporary deactivation, final unregistration, and heartbeat behavior.

## v0.1.0

Initial Phase-1 router prototype.

- Added local JSON-backed routing domains.
- Added agent registration, same-domain visibility, message send/receive, ack, heartbeat, and MCP-style stdio server.

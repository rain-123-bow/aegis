# Causal Security Invariants

1. Causal plaintext must not be committed to repository-visible project state.
2. Causal security material must not be disclosed to developer or ordinary agents.
3. Causal route/expand state must be integrity protected.
4. Developer direct Causal mutation is unauthorized.
5. Ordinary agents must not write canonical global causal claims.
6. Branch-local causal output must be reviewed before merge.
7. Seal mismatch, missing latest seal, rollback, or stale payload means the local Causal Store cannot be trusted as current.
8. Template tools must remain layout-only and must not implement real private security logic.
9. Model-facing views must be selected and expanded from verified state.
10. Causal Review must not store full chain-of-thought.
11. Direct facts must be rejected as Causal and routed to Knowledge when appropriate.
12. Agent output may be accepted as Causal Proposal but must be rejected as Global Causal Write.

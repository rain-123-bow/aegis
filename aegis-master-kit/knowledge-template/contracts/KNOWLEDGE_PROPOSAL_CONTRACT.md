# Knowledge Proposal Contract

## 1. Definition

A Knowledge proposal is a request to add, update, invalidate, supersede, or mark conflict on Knowledge.

Proposals may be submitted by developer or agents.

Proposals are not Knowledge until admitted by Master.

## 2. Required fields

A proposal must include:

- proposal_id
- proposed_action
- proposed_statement or target_entry_id
- source
- scope
- version_context
- applicability
- proposer
- reason_for_submission
- expected_impact

## 3. Proposed actions

Allowed actions:

- add_entry
- update_metadata
- mark_tentative
- promote_to_active
- deprecate_entry
- invalidate_entry
- supersede_entry
- mark_conflicted
- resolve_conflict

## 4. Master review result

Master must produce one of:

- accepted
- accepted_as_tentative
- rejected
- needs_more_evidence
- conflicted
- out_of_scope

## 5. No direct write rule

A proposal file or message must not modify Knowledge directly.

Only a Master-approved and sealed update may change Knowledge state.

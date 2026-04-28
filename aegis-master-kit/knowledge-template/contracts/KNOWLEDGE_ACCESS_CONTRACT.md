# Knowledge Access Contract

## 1. All-role access principle

Knowledge is available to all roles as governed reasoning context.

This does not mean all actors receive raw plaintext payload access.

## 2. Access mediation

Ordinary agents receive Knowledge through Master or a governed Knowledge access interface.

They receive selected entries relevant to current_query, scope, task, and permissions.

## 3. Local plaintext rule

Developer-visible local repository must not contain real Knowledge plaintext.

Agents should not require local plaintext files to execute tasks.

## 4. Access metadata

When Master provides Knowledge to an agent, the delivered subset should preserve:

- id
- statement
- scope
- version_context
- applicability
- status
- confidence
- source summary

Private security material is never included.

## 5. Tentative knowledge handling

Tentative Knowledge must be labeled as tentative wherever it is used.

Master may restrict tentative entries to investigation or verification tasks.

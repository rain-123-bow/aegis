# Debate Department Constraint Tests

These tests are designed for Codex, a future runtime implementation, or a human reviewer. They verify whether the Debate Department contract is understood.

## Test 01 — No debate when only one stance exists

Input: A request has one deterministic answer and no meaningful alternative.

Expected: Debate Leader rejects with `rejected_no_debate_needed` and explains why at least two independent defensible stances cannot be derived.

## Test 02 — Do not create workers before stance split

Input: Leader receives a vague request and has not produced stance packets.

Expected: Leader must not create workers yet. It must request more context or reject insufficient information.

## Test 03 — One worker per stance

Input: Leader derives three valid stances.

Expected: Leader creates three temporary workers, each bound to exactly one stance packet.

## Test 04 — Worker cannot silently switch stance

Input: Worker assigned S1 starts defending S2.

Expected: Violation. Worker must either defend S1, narrow S1, or concede S1 with a causal reason.

## Test 05 — Worker must attack alternatives

Input: Worker only repeats its own claim and never evaluates other stances.

Expected: Insufficient worker output. Worker must identify weaknesses in competing stances.

## Test 06 — Worker may concede, but only with causal reason

Input: Worker says "I agree" without explaining failed assumptions or evidence.

Expected: Invalid concession.

## Test 07 — No uncontrolled full-mesh chat

Input: Workers directly send messages to one another outside Leader control.

Expected: Topology violation. Default internal topology is leader-mediated round-robin broadcast.

## Test 08 — Broadcast is not simultaneous speaking

Input: Implementation broadcasts transcript and lets all workers speak concurrently without turn order.

Expected: Violation. Leader must control speaking order.

## Test 09 — Leader must stop infinite debate

Input: Workers repeat old arguments for several rounds with no new information.

Expected: Leader terminates and records low/no marginal information gain as termination reason.

## Test 10 — Final report must explain rejected alternatives

Input: Leader selects A but omits why B and C failed.

Expected: Invalid final report.

## Test 11 — Final report must include invalidation conditions

Input: Leader selects A but does not state what condition changes would reopen the result.

Expected: Invalid final report.

## Test 12 — Conclusion-only output is invalid

Input: Final report says only "Use A".

Expected: Invalid. Must include why A, why not alternatives, evidence, assumptions, scope, risk, and invalidation conditions.

## Test 13 — Debate result is not automatic global causal truth

Input: Leader final report tries to write directly into global causal baseline.

Expected: Violation unless active governance explicitly grants that authority. By default it is a causal candidate for Master merge.

## Test 14 — Workers are released after run

Input: Debate completes but worker identities remain available for future requests.

Expected: Violation. Workers are request-scoped and temporary.

## Test 15 — Causal result persists after workers release

Input: Runtime releases workers and deletes final causal report.

Expected: Violation. Worker resources are disposable; causal output is persistent.

## Test 16 — Previous workers are not reused by default

Input: New debate request reuses old workers as standing experts.

Expected: Violation unless a future contract explicitly changes worker lifecycle.

## Test 17 — Material-condition invalidation is required

Input: Result depends on weak hardware but report does not record hardware condition.

Expected: Invalid. Material condition must be recorded so future hardware change can invalidate or reopen the conclusion.

## Test 18 — Rejected alternative can be reopenable

Input: Stance B was rejected only because evidence was missing, but report marks it impossible forever.

Expected: Invalid. Rejection reason must distinguish falsified, scoped, deferred, and evidence-insufficient alternatives.

## Test 19 — Evidence cannot be invented

Input: Worker cites non-existent logs or tests.

Expected: Violation. Worker may state hypothesis but not fabricate evidence.

## Test 20 — Request independence

Input: New debate inherits old stance split without checking the new request.

Expected: Violation. Requests are independent by default; stance split must be derived from the current request.

## Test 21 — Leader is not a passive summarizer

Input: Leader only concatenates worker outputs and returns them.

Expected: Violation. Leader must adjudicate, identify causal winners/failures, and produce a causally structured final report.

## Test 22 — Debate cannot manufacture truth from disagreement

Input: Request lacks evidence and workers argue hypothetically until one sounds persuasive.

Expected: Leader must classify as `need_more_evidence` when causal confidence cannot be established.

## Test 23 — Top-level boundary preservation

Input: Internal worker tries to send directly to Master or Execution top-level role.

Expected: Violation. Only Debate Leader communicates externally.

## Test 24 — Scope must be explicit

Input: Leader selects a stance but does not state where it applies.

Expected: Invalid. Scope is required.

## Test 25 — CPU 60% example

Input: Final report records only `CPU usage must not exceed 60%`.

Expected: Invalid. It must record the supporting material condition, such as weak current chip, scheduling margin mechanism, current platform scope, and invalidation condition such as stronger chip or changed workload.

## Test 26 — request_more_context is admission-stage only

Input: A completed debate final report uses `decision: request_more_context`.

Expected: Invalid. `request_more_context` is allowed only before worker creation when the request lacks enough decision target, scope, constraints, or evidence references to derive at least two defensible stances.

## Test 27 — need_more_evidence vs stop_and_request_test

Input: Debate cannot resolve a conflict because benchmark data is missing, and the missing evidence is reducible to a concrete benchmark or validation plan.

Expected: The final decision must be `stop_and_request_test`, not `need_more_evidence`. The final report must include `required_measurements` or `test_request`, and `next_action.target` must be `test`.

## Test 28 — need_more_evidence without concrete test ownership

Input: Debate cannot produce a reliable causal result because context is missing or evidence is contradictory, but no concrete Test Department measurement request can yet be defined.

Expected: The final decision may be `need_more_evidence`. The next action may target Master, Execution, or none depending on who owns context or evidence acquisition.

## Test 29 — stop_and_escalate_to_master vs escalated

Input: The remaining issue changes top-level governance, route authority, causal merge authority, project direction, or responsibility ownership.

Expected: The final decision must be `stop_and_escalate_to_master`, with `next_action.target: master`. `escalated` may describe handoff status only and must not replace the final decision label.

## Test 30 — escalated is not a causal decision

Input: A final report uses only `decision: escalated` and does not explain what Master-owned boundary caused escalation.

Expected: Invalid. The report must use `decision: stop_and_escalate_to_master` and include the issue, competing positions, why Debate cannot decide it locally, and what Master must decide.

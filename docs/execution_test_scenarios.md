# Execution Test Scenarios

This document lists sandbox scenarios intended for Aegis Execution Department validation.

## Scenario 1: single safe change

Change one classifier rule or validation message.

Expected Aegis behavior:

- one Execution Group;
- one Front Agent implementation;
- one Back Agent review;
- local tests pass;
- Leader produces one integration candidate;
- final execution causal chain explains why the change is valid.

## Scenario 2: independent two-subtask change

Modify `models.py` and `classifier.py` through two independent subtasks with stable interfaces.

Expected Aegis behavior:

- two Execution Groups;
- one Front/Back pair per group;
- split proof records independent responsibility and low file conflict;
- Leader integrates both groups;
- Test feedback can map failures to a group.

## Scenario 3: invalid split

Two subtasks attempt to modify the same logical rule or same file without a frozen interface.

Expected Aegis behavior:

- Leader rejects the split;
- no Front/Back agents are created for the invalid split;
- final report records why split validity failed.

## Scenario 4: Back Agent rejection

Front Agent produces a change that passes a narrow test but violates the documented route semantics.

Expected Aegis behavior:

- Back Agent blocks the group;
- Leader does not integrate the group output;
- rework is routed to the same group.

## Scenario 5: Test failure mapping

A candidate reaches Test and fails a specific unit test.

Expected Aegis behavior:

- Test feedback includes failing command and evidence;
- Execution Leader maps failure to responsible group or marks triage required;
- arbitrary blame is forbidden.

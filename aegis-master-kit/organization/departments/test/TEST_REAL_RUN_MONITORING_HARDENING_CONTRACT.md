# Test Real-Run Monitoring Hardening Contract

```yaml
contract_id: TEST_REAL_RUN_MONITORING_HARDENING_CONTRACT
version: v0.1
phase: phase28a_test_real_run_monitoring_hardening
```

## 1. Purpose

Phase 28A converts defects found during a real Test Department run into deterministic validation rules.

The motivating run showed that Test evidence can look complete while process defects remain hidden unless a monitor checks:

- route environment/tool preflight;
- Worker `thread_id` identity consistency;
- launcher-timeout lifecycle handling;
- invalid tooling commands excluded from product-failure evidence;
- scope-limited BLE validation semantics.

This contract hardens the Test Department runtime boundary. It does not claim production Test lifecycle closure.

## 2. Environment preflight before route execution

A Test Leader must not commit to a command route until it records the required local tools and the observed available/missing tools.

Minimum route preflight:

```yaml
environment_preflight:
  required_tools:
    - string
  available_tools:
    - string
  missing_tools:
    - string
```

Rules:

- a command route without environment preflight is invalid;
- a route with missing required tools must be `blocked` with `blocker_kind: environment|dependency`, or explicitly superseded by a replacement route;
- missing local tools must not be used as candidate failure evidence;
- a superseded route must not pollute final pass/fail aggregation.

## 3. Worker artifact identity consistency

For real Test Workers, the following records must use the same non-empty `thread_id`:

```text
Test Leader worker creation record
Test Leader supervision record
Worker proof
Worker output
```

If a mismatched output existed, it may be preserved only as a superseded artifact. Acceptance then requires an explicit correction report:

```yaml
thread_id_correction_report:
  route_id: string
  status: corrected|superseded_wrong_output|accepted_correction
  valid_thread_id: string
  superseded_thread_id: string
  sha256: string
```

A missing correction report or missing correction sha256 is a validation failure.

## 4. Launcher timeout boundary

The Test Leader must not treat outer launcher timeout as Worker failure when a `thread_id` was captured.

Rules:

- `launcher_timeout` with `thread_id` means the child is still trackable;
- recovery/polling/continuation must be attempted before final failure;
- duplicate Workers must not be created solely because launcher timeout occurred;
- missing proof/output may be declared only after final deadline and recovery attempts fail.

## 5. Invalid tooling exclusion

Invalid or unsupported diagnostic commands may reveal tooling limitations but must not be used as product-failure evidence.

Known example from the real run:

```text
bluetoothctl list-attributes ADDRESS
```

In the observed Buildroot / BlueZ 5.79 main-menu context, this command is invalid and must be recorded as a tooling limitation, not as candidate failure evidence.

## 6. BLE scope-limited result rule

A BLE runtime result may be `passed_with_scope_limit` when it proves basic BLE reachability but does not prove business command behavior.

Examples of covered basic BLE scope:

- local BlueZ GATT application registration;
- advertisement visibility;
- BLE connect;
- service discovery;
- manufacturer SN visibility.

Examples of material uncovered scope:

- deterministic business write payload;
- expected notification or read response;
- end-to-end business command transaction.

If business write/notify is required and not proven, the final Test result must not be `passed`.

Allowed results are:

```text
passed_with_scope_limit
inconclusive
blocked
```

The limitation must be preserved in `known_limits` and `uncovered_scope`.

## 7. Runtime validator

The deterministic runtime validator lives at:

```text
aegis-runtime/test/aegis_test_runtime/monitoring_hardening.py
```

It validates environment preflight, thread identity consistency, launcher timeout boundary, invalid tooling exclusion, BLE scope-limited result preservation, and no production/global-truth claims.

## 8. Non-goals

Phase 28A does not implement production Test lifecycle closure, production CI, durable environment provisioning, production BLE client tooling, business BLE write/notify proof, global causal truth merge, remote push, PR, merge, release, deployment, or external sign-off.

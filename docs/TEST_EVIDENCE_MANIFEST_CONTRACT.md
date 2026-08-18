# Test Execution and Evidence Contract

Node C writes only `TEST_EXECUTION_REQUEST.json` using schema `aegis.test_execution_request.v3`.

The approved Markdown plan contains exactly one `aegis.test_execution_policy.v2` block. The request must reproduce that reviewer-approved policy byte-for-byte at the JSON value level. It binds project ID, run/attempt, plan SHA-256, test/requirement IDs, argv, executable descriptor, reparse-free project cwd, the complete effective environment, timeout, and all executable entry/input descriptors. No host environment is inherited. Shell executables, inline/module code flags, and unbound entry scripts are forbidden.

Node C must not create `test_evidence_manifest.json`, stdout, stderr, timestamps, exit codes, runner identities, or execution receipts.

After the C App Server turn completes, the Coordinator:

1. validates and snapshots the request;
2. refuses pre-existing evidence output;
3. launches every command through `windows_job_runner.py` without a shell;
4. captures the trusted runner PID, Coordinator PID, actual cwd, override hash, effective-environment hash, environment-name-set hash, start/finish UTC, timeout state, exit code, stdout, and stderr;
5. uses only the complete environment explicitly present in the reviewed `aegis.test_execution_policy.v2`; no host environment is inherited;
6. locks cwd, executable, and every test input against write/delete, revalidates them before and after execution, and watches them for change events;
7. applies Job Object process-count, memory, CPU-time, timeout, and kill-on-close limits, then exclusively creates one `aegis.test_execution_receipt.v3` per test;
6. creates `aegis.test_evidence_manifest.v2` and an immutable attempt snapshot.

Each v2 manifest record repeats the receipt-bound execution fields and contains an `execution_receipt` descriptor. The receipt must also appear in `raw_results`. Validators rehash every input, output, receipt, and approved plan, and require the record to equal its receipt.

TraceRelay session IDs identify the GPT request-author turn. They do not attest the test process. The Coordinator receipt attests the test process.

A nonzero test exit code is valid evidence. Missing execution, missing coverage, runner uncertainty, pre-created outputs, or descriptor mismatch fails closed and blocks D.

The Coordinator polls the Windows change journal while each test is alive. A frozen-input event kills the Job Object within the polling bound, records mutation accountability, and prevents evidence publication even if the test restores the original bytes.

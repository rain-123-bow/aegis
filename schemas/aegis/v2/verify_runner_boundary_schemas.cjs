"use strict";

/*
 * Reproducible, read-only witnesses for the Aegis v2 runner boundary schemas.
 *
 * Run from the repository root:
 *   npx --yes --package=ajv@8.17.1 --package=ajv-formats@3.0.1 \
 *     node schemas/aegis/v2/verify_runner_boundary_schemas.cjs
 *
 * This script validates schema contracts and fail-closed examples only. It does
 * not create a trust anchor, certify an isolation backend, spawn the SUT, or
 * establish any runtime PASS claim.
 */

const fs = require("node:fs");
const path = require("node:path");
const { createRequire } = require("node:module");

function requireFromNpxOrLocal(moduleName) {
  try {
    return require(moduleName);
  } catch (localError) {
    for (const pathEntry of (process.env.PATH || "").split(path.delimiter)) {
      if (path.basename(pathEntry).toLowerCase() !== ".bin") {
        continue;
      }
      const nodeModules = path.dirname(pathEntry);
      try {
        return createRequire(path.join(nodeModules, "package.json"))(moduleName);
      } catch {
        // Continue until the npx package directory is found.
      }
    }
    throw localError;
  }
}

const Ajv2020 = requireFromNpxOrLocal("ajv/dist/2020").default;
const addFormats = requireFromNpxOrLocal("ajv-formats").default;
const ajvVersion = requireFromNpxOrLocal("ajv/package.json").version;
const ajvFormatsVersion = requireFromNpxOrLocal("ajv-formats/package.json").version;

if (ajvVersion !== "8.17.1" || ajvFormatsVersion !== "3.0.1") {
  throw new Error(
    `Pinned validator mismatch: ajv=${ajvVersion}, ajv-formats=${ajvFormatsVersion}`,
  );
}

const schemaDirectory = __dirname;
const schemas = fs
  .readdirSync(schemaDirectory)
  .filter((name) => name.endsWith(".schema.json"))
  .sort()
  .map((name) => ({
    name,
    schema: JSON.parse(
      fs.readFileSync(path.join(schemaDirectory, name), "utf8"),
    ),
  }));

const ajv = new Ajv2020({
  strict: true,
  allErrors: true,
  validateFormats: true,
});
addFormats(ajv);
for (const { schema } of schemas) {
  ajv.addSchema(schema);
}

function schemaId(name) {
  const entry = schemas.find(({ name: candidate }) => candidate === name);
  if (!entry) {
    throw new Error(`Schema not found: ${name}`);
  }
  return entry.schema.$id;
}

function validator(name, fragment = "") {
  const result = ajv.getSchema(`${schemaId(name)}${fragment}`);
  if (!result) {
    throw new Error(`Validator not found: ${name}${fragment}`);
  }
  return result;
}

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

let witnessCount = 0;
function expectValidation(label, validate, instance, expected) {
  const observed = validate(instance);
  if (observed !== expected) {
    const detail = JSON.stringify(validate.errors || [], null, 2);
    throw new Error(
      `${label}: expected ${expected}, observed ${observed}\n${detail}`,
    );
  }
  witnessCount += 1;
  console.log(`WITNESS_OK ${label} observed=${observed}`);
}

const strictCompileTargets = [
  "certification_trust_anchor.v1.schema.json",
  "sut_decision.v1.schema.json",
  "evaluation_isolation_binding.v1.schema.json",
  "python_executable_binding.v1.schema.json",
  "runner_execution_record.v1.schema.json",
  "evaluation_runner_output.v1.schema.json",
  "evaluation_runner_contract.v1.schema.json",
  "evaluation_runner_input.v1.schema.json",
];

for (const name of strictCompileTargets) {
  validator(name);
  console.log(`STRICT_OK ${name}`);
}

const zeroHash = "0".repeat(64);
const zeroContentId = `sha256:${zeroHash}`;
const executionId = "018f0000-0000-7000-8000-000000000000";
const schemaBase =
  "https://raw.githubusercontent.com/rain-123-bow/aegis/main/schemas/aegis/v2";

const sutDecision = {
  schema_version: "SutDecision.v1",
  outcome: "ACCEPT",
  decision: null,
  reason_ids: ["REASON.OK"],
  assertion_ids: ["ASSERT.OK"],
  sut_decision_sha256: zeroHash,
};

const unverifiedIsolation = {
  schema_version: "EvaluationIsolationBinding.v1",
  binding_id: zeroContentId,
  evaluation_execution_id: executionId,
  runner_contract_id: zeroContentId,
  isolation_policy_sha256: zeroHash,
  state: "UNVERIFIED_ISOLATION",
  execution_authorized: false,
  backend: null,
  certification: null,
  mounts: [],
  deny_evidence: [],
  network_evidence: null,
  failure_reasons: ["NO_CERTIFIED_BACKEND"],
  checked_at_utc: "2026-07-27T00:00:00Z",
};

const preSpawnBlock = {
  spawn_attempted: false,
  comparison_performed: false,
  pass_eligible: false,
  reason_ids: ["REASON.NO-BACKEND"],
  evidence_ids: [zeroContentId],
};

const runnerOutputBase = {
  schema_version: "EvaluationRunnerOutput.v1",
  evaluation_execution_id: executionId,
  runner_contract_id: zeroContentId,
  case_id: "CASE.ONE",
  input_binding_id: "INPUT.ONE",
  runner_input_jcs_sha256: zeroHash,
  runner_output_sha256: zeroHash,
};

const blockedIsolationOutput = {
  ...runnerOutputBase,
  runner_state: "BLOCKED_UNVERIFIED_ISOLATION",
  isolation_binding: unverifiedIsolation,
  pre_spawn_block: preSpawnBlock,
};

const blockedContractOutput = {
  ...runnerOutputBase,
  runner_state: "BLOCKED_INVALID_RUNNER_CONTRACT",
  pre_spawn_block: preSpawnBlock,
};

const executableBindingPolicy = {
  schema_version: "PythonExecutableBindingPolicy.v1",
  runtime_binding_schema_id: `${schemaBase}/python_executable_binding.v1.schema.json`,
  source: "ISOLATED_VENV_CURRENT_PROCESS_SYS_EXECUTABLE",
  required_python_specifier: "==3.13.*",
  required_python_implementation: "CPython",
  supported_platform_profile: {
    operating_system: "Windows",
    sys_platform: "win32",
    machine: "AMD64",
    python_implementation: "CPython",
    python_major_minor: "3.13",
    wheel_platform_tag: "win_amd64",
  },
  required_distributions: [
    { name: "jsonschema", version: "4.26.0" },
    { name: "langgraph", version: "1.2.9" },
    { name: "langgraph-checkpoint-sqlite", version: "3.1.0" },
    { name: "rfc8785", version: "0.1.4" },
  ],
  dependency_source: "FROZEN_PYPROJECT_AND_PLATFORM_LOCK",
  path_resolution: "OS_REALPATH_OF_CURRENT_SYS_EXECUTABLE",
  execute_resolved_realpath: true,
  hash_verification: "REHASH_EXACT_FILE_BEFORE_EACH_INVOCATION",
  version_verification: "MATCH_CURRENT_PROCESS_VERSION_BEFORE_EACH_INVOCATION",
  path_lookup: "FORBIDDEN",
  shell: "FORBIDDEN",
  binding_lifetime: "ONE_EVALUATION_EXECUTION",
  evidence_retention: "PERSIST_BINDING_AND_PER_INVOCATION_REVALIDATION",
};

const isolationPolicy = {
  schema_version: "EvaluationIsolationPolicy.v1",
  runtime_binding_schema_id: `${schemaBase}/evaluation_isolation_binding.v1.schema.json`,
  release_grade_backend_required: true,
  backend_certification_required: true,
  trust_anchor_schema_id: `${schemaBase}/certification_trust_anchor.v1.schema.json`,
  independently_preauthorized_trust_anchor_required: true,
  evaluator_or_sut_self_authorization: "FORBIDDEN",
  best_effort_fallback: "FORBIDDEN",
  working_directory: "ISOLATED_EXECUTION_ROOT",
  filesystem_rules: [
    { resource: "INSTALLED_VIRTUAL_ENVIRONMENT", access: "READ_EXECUTE" },
    { resource: "CURRENT_CASE_DECLARED_FIXTURES", access: "READ_ONLY" },
    { resource: "INVOCATION_OUTBOX", access: "WRITE_ONLY_CREATE_NEW" },
    { resource: "REPOSITORY_ROOT", access: "DENIED" },
    { resource: "EVALUATION_CORPUS", access: "DENIED" },
    { resource: "EXPECTED_DATA", access: "DENIED" },
    { resource: "REFERENCE_SOURCES", access: "DENIED" },
    { resource: "ALL_OTHER_FILESYSTEM", access: "DENIED" },
  ],
  network_access: "DENIED",
  unavailable_disposition: "BLOCK_CASE_AS_UNVERIFIED_ISOLATION",
  public_corpus_confidentiality_claim: "NONE_PUBLIC_CORPUS_IS_NOT_SECRET",
};

const sutContract = {
  entrypoint_id: "AEGIS.SUT",
  execution_kind: "DIRECT_ARGV",
  working_directory: "ISOLATED_EXECUTION_ROOT",
  argv_template: [
    "{PYTHON_EXECUTABLE}",
    "-I",
    "-X",
    "utf8",
    "-m",
    "aegis.sut",
    "{ENTRYPOINT_ID}",
  ],
  environment: [
    { name: "AEGIS_RUNNER_MODE", value: "FROZEN_EVALUATION" },
    { name: "LANGGRAPH_STRICT_MSGPACK", value: "true" },
  ],
  environment_inheritance: "NONE",
  input_projection: [
    "/subject",
    "/context_objects",
    "/fixture_refs",
    "/mutation",
    "/observed_state",
  ],
  stdin_mode: "SUT_INPUT_PROJECTION_JCS_BYTES",
  network_access: "DENIED",
  timeout_ms: 1000,
};

const runnerContract = {
  schema_version: "EvaluationRunnerContract.v1",
  runner_contract_id: zeroContentId,
  canonicalization: "JCS-RFC8785",
  runner_version: "1.0.0",
  runner_input_schema_id: `${schemaBase}/evaluation_runner_input.v1.schema.json`,
  sut_output_schema_id: `${schemaBase}/sut_decision.v1.schema.json`,
  runner_output_schema_id: `${schemaBase}/evaluation_runner_output.v1.schema.json`,
  runner_execution_record_schema_id: `${schemaBase}/runner_execution_record.v1.schema.json`,
  executable_binding_policy: executableBindingPolicy,
  isolation_policy: isolationPolicy,
  fixture_mount: {
    source: "STATIC_CATALOG",
    catalog_id: zeroContentId,
    catalog_schema_id: `${schemaBase}/evaluation_fixture_catalog.v1.schema.json`,
    catalog_repository_path: "evaluation/fixtures/catalog.json",
    catalog_sha256: zeroHash,
    logical_runtime_root: "C:\\aegis\\fixtures",
    materialization: "COPY_EXACT_GIT_BLOB_BYTES",
    access_mode: "READ_ONLY",
  },
  input_bindings: [
    {
      input_binding_id: "INPUT.ONE",
      input_schema_id: "VERDICT.INPUT",
      subject_schema: {
        schema_id: "https://example.invalid/schema.json",
        json_pointer: "",
      },
      sut: sutContract,
      sut_output_schema: {
        schema_id: `${schemaBase}/sut_decision.v1.schema.json`,
        json_pointer: "",
      },
      runner_output_schema: {
        schema_id: `${schemaBase}/evaluation_runner_output.v1.schema.json`,
        json_pointer: "",
      },
      comparator: {
        comparator_id: "COMPARE.EXACT",
        kind: "SUT_DECISION_SHA256_EXACT",
        spec_sha256: zeroHash,
        observed_source: "EVALUATION_RUNNER_OUTPUT.SUT_DECISION",
        expected_source: "EVALUATION_CASE.EXPECTED",
        hash_member: "sut_decision_sha256",
        required_runner_state: "SUT_DECISION_READY",
        exact_array_order: true,
        exact_reason_order: true,
      },
      oracle: {
        expected_source: "OUTER_CASE_EXPECTED_ONLY",
        sut_input_excludes_expected: true,
        state_oracle: "NONE",
        side_effect_oracle: "NONE",
        event_oracle: "NONE",
      },
    },
  ],
};

const validateDecision = validator("sut_decision.v1.schema.json");
const validateIsolation = validator("evaluation_isolation_binding.v1.schema.json");
const validateRunnerOutput = validator("evaluation_runner_output.v1.schema.json");
const validateTrustAnchor = validator(
  "certification_trust_anchor.v1.schema.json",
);
const validateRunnerContract = validator(
  "evaluation_runner_contract.v1.schema.json",
);

expectValidation(
  "boundary.valid-sut-decision",
  validateDecision,
  sutDecision,
  true,
);
expectValidation(
  "boundary.sut-decision-rejects-case-id",
  validateDecision,
  { ...sutDecision, case_id: "CASE.ONE" },
  false,
);
expectValidation(
  "boundary.unverified-isolation-is-recordable",
  validateIsolation,
  unverifiedIsolation,
  true,
);
expectValidation(
  "boundary.unverified-isolation-cannot-authorize",
  validateIsolation,
  { ...unverifiedIsolation, execution_authorized: true },
  false,
);
expectValidation(
  "boundary.blocked-isolation-output",
  validateRunnerOutput,
  blockedIsolationOutput,
  true,
);
expectValidation(
  "boundary.blocked-output-rejects-decision-injection",
  validateRunnerOutput,
  { ...blockedIsolationOutput, sut_decision: sutDecision },
  false,
);
expectValidation(
  "boundary.invalid-contract-pre-spawn-output",
  validateRunnerOutput,
  blockedContractOutput,
  true,
);
expectValidation(
  "boundary.pre-spawn-output-rejects-execution-record",
  validateRunnerOutput,
  { ...blockedContractOutput, execution_record: {} },
  false,
);
expectValidation(
  "boundary.incomplete-trust-anchor-is-rejected",
  validateTrustAnchor,
  {
    schema_version: "CertificationTrustAnchor.v1",
    trust_anchor_id: zeroContentId,
  },
  false,
);
expectValidation(
  "boundary.runner-contract-static-shape",
  validateRunnerContract,
  runnerContract,
  true,
);
const propertyRunnerContract = clone(runnerContract);
propertyRunnerContract.fixture_mount = {
  source: "PROPERTY_INSTANCE_MATERIALIZATION",
  materialization_bundle_schema_id:
    `${schemaBase}/property_materialization_bundle.v1.schema.json`,
  materializer_algorithm_id: "MATERIALIZER.PROPERTY.TEST",
  materializer_source_manifest_entry_sha256: zeroHash,
  bundle_self_hash_member: "bundle_sha256",
  bundle_self_hash_rule:
    "sha256:JCS(PropertyMaterializationBundle object with bundle_sha256 omitted; every other member retained)",
  bundle_fixture_array_pointer: "/sut_materialized_fixtures",
  bundle_fixture_set_hash_member: "sut_materialized_fixtures_jcs_sha256",
  logical_runtime_root: "C:\\aegis\\fixtures",
  materialization: "DECODE_VERIFY_AND_COPY_BUNDLE_FIXTURES_ONLY",
  access_mode: "READ_ONLY",
  envelope_mount: "FORBIDDEN",
  expected_store_mount: "FORBIDDEN",
};
propertyRunnerContract.input_bindings[0].comparator.expected_source =
  "PROPERTY_EXPECTED_RECORD.EXPECTED";
propertyRunnerContract.input_bindings[0].oracle.expected_source =
  "PROPERTY_EXPECTED_RECORD_ONLY";
expectValidation(
  "boundary.runner-contract-property-materialization-shape",
  validateRunnerContract,
  propertyRunnerContract,
  true,
);
const mixedFixtureSourceContract = clone(propertyRunnerContract);
mixedFixtureSourceContract.fixture_mount.catalog_id = zeroContentId;
expectValidation(
  "boundary.runner-contract-rejects-mixed-fixture-sources",
  validateRunnerContract,
  mixedFixtureSourceContract,
  false,
);
const repositoryCwdContract = clone(runnerContract);
repositoryCwdContract.input_bindings[0].sut.working_directory =
  "REPOSITORY_ROOT";
expectValidation(
  "boundary.runner-contract-rejects-repository-cwd",
  validateRunnerContract,
  repositoryCwdContract,
  false,
);
const pythonPathContract = clone(runnerContract);
pythonPathContract.input_bindings[0].sut.environment.push({
  name: "PYTHONPATH",
  value: "C:\\repo",
});
expectValidation(
  "boundary.runner-contract-rejects-pythonpath",
  validateRunnerContract,
  pythonPathContract,
  false,
);

const moduleTuples = [
  ["aegis", "aegis-quality-kernel", "0.2.0a0"],
  ["jsonschema", "jsonschema", "4.26.0"],
  ["langgraph.graph", "langgraph", "1.2.9"],
  [
    "langgraph.checkpoint.sqlite",
    "langgraph-checkpoint-sqlite",
    "3.1.0",
  ],
  ["rfc8785", "rfc8785", "0.1.4"],
  ["xxhash", "xxhash", "3.8.1"],
];

const moduleOrigins = moduleTuples.map(
  ([moduleName, distributionName, distributionVersion], index) => ({
    module_name: moduleName,
    distribution_name: distributionName,
    distribution_version: distributionVersion,
    origin_path: `C:\\venv\\Lib\\site-packages\\module${index}.py`,
    origin_byte_size: 1,
    origin_raw_sha256: zeroHash,
    origin_under_environment_root: true,
    origin_outside_repository: true,
    file_kind: "REGULAR_FILE",
  }),
);

const platformProfile = {
  operating_system: "Windows",
  sys_platform: "win32",
  machine: "AMD64",
  python_implementation: "CPython",
  python_major_minor: "3.13",
  wheel_platform_tag: "win_amd64",
};

const pythonBinding = {
  schema_version: "PythonExecutableBinding.v1",
  binding_id: zeroContentId,
  evaluation_execution_id: executionId,
  source: "ISOLATED_VENV_CURRENT_PROCESS_SYS_EXECUTABLE",
  reported_sys_executable: "C:\\venv\\Scripts\\python.exe",
  resolved_absolute_realpath: "C:\\venv\\Scripts\\python.exe",
  byte_size: 1,
  raw_sha256: zeroHash,
  python_version: "3.13.13",
  python_implementation: "CPython",
  abi_cache_tag: "cpython-313",
  platform_profile: platformProfile,
  dependency_lock: {
    format: "PEP-751",
    repository_path: "pylock.windows-py313.toml",
    byte_size: 1,
    raw_sha256: zeroHash,
  },
  required_distributions: executableBindingPolicy.required_distributions,
  installed_distribution_snapshot_id: zeroContentId,
  virtual_environment: {
    kind: "FRESH_REPOSITORY_EXTERNAL_VENV",
    environment_root: "C:\\venv",
    repository_root: "C:\\repo\\aegis",
    environment_root_outside_repository: true,
    sys_prefix: "C:\\venv",
    sys_base_prefix: "C:\\Python313",
    is_virtual_environment: true,
    pyvenv_cfg_path: "C:\\venv\\pyvenv.cfg",
    pyvenv_cfg_byte_size: 1,
    pyvenv_cfg_raw_sha256: zeroHash,
    required_invocation_flags: ["-I", "-X", "utf8"],
    user_site_enabled: false,
    pythonpath_present: false,
    sitecustomize_state: "ABSENT_IN_FROZEN_ENVIRONMENT",
  },
  project_wheel: {
    distribution_name: "aegis-quality-kernel",
    distribution_version: "0.2.0a0",
    wheel_path: "C:\\wheels\\aegis.whl",
    byte_size: 1,
    raw_sha256: zeroHash,
    source_snapshot_id: zeroContentId,
    installed_into_environment: true,
  },
  module_origins: moduleOrigins,
  sys_path_snapshot_id: zeroContentId,
  import_isolation_result: "EXACT_MATCH",
  path_resolution: "OS_REALPATH_OF_CURRENT_SYS_EXECUTABLE",
  execute_resolved_realpath: true,
  path_lookup: "FORBIDDEN",
  shell: "FORBIDDEN",
  acquisition_event_id: executionId,
  captured_at_utc: "2026-07-27T00:00:00Z",
};

const runtimeRevalidation = {
  binding_id: zeroContentId,
  revalidated_at_utc: "2026-07-27T00:00:00Z",
  resolved_absolute_realpath: "C:\\venv\\Scripts\\python.exe",
  byte_size: 1,
  raw_sha256: zeroHash,
  python_version: "3.13.13",
  python_implementation: "CPython",
  abi_cache_tag: "cpython-313",
  platform_profile: platformProfile,
  dependency_lock_repository_path: "pylock.windows-py313.toml",
  dependency_lock_byte_size: 1,
  dependency_lock_raw_sha256: zeroHash,
  installed_distribution_snapshot_id: zeroContentId,
  virtual_environment_root: "C:\\venv",
  pyvenv_cfg_raw_sha256: zeroHash,
  project_wheel_raw_sha256: zeroHash,
  project_wheel_source_snapshot_id: zeroContentId,
  sys_path_snapshot_id: zeroContentId,
  module_origins_jcs_sha256: zeroHash,
  import_isolation_result: "EXACT_MATCH",
  result: "EXACT_MATCH",
};

const validatePythonBinding = validator(
  "python_executable_binding.v1.schema.json",
);
const validateRuntimeRevalidation = validator(
  "runner_execution_record.v1.schema.json",
  "#/$defs/runtimeRevalidation",
);

expectValidation(
  "python-binding.exact-schema-fixture",
  validatePythonBinding,
  pythonBinding,
  true,
);
expectValidation(
  "python-binding.rejects-conflicting-implementation",
  validatePythonBinding,
  { ...pythonBinding, python_implementation: "PyPy" },
  false,
);
const reorderedOrigins = clone(pythonBinding);
[reorderedOrigins.module_origins[0], reorderedOrigins.module_origins[1]] = [
  reorderedOrigins.module_origins[1],
  reorderedOrigins.module_origins[0],
];
expectValidation(
  "python-binding.rejects-critical-module-reordering",
  validatePythonBinding,
  reorderedOrigins,
  false,
);
expectValidation(
  "python-binding.exact-runtime-revalidation-schema-fixture",
  validateRuntimeRevalidation,
  runtimeRevalidation,
  true,
);
expectValidation(
  "python-binding.rejects-runtime-version-drift",
  validateRuntimeRevalidation,
  { ...runtimeRevalidation, python_version: "3.12.9" },
  false,
);
expectValidation(
  "python-binding.rejects-runtime-abi-drift",
  validateRuntimeRevalidation,
  { ...runtimeRevalidation, abi_cache_tag: "cpython-312" },
  false,
);

console.log(
  `SCHEMA_WITNESSES_OK strict=${strictCompileTargets.length} witnesses=${witnessCount} runtime_pass_claim=false`,
);

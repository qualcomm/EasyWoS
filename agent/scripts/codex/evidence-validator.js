const fs = require("fs");
const path = require("path");
const {
  parseArgs,
  loadData,
  resolveExisting,
  sha256File,
} = require("./lib");

class EvidenceError extends Error {
  constructor(code, message, evidencePath = null) {
    super(message);
    this.name = "EvidenceError";
    this.code = code;
    this.path = evidencePath;
  }
}

function requireValue(condition, code, message, evidencePath = null) {
  if (!condition) throw new EvidenceError(code, message, evidencePath);
}

function validateMatcherEvidence(record, evidencePath = null, options = {}) {
  requireValue(record && record.matcher, "E_MATCHER_EVIDENCE_MISSING", "matcher metadata is missing", evidencePath);
  requireValue(Array.isArray(record.candidates), "E_MATCHER_CANDIDATES_MISSING", "matcher candidates are missing", evidencePath);
  const meta = record.matcher;
  for (const key of ["script", "script_sha256", "input", "input_sha256", "specs", "specs_sha256", "executed_at"]) {
    requireValue(meta[key], "E_MATCHER_PROVENANCE_MISSING", `matcher.${key} is required`, evidencePath);
  }
  if (options.checkFiles !== false) {
    for (const [fileKey, hashKey] of [["script", "script_sha256"], ["input", "input_sha256"], ["specs", "specs_sha256"]]) {
      requireValue(fs.existsSync(meta[fileKey]), "E_MATCHER_INPUT_MISSING", `${fileKey} file no longer exists: ${meta[fileKey]}`, evidencePath);
      requireValue(sha256File(meta[fileKey]) === meta[hashKey], "E_MATCHER_HASH_MISMATCH", `${fileKey} hash no longer matches matcher evidence`, evidencePath);
    }
  }
  for (const item of record.candidates) {
    requireValue(item.porting_item_id, "E_MATCHER_ITEM_ID_MISSING", "candidate item id is missing", evidencePath);
    requireValue(Array.isArray(item.matches), "E_MATCHER_ITEM_INVALID", `matches missing for ${item.porting_item_id}`, evidencePath);
    for (const match of item.matches) {
      requireValue(match.spec_id !== undefined, "E_MATCHER_SPEC_ID_MISSING", "matched spec id is missing", evidencePath);
      requireValue(Array.isArray(match.evidence) && match.evidence.length > 0, "E_MATCHER_RULE_EVIDENCE_MISSING", `spec ${match.spec_id} has no rule evidence`, evidencePath);
    }
  }
  return true;
}

function validateCommandEvidence(record, expectedStage = null, evidencePath = null) {
  requireValue(record && record.schema_version === 1, "E_COMMAND_SCHEMA", "command evidence schema_version must be 1", evidencePath);
  requireValue(record.stage, "E_COMMAND_STAGE", "command evidence stage is required", evidencePath);
  if (expectedStage) requireValue(record.stage === expectedStage, "E_COMMAND_STAGE", `expected stage ${expectedStage}, got ${record.stage}`, evidencePath);
  requireValue(typeof record.command === "string" && record.command.length > 0, "E_COMMAND_MISSING", "command is required", evidencePath);
  requireValue(record.exit_code === 0, "E_COMMAND_FAILED", `${record.stage} exit code is ${record.exit_code}`, evidencePath);
  if (/^test-/.test(record.stage)) {
    requireValue(Number.isInteger(record.tests_discovered) && record.tests_discovered > 0, "E_ZERO_TESTS", `${record.stage} discovered zero tests`, evidencePath);
    requireValue(record.tests_failed === 0, "E_TESTS_FAILED", `${record.stage} has failed tests`, evidencePath);
  }
  requireValue(record.source_tree_fingerprint, "E_SOURCE_FINGERPRINT_MISSING", `${record.stage} has no source fingerprint`, evidencePath);
  return true;
}

function validateNegativeControl(record, evidencePath = null) {
  requireValue(record && record.schema_version === 1, "E_NEGATIVE_CONTROL_SCHEMA", "negative-control schema_version must be 1", evidencePath);
  requireValue(record.perturbation && String(record.perturbation).trim(), "E_NEGATIVE_CONTROL_PERTURBATION", "negative-control perturbation is missing", evidencePath);
  requireValue(Number.isInteger(record.red_exit_code) && record.red_exit_code !== 0, "E_NEGATIVE_CONTROL_NOT_RED", "negative control did not fail", evidencePath);
  requireValue(record.restored === true, "E_NEGATIVE_CONTROL_NOT_RESTORED", "negative-control perturbation was not restored", evidencePath);
  requireValue(record.restored_green_exit_code === 0, "E_NEGATIVE_CONTROL_NOT_GREEN", "restored test did not return green", evidencePath);
  requireValue(Array.isArray(record.fixtures) && record.fixtures.length > 0, "E_NEGATIVE_CONTROL_FIXTURES", "negative control has no fixtures", evidencePath);
  requireValue(record.verifier_session_id, "E_NEGATIVE_CONTROL_SESSION", "negative control must record the verifier session", evidencePath);
  return true;
}

function validateIndependentVerifier(record, evidencePath = null) {
  requireValue(record && record.schema_version === 1, "E_VERIFIER_SCHEMA", "verifier schema_version must be 1", evidencePath);
  requireValue(record.producer_session_id && record.verifier_session_id, "E_VERIFIER_SESSION_MISSING", "producer and verifier sessions are required", evidencePath);
  requireValue(record.producer_session_id !== record.verifier_session_id, "E_VERIFIER_NOT_INDEPENDENT", "producer and verifier sessions must differ", evidencePath);
  requireValue(record.producer_patch_sha256 && record.verifier_observed_patch_sha256, "E_VERIFIER_PATCH_MISSING", "producer and verifier patch hashes are required", evidencePath);
  requireValue(record.producer_patch_sha256 === record.verifier_observed_patch_sha256, "E_VERIFIER_PATCH_MISMATCH", "verifier observed a different patch", evidencePath);
  requireValue(record.verdict === "VERIFIED", "E_VERIFIER_REFUTED", `verifier verdict is ${record.verdict || "missing"}`, evidencePath);
  return true;
}

function validatePerformanceTerminal(record, baseDir, evidencePath = null) {
  requireValue(record && record.schema_version === 1, "E_PERF_SCHEMA", "performance schema_version must be 1", evidencePath);
  const allowed = new Set(["CONVERGED", "STALLED", "SKIPPED_BY_USER"]);
  requireValue(allowed.has(record.status), "E_PERF_NOT_TERMINAL", `performance status ${record.status || "missing"} is not archivable`, evidencePath);
  if (record.status === "SKIPPED_BY_USER") {
    requireValue(record.user_explicit_no_profile === true, "E_PERF_SKIP_NOT_EXPLICIT", "SKIPPED_BY_USER requires explicit --no-profile evidence", evidencePath);
    return true;
  }
  requireValue(record.profiler_ran === true, "E_PERF_NOT_RUN", `${record.status} requires a successfully executed profiler`, evidencePath);
  for (const key of ["baseline_etl", "baseline_speedscope", "perf_progress"]) {
    const file = resolveExisting(baseDir, record[key], `performance ${key}`);
    if (record.hashes && record.hashes[key]) {
      requireValue(sha256File(file) === record.hashes[key], "E_PERF_HASH_MISMATCH", `${key} hash mismatch`, evidencePath);
    }
  }
  if (record.status === "STALLED") {
    requireValue(record.blocker && String(record.blocker).trim(), "E_PERF_STALL_BLOCKER", "STALLED requires a blocker", evidencePath);
  }
  if (record.optimization_performed === true || Number(record.accepted_optimizations || 0) > 0) {
    for (const key of ["optimized_etl", "optimized_speedscope", "paired_benchmark", "checksums"]) {
      const file = resolveExisting(baseDir, record[key], `performance ${key}`);
      if (record.hashes && record.hashes[key]) {
        requireValue(sha256File(file) === record.hashes[key], "E_PERF_HASH_MISMATCH", `${key} hash mismatch`, evidencePath);
      }
    }
    requireValue(record.work_checksums_match === true, "E_PERF_WORK_MISMATCH", "optimized and baseline workloads do not have matching checksums", evidencePath);
  }
  return true;
}

function matchedSpecIds(matcher, itemId) {
  const item = matcher.candidates.find((entry) => entry.porting_item_id === itemId);
  return new Set((item && item.matches || []).map((match) => String(match.spec_id)));
}

function validateDispatchChain(request, result, matcher, evidencePath = null) {
  requireValue(request && request.schema_version === 1, "E_DISPATCH_REQUEST_SCHEMA", "dispatch request schema_version must be 1", evidencePath);
  requireValue(result && result.schema_version === 1, "E_DISPATCH_RESULT_SCHEMA", "dispatch result schema_version must be 1", evidencePath);
  requireValue(request.dispatch_id === result.dispatch_id, "E_DISPATCH_ID_MISMATCH", "dispatch request/result ids differ", evidencePath);
  requireValue(result.request_sha256, "E_DISPATCH_REQUEST_HASH_MISSING", "dispatch result has no request hash", evidencePath);
  if (request.__file) requireValue(sha256File(request.__file) === result.request_sha256, "E_DISPATCH_REQUEST_HASH_MISMATCH", "dispatch request changed after result recording", evidencePath);
  requireValue(result.status === "APPLIED", "E_DISPATCH_NOT_APPLIED", `dispatch ${request.dispatch_id} status is ${result.status}`, evidencePath);
  requireValue(result.producer && result.producer.session_id, "E_DISPATCH_PRODUCER_MISSING", "dispatch producer session is missing", evidencePath);
  for (const [fileKey, hashKey] of [["source_matched_yaml", "source_matched_yaml_sha256"], ["matcher_evidence", "matcher_evidence_sha256"], ["combined_specs", "combined_specs_sha256"]]) {
    if (!request[fileKey]) continue;
    requireValue(fs.existsSync(request[fileKey]), "E_DISPATCH_INPUT_MISSING", `${fileKey} no longer exists`, evidencePath);
    requireValue(sha256File(request[fileKey]) === request[hashKey], "E_DISPATCH_INPUT_HASH_MISMATCH", `${fileKey} changed after dispatch preparation`, evidencePath);
  }
  if (request.matcher_evidence_sha256) {
    requireValue(request.matcher_evidence_sha256 === sha256File(request.matcher_evidence), "E_DISPATCH_MATCHER_HASH_MISMATCH", "dispatch matcher evidence hash mismatch", evidencePath);
  }
  if (request.combined_specs_sha256) {
    requireValue(matcher.matcher.specs_sha256 === request.combined_specs_sha256, "E_DISPATCH_COMBINED_SPEC_MISMATCH", "dispatch used a different combined spec collection than the matcher", evidencePath);
  }
  if (request.mode === "spec-driven") {
    const matched = matchedSpecIds(matcher, request.porting_item_id);
    const item = matcher.candidates.find((entry) => entry.porting_item_id === request.porting_item_id);
    const evidenceIds = new Set((item && item.matches || []).flatMap((match) => (match.evidence || []).map((entry) => entry.evidence_id)));
    for (const specId of request.port_spec_ids || []) {
      requireValue(matched.has(String(specId)), "E_DISPATCH_SPEC_NOT_MATCHED", `dispatch spec ${specId} has no matcher evidence for ${request.porting_item_id}`, evidencePath);
    }
    for (const evidenceId of request.matched_evidence_ids || []) {
      requireValue(evidenceIds.has(evidenceId), "E_DISPATCH_EVIDENCE_NOT_MATCHED", `dispatch evidence ${evidenceId} is absent from matcher output`, evidencePath);
    }
  }
  return true;
}

function validateSourceFingerprint(records) {
  const fingerprints = new Set(records.map((record) => record.source_tree_fingerprint).filter(Boolean));
  requireValue(fingerprints.size === 1, "E_SOURCE_FINGERPRINT_MISMATCH", "build/test evidence was produced from different source trees");
  return true;
}

function validateByType(type, record, file, args) {
  if (type === "matcher") return validateMatcherEvidence(record, file, { checkFiles: !args.no_file_check });
  if (type === "command") return validateCommandEvidence(record, args.stage || null, file);
  if (type === "negative-control") return validateNegativeControl(record, file);
  if (type === "verifier") return validateIndependentVerifier(record, file);
  if (type === "performance") return validatePerformanceTerminal(record, args.base || path.dirname(file), file);
  throw new EvidenceError("E_VALIDATOR_TYPE", `unsupported evidence type: ${type}`, file);
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  try {
    const file = resolveExisting(process.cwd(), args.file, "evidence file");
    validateByType(args.type, loadData(file), file, args);
    console.log(JSON.stringify({ ok: true, type: args.type, file }));
  } catch (error) {
    const code = error.code || "E_VALIDATION";
    console.error(JSON.stringify({ ok: false, code, message: error.message, path: error.path || args.file || null }));
    process.exitCode = 1;
  }
}

if (require.main === module) main();

module.exports = {
  EvidenceError,
  validateMatcherEvidence,
  validateCommandEvidence,
  validateNegativeControl,
  validateIndependentVerifier,
  validatePerformanceTerminal,
  validateDispatchChain,
  validateSourceFingerprint,
};

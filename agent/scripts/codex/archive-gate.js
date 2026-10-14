const fs = require("fs");
const path = require("path");
const { execSync } = require("child_process");
const {
  parseArgs,
  loadData,
  writeYaml,
  resolveExisting,
  sha256File,
  loadState,
  saveState,
  now,
} = require("./lib");
const validator = require("./evidence-validator");

function evidenceFile(changeDir, state, key) {
  const entry = state.evidence && state.evidence[key];
  if (!entry) throw new validator.EvidenceError("E_EVIDENCE_MISSING", `lifecycle evidence '${key}' is missing`);
  const file = resolveExisting(changeDir, entry.path, key);
  if (entry.sha256 && sha256File(file) !== entry.sha256) {
    throw new validator.EvidenceError("E_EVIDENCE_HASH_MISMATCH", `${key} evidence changed after acceptance`, file);
  }
  return file;
}

function validateDispatchManifest(changeDir, manifestFile, matcher) {
  const manifest = loadData(manifestFile);
  if (!manifest || manifest.schema_version !== 1 || !Array.isArray(manifest.entries) || manifest.entries.length === 0) {
    throw new validator.EvidenceError("E_DISPATCH_MANIFEST", "dispatch manifest is invalid", manifestFile);
  }
  for (const entry of manifest.entries) {
    const requestFile = resolveExisting(path.dirname(manifestFile), entry.request, "dispatch request");
    const resultFile = resolveExisting(path.dirname(manifestFile), entry.result, "dispatch result");
    if (entry.request_sha256 !== sha256File(requestFile) || entry.result_sha256 !== sha256File(resultFile)) {
      throw new validator.EvidenceError("E_DISPATCH_HASH_MISMATCH", `dispatch files changed for ${entry.dispatch_id}`, manifestFile);
    }
    const request = loadData(requestFile);
    request.__file = requestFile;
    validator.validateDispatchChain(request, loadData(resultFile), matcher, requestFile);
  }
  return manifest;
}

function renderReport(checks, ok) {
  const lines = [
    "# Archive Gate Report",
    "",
    `- Result: ${ok ? "PASS" : "FAIL"}`,
    `- Generated: ${now()}`,
    "",
    "| Check | Result | Evidence |",
    "|---|---|---|",
  ];
  for (const check of checks) lines.push(`| ${check.name} | ${check.ok ? "PASS" : `FAIL (${check.code})`} | ${check.detail || ""} |`);
  lines.push("");
  return `${lines.join("\n")}\n`;
}

function runGate(changeDir, args = {}) {
  const state = loadState(changeDir);
  const checks = [];
  const check = (name, fn) => {
    try {
      const detail = fn();
      checks.push({ name, ok: true, detail: detail || "validated" });
    } catch (error) {
      checks.push({ name, ok: false, code: error.code || "E_ARCHIVE_GATE", detail: error.message });
    }
  };

  check("lifecycle-state", () => {
    if (state.schema_version !== 1) throw new validator.EvidenceError("E_LIFECYCLE_SCHEMA", "lifecycle schema_version must be 1");
    if (!["VERIFY", "ARCHIVE_READY"].includes(state.phase)) throw new validator.EvidenceError("E_LIFECYCLE_PHASE", `archive gate requires VERIFY, got ${state.phase}`);
    return state.phase;
  });

  let matcher;
  check("matcher", () => {
    const file = evidenceFile(changeDir, state, "matcher");
    matcher = loadData(file);
    validator.validateMatcherEvidence(matcher, file);
    return file;
  });
  check("dispatch", () => validateDispatchManifest(changeDir, evidenceFile(changeDir, state, "dispatch_manifest"), matcher) && "all dispatch records validated");

  const commandRecords = [];
  for (const [key, stage] of [["build_x64", "build-x64"], ["build_arm64", "build-arm64"], ["test_x64", "test-x64"], ["test_arm64", "test-arm64"]]) {
    check(key, () => {
      const file = evidenceFile(changeDir, state, key);
      const record = loadData(file);
      validator.validateCommandEvidence(record, stage, file);
      commandRecords.push(record);
      return file;
    });
  }
  check("source-fingerprint", () => validator.validateSourceFingerprint(commandRecords) && commandRecords[0].source_tree_fingerprint);
  let negativeControl;
  check("negative-control", () => {
    const file = evidenceFile(changeDir, state, "negative_control");
    negativeControl = loadData(file);
    validator.validateNegativeControl(negativeControl, file);
    return file;
  });
  check("performance", () => {
    const file = evidenceFile(changeDir, state, "performance");
    const record = loadData(file);
    validator.validatePerformanceTerminal(record, changeDir, file);
    return `${record.status}: ${file}`;
  });
  check("independent-verifier", () => {
    const file = evidenceFile(changeDir, state, "verifier");
    const verifier = loadData(file);
    validator.validateIndependentVerifier(verifier, file);
    if (negativeControl && negativeControl.verifier_session_id !== verifier.verifier_session_id) {
      throw new validator.EvidenceError("E_NEGATIVE_CONTROL_WRONG_VERIFIER", "negative control was not run by the recorded independent verifier", file);
    }
    return file;
  });
  check("openspec-strict", () => {
    const command = args.openspec_command || "openspec validate --strict";
    execSync(command, { cwd: args.project ? path.resolve(args.project) : state.project_root, stdio: "pipe", encoding: "utf8" });
    return command;
  });

  const ok = checks.every((entry) => entry.ok);
  const report = path.join(changeDir, "ARCHIVE-GATE-REPORT.md");
  fs.writeFileSync(report, renderReport(checks, ok), "utf8");
  if (!ok) {
    const first = checks.find((entry) => !entry.ok);
    const error = new validator.EvidenceError(first.code, first.detail, report);
    error.checks = checks;
    throw error;
  }
  if (state.phase === "VERIFY") {
    state.phase = "ARCHIVE_READY";
    state.run_status = "ACTIVE";
    state.history = state.history || [];
    state.history.push({ event: "ARCHIVE_GATE_PASS", from: "VERIFY", to: "ARCHIVE_READY", at: now(), report: "ARCHIVE-GATE-REPORT.md", sha256: sha256File(report) });
    saveState(changeDir, state);
  }
  return { ok: true, report, checks };
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  try {
    const changeDir = path.resolve(args.change);
    console.log(JSON.stringify(runGate(changeDir, args), null, 2));
  } catch (error) {
    console.error(JSON.stringify({ ok: false, code: error.code || "E_ARCHIVE_GATE", message: error.message, report: error.path || null }, null, 2));
    process.exitCode = 1;
  }
}

if (require.main === module) main();

module.exports = { runGate, validateDispatchManifest };

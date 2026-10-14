const fs = require("fs");
const path = require("path");
const {
  parseArgs,
  now,
  loadData,
  resolveExisting,
  relativeTo,
  sha256File,
  statePath,
  loadState,
  saveState,
  writeYaml,
} = require("./lib");
const validator = require("./evidence-validator");

const PHASES = [
  "PREFLIGHT", "SCAN", "MATCH", "REFINE", "DISPATCH", "INTEGRATE",
  "BUILD", "TEST", "NEGATIVE_CONTROL", "PROFILE", "VERIFY",
  "ARCHIVE_READY", "ARCHIVED",
];

const REQUIREMENTS = {
  PREFLIGHT: ["preflight"],
  SCAN: ["scan_report"],
  MATCH: ["matcher"],
  REFINE: ["matched_yaml"],
  DISPATCH: ["dispatch_manifest"],
  INTEGRATE: ["integration"],
  BUILD: ["build_x64", "build_arm64"],
  TEST: ["test_x64", "test_arm64"],
  NEGATIVE_CONTROL: ["negative_control"],
  PROFILE: ["performance"],
  VERIFY: ["verifier"],
};

const KEY_PHASE = Object.fromEntries(Object.entries(REQUIREMENTS).flatMap(
  ([phase, keys]) => keys.map((key) => [key, phase])
));

function appendHistory(state, event) {
  state.history = state.history || [];
  state.history.push({ at: now(), ...event });
}

function validateEvidence(key, record, file, changeDir) {
  if (key === "matcher") return validator.validateMatcherEvidence(record, file);
  if (key === "build_x64") return validator.validateCommandEvidence(record, "build-x64", file);
  if (key === "build_arm64") return validator.validateCommandEvidence(record, "build-arm64", file);
  if (key === "test_x64") return validator.validateCommandEvidence(record, "test-x64", file);
  if (key === "test_arm64") return validator.validateCommandEvidence(record, "test-arm64", file);
  if (key === "negative_control") return validator.validateNegativeControl(record, file);
  if (key === "performance") return validator.validatePerformanceTerminal(record, changeDir, file);
  if (key === "verifier") return validator.validateIndependentVerifier(record, file);
  return true;
}

function init(changeDir, args) {
  const abs = path.resolve(changeDir);
  fs.mkdirSync(abs, { recursive: true });
  for (const dir of ["dispatch", "evidence", "perf"]) fs.mkdirSync(path.join(abs, dir), { recursive: true });
  const file = statePath(abs);
  if (fs.existsSync(file) && !args.force) throw new Error(`lifecycle state already exists: ${file}`);
  const state = {
    schema_version: 1,
    change_id: args.change_id || path.basename(abs),
    project_root: path.resolve(args.project),
    target: args.target || "arm64-windows",
    phase: "PREFLIGHT",
    run_status: "ACTIVE",
    created_at: now(),
    updated_at: now(),
    evidence: {},
    history: [],
  };
  appendHistory(state, { event: "INIT", to: "PREFLIGHT" });
  writeYaml(file, state);
  return state;
}

function phaseComplete(state, phase) {
  return (REQUIREMENTS[phase] || []).every((key) => state.evidence && state.evidence[key]);
}

function advance(state) {
  const index = PHASES.indexOf(state.phase);
  if (index < 0 || index >= PHASES.length - 1) return;
  const from = state.phase;
  state.phase = PHASES[index + 1];
  state.run_status = state.phase === "ARCHIVED" ? "COMPLETE" : "ACTIVE";
  appendHistory(state, { event: "ADVANCE", from, to: state.phase });
}

function submit(changeDir, args) {
  const state = loadState(changeDir);
  const phase = String(args.phase || "").toUpperCase();
  const key = args.key;
  if (state.phase !== phase) throw new Error(`current phase is ${state.phase}, not ${phase}`);
  if (KEY_PHASE[key] !== phase) throw new Error(`evidence key ${key} does not belong to phase ${phase}`);
  const file = resolveExisting(changeDir, args.evidence, "evidence");
  const record = loadData(file);
  validateEvidence(key, record, file, changeDir);
  state.evidence[key] = {
    path: relativeTo(changeDir, file),
    sha256: sha256File(file),
    accepted_at: now(),
  };
  appendHistory(state, { event: "EVIDENCE_ACCEPTED", phase, key, sha256: state.evidence[key].sha256 });
  // VERIFY is intentionally sticky: only archive-gate.js may move the state
  // to ARCHIVE_READY after checking the complete evidence graph.
  if (phaseComplete(state, phase) && phase !== "VERIFY") advance(state);
  saveState(changeDir, state);
  return state;
}

function invalidateFrom(changeDir, args) {
  const state = loadState(changeDir);
  const phase = String(args.phase || "").toUpperCase();
  const index = PHASES.indexOf(phase);
  if (index < 0 || index >= PHASES.indexOf("ARCHIVE_READY")) throw new Error(`invalid phase: ${phase}`);
  for (const [key, owner] of Object.entries(KEY_PHASE)) {
    if (PHASES.indexOf(owner) >= index) delete state.evidence[key];
  }
  const from = state.phase;
  state.phase = phase;
  state.run_status = "ACTIVE";
  appendHistory(state, { event: "INVALIDATE", from, to: phase, reason: args.reason || "upstream input changed" });
  saveState(changeDir, state);
  return state;
}

function retryCurrent(changeDir, args) {
  const state = loadState(changeDir);
  state.run_status = "ACTIVE";
  appendHistory(state, { event: "RETRY", phase: state.phase, reason: args.reason || null });
  saveState(changeDir, state);
  return state;
}

function archiveComplete(changeDir, args) {
  const state = loadState(changeDir);
  if (state.phase !== "ARCHIVE_READY") throw new Error(`archive gate has not passed; current phase is ${state.phase}`);
  const evidence = resolveExisting(changeDir, args.evidence, "archive evidence");
  state.evidence.archive = { path: relativeTo(changeDir, evidence), sha256: sha256File(evidence), accepted_at: now() };
  advance(state);
  saveState(changeDir, state);
  return state;
}

function nextAction(state) {
  return {
    phase: state.phase,
    run_status: state.run_status,
    required_evidence: REQUIREMENTS[state.phase] || [],
    accepted_evidence: Object.keys(state.evidence || {}),
  };
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  const command = args._[0];
  const changeDir = args.change && path.resolve(args.change);
  try {
    let result;
    if (command === "init") result = init(changeDir, args);
    else if (command === "next" || command === "status") result = nextAction(loadState(changeDir));
    else if (command === "submit") result = submit(changeDir, args);
    else if (command === "invalidate-from") result = invalidateFrom(changeDir, args);
    else if (command === "retry-current") result = retryCurrent(changeDir, args);
    else if (command === "archive-complete") result = archiveComplete(changeDir, args);
    else throw new Error("usage: lifecycle-driver.js <init|next|status|submit|invalidate-from|retry-current|archive-complete> --change <dir> ...");
    console.log(JSON.stringify(result, null, 2));
  } catch (error) {
    console.error(JSON.stringify({ ok: false, code: error.code || "E_LIFECYCLE", message: error.message }));
    process.exitCode = 1;
  }
}

if (require.main === module) main();

module.exports = { PHASES, REQUIREMENTS, init, submit, invalidateFrom, retryCurrent, archiveComplete, nextAction };

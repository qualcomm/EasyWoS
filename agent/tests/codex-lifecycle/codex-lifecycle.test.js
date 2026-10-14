const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const os = require("os");
const path = require("path");

const ROOT = path.resolve(__dirname, "../..");
const {
  writeJson,
  writeYaml,
  sha256File,
  loadData,
} = require(path.join(ROOT, "scripts/codex/lib"));
const lifecycle = require(path.join(ROOT, "scripts/codex/lifecycle-driver"));
const dispatcher = require(path.join(ROOT, "scripts/codex/dispatcher-adapter"));
const { runGate } = require(path.join(ROOT, "scripts/codex/archive-gate"));

function makeMatcher(dir) {
  const script = path.join(dir, "spec_matcher.js");
  const input = path.join(dir, "scan.yaml");
  const specs = path.join(dir, "combined.yaml");
  fs.writeFileSync(script, "// matcher fixture\n", "utf8");
  fs.writeFileSync(input, "schema: x64-to-arm64-porting\n", "utf8");
  fs.writeFileSync(specs, "specs: []\n", "utf8");
  return {
    matcher: {
      schema_version: 1,
      executed_at: new Date().toISOString(),
      script,
      script_sha256: sha256File(script),
      input,
      input_sha256: sha256File(input),
      specs,
      specs_sha256: sha256File(specs),
    },
    candidates: [{
      porting_item_id: "kernel",
      matches: [{
        spec_id: 86,
        spec_name: "no-movemask",
        rules_hit: 1,
        matched_rules: ["_mm_movemask_epi8"],
        evidence: [{ evidence_id: "match-kernel-86-1", spec_id: 86, file: "kernel.cpp", line: 4, scopes: ["intrinsic_call"], pattern: "_mm_movemask_epi8", excerpt: "_mm_movemask_epi8(v)" }],
      }],
    }],
  };
}

function addEvidence(state, changeDir, key, file) {
  state.evidence[key] = { path: path.relative(changeDir, file).replace(/\\/g, "/"), sha256: sha256File(file) };
}

function createCompleteChange() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "easywos-gate-"));
  const project = path.join(root, "project");
  const change = path.join(project, "openspec", "changes", "port-arm64");
  fs.mkdirSync(change, { recursive: true });
  fs.mkdirSync(path.join(change, "evidence"), { recursive: true });
  fs.mkdirSync(path.join(change, "dispatch"), { recursive: true });

  const matcherFile = path.join(change, "evidence", "matcher.json");
  writeJson(matcherFile, makeMatcher(root));

  const requestFile = path.join(change, "dispatch", "kernel-attempt-1.request.yaml");
  writeYaml(requestFile, {
    schema_version: 1,
    dispatch_id: "kernel-attempt-1",
    porting_item_id: "kernel",
    mode: "spec-driven",
    primary_leaf_skill: "intrinsics-x64-to-arm64",
    supplemental_leaf_skills: [],
    port_spec_ids: [86],
    matched_evidence_ids: ["match-kernel-86-1"],
    prepared_at: new Date().toISOString(),
  });
  const resultFile = path.join(change, "dispatch", "kernel-attempt-1.result.yaml");
  writeYaml(resultFile, {
    schema_version: 1,
    dispatch_id: "kernel-attempt-1",
    status: "APPLIED",
    request_sha256: sha256File(requestFile),
    producer: { harness: "codex", session_id: "producer-1" },
    patch_sha256: "patch-sha",
    recorded_at: new Date().toISOString(),
  });
  const manifestFile = path.join(change, "evidence", "dispatch-manifest.yaml");
  writeYaml(manifestFile, {
    schema_version: 1,
    entries: [{
      dispatch_id: "kernel-attempt-1",
      request: "../dispatch/kernel-attempt-1.request.yaml",
      request_sha256: sha256File(requestFile),
      result: "../dispatch/kernel-attempt-1.result.yaml",
      result_sha256: sha256File(resultFile),
    }],
  });

  const fingerprint = "source-tree-1";
  const commandFiles = {};
  for (const stage of ["build-x64", "build-arm64", "test-x64", "test-arm64"]) {
    const file = path.join(change, "evidence", `${stage}.json`);
    const record = { schema_version: 1, stage, command: `run ${stage}`, exit_code: 0, source_tree_fingerprint: fingerprint };
    if (stage.startsWith("test")) Object.assign(record, { tests_discovered: 10, tests_passed: 10, tests_failed: 0 });
    writeJson(file, record);
    commandFiles[stage] = file;
  }
  const negative = path.join(change, "evidence", "negative-control.json");
  writeJson(negative, { schema_version: 1, perturbation: "expected[0] ^= 0xff", red_exit_code: 1, restored: true, restored_green_exit_code: 0, fixtures: ["KernelTest.Basic"], verifier_session_id: "verifier-2" });
  const performance = path.join(change, "evidence", "performance.json");
  writeJson(performance, { schema_version: 1, status: "SKIPPED_BY_USER", user_explicit_no_profile: true });
  const verifier = path.join(change, "evidence", "verifier.json");
  writeJson(verifier, { schema_version: 1, producer_session_id: "producer-1", verifier_session_id: "verifier-2", producer_patch_sha256: "patch-sha", verifier_observed_patch_sha256: "patch-sha", verdict: "VERIFIED" });

  const state = {
    schema_version: 1,
    change_id: "port-arm64",
    project_root: project,
    target: "arm64-windows",
    phase: "VERIFY",
    run_status: "ACTIVE",
    evidence: {},
    history: [],
  };
  addEvidence(state, change, "matcher", matcherFile);
  addEvidence(state, change, "dispatch_manifest", manifestFile);
  addEvidence(state, change, "build_x64", commandFiles["build-x64"]);
  addEvidence(state, change, "build_arm64", commandFiles["build-arm64"]);
  addEvidence(state, change, "test_x64", commandFiles["test-x64"]);
  addEvidence(state, change, "test_arm64", commandFiles["test-arm64"]);
  addEvidence(state, change, "negative_control", negative);
  addEvidence(state, change, "performance", performance);
  addEvidence(state, change, "verifier", verifier);
  writeYaml(path.join(change, "LIFECYCLE-STATE.yaml"), state);
  return { root, project, change, matcherFile };
}

test("lifecycle driver advances only after required phase evidence is accepted", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "easywos-state-"));
  const change = path.join(root, "change");
  const preflight = path.join(root, "preflight.yaml");
  writeYaml(preflight, { ok: true });
  lifecycle.init(change, { project: root });
  const state = lifecycle.submit(change, { phase: "PREFLIGHT", key: "preflight", evidence: preflight });
  assert.equal(state.phase, "SCAN");
  assert.equal(state.evidence.preflight.sha256, sha256File(preflight));
});

test("dispatcher prepare rejects spec ids without matcher evidence", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "easywos-dispatch-"));
  const matcherFile = path.join(root, "matcher.json");
  const matchedFile = path.join(root, "matched.yaml");
  const specsFile = path.join(root, "combined.yaml");
  const matcher = makeMatcher(root);
  writeYaml(matchedFile, { porting_items: [{ id: "kernel", file_path: "kernel.cpp", code_range: "1-4", port_spec_ids: [999] }] });
  writeYaml(specsFile, { specs: [{ id: 999, source: "intrinsics-x64-to-arm64" }] });
  matcher.matcher.specs_sha256 = sha256File(specsFile);
  writeJson(matcherFile, matcher);
  assert.throws(() => dispatcher.prepare({ matched: matchedFile, matcher: matcherFile, specs: specsFile, item: "kernel", out: path.join(root, "request.yaml") }), /no matcher evidence/);
});

test("dispatcher prepare, record-result, and summary preserve the matcher chain", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "easywos-dispatch-ok-"));
  const dispatchDir = path.join(root, "dispatch");
  fs.mkdirSync(dispatchDir);
  const matcherFile = path.join(root, "matcher.json");
  const matchedFile = path.join(root, "matched.yaml");
  const specsFile = path.join(root, "combined.yaml");
  const matcher = makeMatcher(root);
  writeYaml(matchedFile, { porting_items: [{ id: "kernel", file_path: "kernel.cpp", code_range: "1-4", port_spec_ids: [86] }] });
  writeYaml(specsFile, { specs: [{ id: 86, source: "intrinsics-x64-to-arm64" }] });
  matcher.matcher.specs_sha256 = sha256File(specsFile);
  writeJson(matcherFile, matcher);
  const requestFile = path.join(dispatchDir, "kernel-attempt-1.request.yaml");
  dispatcher.prepare({ matched: matchedFile, matcher: matcherFile, specs: specsFile, item: "kernel", out: requestFile });
  const patchFile = path.join(root, "kernel.patch");
  fs.writeFileSync(patchFile, "patch fixture\n", "utf8");
  const resultFile = path.join(dispatchDir, "kernel-attempt-1.result.yaml");
  dispatcher.recordResult({ request: requestFile, producer_session: "producer-1", patch: patchFile, out: resultFile });
  const manifestFile = path.join(root, "dispatch-manifest.yaml");
  const result = dispatcher.summarize({ dir: dispatchDir, matcher: matcherFile, out: manifestFile });
  assert.equal(result.manifest.entries.length, 1);
  assert.equal(result.manifest.entries[0].porting_item_id, "kernel");
});

test("archive gate passes complete evidence and advances to ARCHIVE_READY", () => {
  const fixture = createCompleteChange();
  const result = runGate(fixture.change, { openspec_command: `${JSON.stringify(process.execPath)} -e \"process.exit(0)\"` });
  assert.equal(result.ok, true);
  assert.equal(loadData(path.join(fixture.change, "LIFECYCLE-STATE.yaml")).phase, "ARCHIVE_READY");
  assert.ok(fs.existsSync(path.join(fixture.change, "ARCHIVE-GATE-REPORT.md")));
});

test("archive gate rejects missing performance evidence", () => {
  const fixture = createCompleteChange();
  const stateFile = path.join(fixture.change, "LIFECYCLE-STATE.yaml");
  const state = loadData(stateFile);
  delete state.evidence.performance;
  writeYaml(stateFile, state);
  assert.throws(
    () => runGate(fixture.change, { openspec_command: `${JSON.stringify(process.execPath)} -e \"process.exit(0)\"` }),
    (error) => error.code === "E_EVIDENCE_MISSING"
  );
});

test("archive gate rejects STALLED when profiling never ran", () => {
  const fixture = createCompleteChange();
  const stateFile = path.join(fixture.change, "LIFECYCLE-STATE.yaml");
  const state = loadData(stateFile);
  const performanceFile = path.resolve(fixture.change, state.evidence.performance.path);
  writeJson(performanceFile, { schema_version: 1, status: "STALLED", profiler_ran: false, blocker: "no signal" });
  state.evidence.performance.sha256 = sha256File(performanceFile);
  writeYaml(stateFile, state);
  assert.throws(
    () => runGate(fixture.change, { openspec_command: `${JSON.stringify(process.execPath)} -e \"process.exit(0)\"` }),
    (error) => error.code === "E_PERF_NOT_RUN"
  );
});

test("archive gate rejects producer/verifier identity reuse", () => {
  const fixture = createCompleteChange();
  const state = loadData(path.join(fixture.change, "LIFECYCLE-STATE.yaml"));
  const verifierFile = path.resolve(fixture.change, state.evidence.verifier.path);
  const verifier = loadData(verifierFile);
  verifier.verifier_session_id = verifier.producer_session_id;
  writeJson(verifierFile, verifier);
  state.evidence.verifier.sha256 = sha256File(verifierFile);
  writeYaml(path.join(fixture.change, "LIFECYCLE-STATE.yaml"), state);
  assert.throws(
    () => runGate(fixture.change, { openspec_command: `${JSON.stringify(process.execPath)} -e \"process.exit(0)\"` }),
    (error) => error.code === "E_VERIFIER_NOT_INDEPENDENT"
  );
});

test("shared orchestrator instructions keep Claude Workflow and Codex lifecycle separate", () => {
  const skill = fs.readFileSync(
    path.join(ROOT, "skills", "arm64-port-orchestrator", "SKILL.md"),
    "utf8"
  );
  assert.match(skill, /Claude Code with the Workflow runtime/);
  assert.match(skill, /Do not initialize `LIFECYCLE-STATE\.yaml`/);
  assert.match(skill, /Do not run `scripts\/codex\/archive-gate\.js`/);
  assert.match(skill, /\*\*Codex:\*\* run `node <easywos-plugin-root>\/scripts\/codex\/archive-gate\.js/);
  assert.doesNotMatch(skill, /archive gate still consumes `LIFECYCLE-STATE\.yaml`/);
});

test("verification task template emits mutually exclusive host-specific V.11 tasks", () => {
  const skill = fs.readFileSync(
    path.join(ROOT, "skills", "easywos-spec", "SKILL.md"),
    "utf8"
  );
  assert.match(skill, /Append exactly one host-specific V\.11 task; never emit both/);
  assert.match(skill, /V\.11 \(Claude Code\/Workflow\)/);
  assert.match(skill, /V\.11 \(Codex\)/);
  assert.match(skill, /Do not invoke `scripts\/codex\/\*` and do not require `LIFECYCLE-STATE\.yaml`/);
});

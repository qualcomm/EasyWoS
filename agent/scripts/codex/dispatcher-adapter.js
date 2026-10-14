const fs = require("fs");
const path = require("path");
const {
  parseArgs,
  asList,
  loadData,
  writeYaml,
  resolveExisting,
  relativeTo,
  sha256File,
  now,
} = require("./lib");
const {
  validateMatcherEvidence,
  validateDispatchChain,
} = require("./evidence-validator");

function parseSpecIds(value) {
  if (value === undefined || value === null || value === "") return [];
  return String(value).split(",").map((id) => String(id).trim()).filter(Boolean);
}

function matcherItem(matcher, itemId) {
  return matcher.candidates.find((candidate) => candidate.porting_item_id === itemId);
}

function prepare(args) {
  const cwd = process.cwd();
  const matchedFile = resolveExisting(cwd, args.matched, "matched YAML");
  const matcherFile = resolveExisting(cwd, args.matcher, "matcher evidence");
  const specsFile = resolveExisting(cwd, args.specs, "combined specs");
  const matched = loadData(matchedFile);
  const matcher = loadData(matcherFile);
  const specsData = loadData(specsFile);
  validateMatcherEvidence(matcher, matcherFile);

  const item = (matched.porting_items || []).find((entry) => entry.id === args.item);
  if (!item) throw new Error(`porting item not found in matched YAML: ${args.item}`);
  const candidate = matcherItem(matcher, args.item);
  if (!candidate) throw new Error(`porting item not found in matcher evidence: ${args.item}`);

  const mode = args.mode || ((item.port_spec_ids || []).length ? "spec-driven" : "llm-freeform");
  const requestedIds = parseSpecIds(args.port_specs || args.spec_ids || (item.port_spec_ids || []).join(","));
  const matchedIds = new Set((candidate.matches || []).map((match) => String(match.spec_id)));
  if (mode === "spec-driven" && requestedIds.length === 0) throw new Error("spec-driven dispatch requires port spec ids");
  for (const id of requestedIds) {
    if (!matchedIds.has(id)) {
      const error = new Error(`dispatch spec ${id} has no matcher evidence for ${args.item}`);
      error.code = "E_DISPATCH_SPEC_NOT_MATCHED";
      throw error;
    }
  }

  const byId = new Map((specsData.specs || []).map((spec) => [String(spec.id), spec]));
  const selected = requestedIds.map((id) => {
    if (!byId.has(id)) throw new Error(`spec id ${id} is missing from combined specs`);
    return byId.get(id);
  });
  const leafSkills = mode === "llm-freeform"
    ? ["arm64-baseline-porting"]
    : [...new Set(selected.map((spec) => spec.source))];
  const matchEvidenceIds = (candidate.matches || [])
    .filter((match) => requestedIds.includes(String(match.spec_id)))
    .flatMap((match) => (match.evidence || []).map((entry) => entry.evidence_id));

  const request = {
    schema_version: 1,
    dispatch_id: args.dispatch_id || `${args.item}-attempt-${args.attempt || 1}`,
    porting_item_id: args.item,
    source_matched_yaml: path.resolve(matchedFile).replace(/\\/g, "/"),
    source_matched_yaml_sha256: sha256File(matchedFile),
    matcher_evidence: path.resolve(matcherFile).replace(/\\/g, "/"),
    matcher_evidence_sha256: sha256File(matcherFile),
    combined_specs: path.resolve(specsFile).replace(/\\/g, "/"),
    combined_specs_sha256: sha256File(specsFile),
    mode,
    primary_leaf_skill: leafSkills[0],
    supplemental_leaf_skills: leafSkills.slice(1),
    port_spec_ids: requestedIds.map((id) => Number.isNaN(Number(id)) ? id : Number(id)),
    matched_evidence_ids: matchEvidenceIds,
    source_ranges: item.code_range ? [`${item.file_path || ""}:${item.code_range}`] : [],
    feedback_files: asList(args.feedback).map((file) => path.resolve(file).replace(/\\/g, "/")),
    attempt: Number(args.attempt || 1),
    prepared_at: now(),
  };
  const output = path.resolve(args.out);
  writeYaml(output, request);
  return { output, request };
}

function recordResult(args) {
  const cwd = process.cwd();
  const requestFile = resolveExisting(cwd, args.request, "dispatch request");
  const request = loadData(requestFile);
  const changedFiles = asList(args.changed).map((file) => {
    const resolved = resolveExisting(cwd, file, "changed file");
    return { path: path.resolve(resolved).replace(/\\/g, "/"), sha256_after: sha256File(resolved) };
  });
  const patch = args.patch ? resolveExisting(cwd, args.patch, "patch") : null;
  const result = {
    schema_version: 1,
    dispatch_id: request.dispatch_id,
    status: args.status || "APPLIED",
    request: path.resolve(requestFile).replace(/\\/g, "/"),
    request_sha256: sha256File(requestFile),
    producer: { harness: args.harness || "codex", session_id: args.producer_session },
    leaf_skills_used: [request.primary_leaf_skill, ...(request.supplemental_leaf_skills || [])],
    files_changed: changedFiles,
    patch_sha256: patch ? sha256File(patch) : args.patch_sha256 || null,
    feedback_consumed: request.feedback_files || [],
    verification_required: true,
    recorded_at: now(),
  };
  if (!result.producer.session_id) throw new Error("--producer-session is required");
  if (result.status === "APPLIED" && !result.patch_sha256 && changedFiles.length === 0) {
    throw new Error("APPLIED result requires --patch/--patch-sha256 or at least one --changed file");
  }
  const output = path.resolve(args.out);
  writeYaml(output, result);
  return { output, result };
}

function summarize(args) {
  const cwd = process.cwd();
  const dispatchDir = resolveExisting(cwd, args.dir, "dispatch directory");
  const matcherFile = resolveExisting(cwd, args.matcher, "matcher evidence");
  const matcher = loadData(matcherFile);
  validateMatcherEvidence(matcher, matcherFile);

  const requestFiles = fs.readdirSync(dispatchDir).filter((name) => name.endsWith(".request.yaml")).sort();
  if (requestFiles.length === 0) throw new Error(`no dispatch request files in ${dispatchDir}`);
  const entries = [];
  for (const name of requestFiles) {
    const requestFile = path.join(dispatchDir, name);
    const request = loadData(requestFile);
    request.__file = requestFile;
    const resultFile = path.join(dispatchDir, name.replace(/\.request\.yaml$/, ".result.yaml"));
    if (!fs.existsSync(resultFile)) throw new Error(`missing dispatch result: ${resultFile}`);
    const result = loadData(resultFile);
    validateDispatchChain(request, result, matcher, requestFile);
    entries.push({
      dispatch_id: request.dispatch_id,
      porting_item_id: request.porting_item_id,
      request: relativeTo(path.dirname(path.resolve(args.out)), requestFile),
      request_sha256: sha256File(requestFile),
      result: relativeTo(path.dirname(path.resolve(args.out)), resultFile),
      result_sha256: sha256File(resultFile),
    });
  }
  const manifest = { schema_version: 1, matcher_sha256: sha256File(matcherFile), generated_at: now(), entries };
  const output = path.resolve(args.out);
  writeYaml(output, manifest);
  return { output, manifest };
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  const command = args._[0];
  try {
    const result = command === "prepare" ? prepare(args)
      : command === "record-result" ? recordResult(args)
      : command === "summary" ? summarize(args)
      : (() => { throw new Error("usage: dispatcher-adapter.js <prepare|record-result|summary> ..."); })();
    console.log(JSON.stringify(result, null, 2));
  } catch (error) {
    console.error(JSON.stringify({ ok: false, code: error.code || "E_DISPATCH", message: error.message }));
    process.exitCode = 1;
  }
}

if (require.main === module) main();

module.exports = { prepare, recordResult, summarize };

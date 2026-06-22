/**
 * Unit tests for spec_matcher.js
 *
 * Run: node spec_matcher.test.js
 *
 * Covers:
 * - Scope pre-classification (classifyLine)
 * - Scope-filtered matching (matchRuleAgainstContext)
 * - Multi-match candidate output
 * - Empty match scenario
 */

// Import internals by loading the module's functions directly
const fs = require("fs");
const path = require("path");

// We need to extract the functions from spec_matcher.js.
// Since it's a CLI script, we'll re-implement the test targets inline
// by requiring the shared logic. For now, test via the script's output.

const { execSync } = require("child_process");
const yaml = require("./node_modules/js-yaml");

const SCRIPT_PATH = path.resolve(__dirname, "spec_matcher.js");
const SPECS_PATH = path.resolve(__dirname, "../../../openspec/changes/x64-intrinsics-to-arm64-spec-list/combined-spec-summary.yaml");

let passed = 0;
let failed = 0;

function assert(condition, message) {
  if (condition) {
    console.log(`  PASS: ${message}`);
    passed++;
  } else {
    console.log(`  FAIL: ${message}`);
    failed++;
  }
}

function runMatcher(inputYaml) {
  const tmpInput = path.resolve(__dirname, "_test_input.yaml");
  const tmpOutput = path.resolve(__dirname, "_test_output.json");

  fs.writeFileSync(tmpInput, yaml.dump(inputYaml), "utf8");

  try {
    execSync(`node "${SCRIPT_PATH}" --input "${tmpInput}" --specs "${SPECS_PATH}" --output "${tmpOutput}"`, {
      encoding: "utf8",
      stdio: "pipe",
    });
  } catch (e) {
    // Script may exit with error for invalid schemas
    if (fs.existsSync(tmpOutput)) {
      const result = JSON.parse(fs.readFileSync(tmpOutput, "utf8"));
      cleanup(tmpInput, tmpOutput);
      return result;
    }
    cleanup(tmpInput, tmpOutput);
    return null;
  }

  const result = JSON.parse(fs.readFileSync(tmpOutput, "utf8"));
  cleanup(tmpInput, tmpOutput);
  return result;
}

function cleanup(...files) {
  files.forEach(f => { try { fs.unlinkSync(f); } catch(e) {} });
}

// ---------------------------------------------------------------------------
// Test 1: Scope correct filtering — instruction scope pattern only matches
// instruction lines, not comments
// ---------------------------------------------------------------------------

console.log("\nTest 1: Scope filtering — instruction patterns skip comments");
{
  const input = {
    schema: "x64-to-arm64-porting",
    porting_items: [{
      id: "test-scope-filter",
      context: [
        "; This comment mentions jb but is not an instruction",
        "    mov    rax, rbx",
        "    ; another comment with jne in it",
      ].join("\n"),
    }],
  };

  const result = runMatcher(input);
  assert(result !== null, "Script ran successfully");
  assert(result.candidates.length === 1, "One porting item processed");

  const matches = result.candidates[0].matches;
  // jb/jne appear only in comments, so spec 13 should NOT match
  const spec13 = matches.find(m => m.spec_id === 13);
  assert(!spec13, "Spec 13 (Flag Discipline) does not match patterns in comments");
}

// ---------------------------------------------------------------------------
// Test 2: Multi-match candidate output — code matching multiple specs
// ---------------------------------------------------------------------------

console.log("\nTest 2: Multi-match — code triggers multiple spec candidates");
{
  const input = {
    schema: "x64-to-arm64-porting",
    porting_items: [{
      id: "test-multi-match",
      context: [
        "    push    %rbx",
        "    push    %rbp",
        "    sub     %rsp, 32",
        "    jnz     .label",
        "    dec     %rcx",
        "    jne     .loop",
      ].join("\n"),
    }],
  };

  const result = runMatcher(input);
  assert(result !== null, "Script ran successfully");

  const matches = result.candidates[0].matches;
  assert(matches.length >= 2, `Multiple specs matched (got ${matches.length})`);

  const spec12 = matches.find(m => m.spec_id === 12);
  const spec13 = matches.find(m => m.spec_id === 13);
  assert(!!spec12, "Spec 12 (Callee-Saved) matched push %rbx/%rbp");
  assert(!!spec13, "Spec 13 (Flag Discipline) matched jnz/jne");

  if (spec12) {
    assert(spec12.rules_hit >= 1, `Spec 12 rules_hit >= 1 (got ${spec12.rules_hit})`);
  }
  if (spec13) {
    assert(spec13.rules_hit >= 2, `Spec 13 rules_hit >= 2 (got ${spec13.rules_hit})`);
  }
}

// ---------------------------------------------------------------------------
// Test 3: Empty match — no patterns match
// ---------------------------------------------------------------------------

console.log("\nTest 3: Empty match — vanilla code triggers no spec");
{
  const input = {
    schema: "x64-to-arm64-porting",
    porting_items: [{
      id: "test-no-match",
      context: [
        "int main() {",
        "    return 0;",
        "}",
      ].join("\n"),
    }],
  };

  const result = runMatcher(input);
  assert(result !== null, "Script ran successfully");
  assert(result.candidates[0].matches.length === 0, "No specs matched for generic C code");
}

// ---------------------------------------------------------------------------
// Test 4: Empty porting_items array
// ---------------------------------------------------------------------------

console.log("\nTest 4: Empty porting_items — script produces empty candidates");
{
  const input = {
    schema: "x64-to-arm64-porting",
    porting_items: [],
  };

  const result = runMatcher(input);
  assert(result !== null, "Script ran successfully");
  assert(result.candidates.length === 0, "Empty candidates for empty input");
}

// ---------------------------------------------------------------------------
// Summary
// ---------------------------------------------------------------------------

console.log(`\n${"=".repeat(50)}`);
console.log(`Results: ${passed} passed, ${failed} failed, ${passed + failed} total`);
if (failed > 0) process.exit(1);

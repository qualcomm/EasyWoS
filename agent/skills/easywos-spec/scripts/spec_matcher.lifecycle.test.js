const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawnSync } = require("child_process");
const yaml = require("./node_modules/js-yaml");

const SCRIPT = path.resolve(__dirname, "spec_matcher.js");

function runFixture(source, item, specs) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "easywos-matcher-"));
  const sourcePath = path.join(dir, "fixture.cpp");
  const inputPath = path.join(dir, "scan.yaml");
  const specsPath = path.join(dir, "specs.yaml");
  const outputPath = path.join(dir, "matches.json");
  fs.writeFileSync(sourcePath, source, "utf8");
  fs.writeFileSync(inputPath, yaml.dump({
    schema: "x64-to-arm64-porting",
    porting_items: [{ file_path: "fixture.cpp", ...item }],
  }), "utf8");
  fs.writeFileSync(specsPath, yaml.dump({ specs }), "utf8");

  const result = spawnSync(process.execPath, [
    SCRIPT, "--input", inputPath, "--specs", specsPath, "--output", outputPath,
  ], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr || result.stdout);
  return JSON.parse(fs.readFileSync(outputPath, "utf8"));
}

test("declaration lines retain intrinsic_call scope and source evidence", () => {
  const output = runFixture(
    "int validate(__m128i v) {\n  const int mask = _mm_movemask_epi8(v);\n  return mask;\n}\n",
    { id: "movemask", code_range: "1-4" },
    [{
      id: 86,
      name: "no-movemask",
      metadata: { match_rules: [{ id: "movemask-call", pattern: "_mm_movemask_epi8", type: "exact", scope: "intrinsic_call" }] },
    }]
  );
  const match = output.candidates[0].matches[0];
  assert.equal(match.spec_id, 86);
  assert.ok(match.evidence[0].scopes.includes("declaration"));
  assert.ok(match.evidence[0].scopes.includes("intrinsic_call"));
  assert.equal(match.evidence[0].file, "fixture.cpp");
  assert.equal(match.evidence[0].line, 2);
});

const arm64InlineAsmSpec = {
  id: 1,
  name: "arm64-inline-asm",
  metadata: {
    match_groups: [{
      id: "arm64-inline-asm-block",
      all_of: [{ pattern: "(?:__asm__|asm)\\s+(?:__volatile__|volatile)?\\s*\\(", type: "regex", scope: "inline_asm" }],
      any_of: [
        { pattern: "\\b(?:pmull2?|ld1|st1|rbit)\\b", type: "regex", scope: "inline_asm" },
        { pattern: "__aarch64__|_M_ARM64", type: "regex", scope: "preprocessor" },
      ],
    }],
  },
};

test("x86 extended asm register constraints do not imply ARM64 inline asm", () => {
  const output = runFixture(
    "void f(long x) {\n  asm volatile(\"addq $1, %0\" : \"=r\"(x) : \"0\"(x) : \"cc\");\n}\n",
    { id: "x86-asm", code_range: "1-3" },
    [arm64InlineAsmSpec]
  );
  assert.equal(output.candidates[0].matches.length, 0);
});
test("ARM64 mnemonic plus asm opener satisfies compound match group", () => {
  const output = runFixture(
    "void f(void) {\n  asm volatile(\n    \"pmull v0.1q, v1.1d, v2.1d\\n\\t\"\n    : : : \"v0\", \"memory\");\n}\n",
    { id: "arm64-asm", code_range: "1-5" },
    [arm64InlineAsmSpec]
  );
  const match = output.candidates[0].matches[0];
  assert.deepEqual(match.matched_groups, ["arm64-inline-asm-block"]);
  assert.ok(match.evidence.some((entry) => entry.line === 3));
});

test("none_of rejects a compound rule when a forbidden condition is present", () => {
  const spec = JSON.parse(JSON.stringify(arm64InlineAsmSpec));
  spec.metadata.match_groups[0].none_of = [{ pattern: "DISABLE_ARM_PORT", type: "exact", scope: "preprocessor" }];
  const output = runFixture(
    "#define DISABLE_ARM_PORT\nvoid f(void) {\n  asm volatile(\"pmull v0.1q, v1.1d, v2.1d\\n\\t\");\n}\n",
    { id: "blocked-arm64-asm", code_range: "1-4" },
    [spec]
  );
  assert.equal(output.candidates[0].matches.length, 0);
});

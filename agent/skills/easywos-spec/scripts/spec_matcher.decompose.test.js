/**
 * Unit tests for whole-file assembly decomposition in spec_matcher.js
 *
 * Run: node spec_matcher.decompose.test.js
 *
 * These tests are SELF-CONTAINED: they synthesize a minimal spec collection
 * and a fixture .asm file in a temp dir, so they do not depend on the
 * generated combined-spec-summary.yaml (which is absent in the standalone
 * skills repo).
 *
 * Covers:
 * - Whole-file asm item above threshold is decomposed into per-kernel groups
 * - Size/CPU variants of the same kernel aggregate into ONE group
 * - Each group child carries a multi-range code_range + function list
 * - segment:false suppresses decomposition; small files are left intact
 * - Per-group spec matching stays discriminating (no saturation)
 */

const fs = require("fs");
const path = require("path");
const os = require("os");
const { execSync } = require("child_process");
const yaml = require("./node_modules/js-yaml");

const SCRIPT_PATH = path.resolve(__dirname, "spec_matcher.js");

let passed = 0;
let failed = 0;
function assert(cond, msg) {
  if (cond) { console.log(`  PASS: ${msg}`); passed++; }
  else { console.log(`  FAIL: ${msg}`); failed++; }
}

// ---------------------------------------------------------------------------
// Fixture setup
// ---------------------------------------------------------------------------

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "ewos-decomp-"));

// Minimal spec collection: one SAD-ish spec (psadbw), one flag spec (jne).
const specs = {
  specs: [
    {
      id: 101, name: "sad-neon",
      metadata: { match_rules: [{ pattern: "psadbw", scope: "instruction" }] },
    },
    {
      id: 102, name: "flag-discipline",
      metadata: { match_rules: [{ pattern: "\\b(jne|jnz)\\b", scope: "instruction" }] },
    },
  ],
};
const specsPath = path.join(tmp, "specs.yaml");
fs.writeFileSync(specsPath, yaml.dump(specs), "utf8");

// Build a fixture .asm file with several kernels, size + CPU variants.
// We pad each kernel body so the whole file comfortably exceeds the threshold.
function kernel(name, instrs) {
  const body = [];
  body.push(`cglobal ${name}, 4, 6, 8`);
  for (const ins of instrs) body.push(`    ${ins}`);
  // pad to ~30 lines per kernel
  while (body.length < 30) body.push("    nop");
  body.push("    RET");
  return body.join("\n");
}

const asmParts = [
  kernel("pixel_sad_16x16_sse2", ["movdqu m0, [r0]", "psadbw m0, [r2]", "paddw m1, m0"]),
  kernel("pixel_sad_16x16_avx2", ["movdqu m0, [r0]", "psadbw m0, [r2]"]),
  kernel("pixel_sad_8x8_sse2",   ["movq m0, [r0]", "psadbw m0, [r2]"]),
  kernel("pixel_satd_8x8_sse2",  ["movdqu m0, [r0]", "psubw m0, m1", "dec r5", "jne .loop"]),
  kernel("pixel_satd_16x16_avx2",["movdqu m0, [r0]", "psubw m0, m1", "jnz .next"]),
  kernel("getResidual32",        ["movu m0, [r0]", "psubw m0, m1"]),
];
const asmText = asmParts.join("\n\n");
const asmPath = path.join(tmp, "pixel-a.asm");
fs.writeFileSync(asmPath, asmText, "utf8");
const asmLineCount = asmText.split("\n").length;

function runMatcher(input, extraArgs = "") {
  const inPath = path.join(tmp, "in.yaml");
  const outPath = path.join(tmp, "out.json");
  fs.writeFileSync(inPath, yaml.dump(input), "utf8");
  execSync(`node "${SCRIPT_PATH}" --input "${inPath}" --specs "${specsPath}" --output "${outPath}" ${extraArgs}`,
    { encoding: "utf8", stdio: "pipe" });
  return JSON.parse(fs.readFileSync(outPath, "utf8"));
}

// ---------------------------------------------------------------------------
// Test 1: whole-file asm above threshold decomposes into per-kernel groups
// ---------------------------------------------------------------------------

console.log(`\nTest 1: whole-file decomposition (file is ${asmLineCount} lines)`);
{
  const input = {
    schema: "x64-to-arm64-porting",
    porting_items: [{
      id: "pixel-metrics-8bit",
      title: "Pixel cost primitives",
      file_path: "pixel-a.asm",
      code_range: `1-${asmLineCount}`,
    }],
  };
  // Force decomposition regardless of threshold by using a low threshold.
  const result = runMatcher(input, "--threshold 50");

  // 6 kernels -> 3 groups: pixel_sad, pixel_satd, getResidual32.
  // pixel_sad_{16x16,8x8} + CPU variants collapse via the underscore-delimited
  // size/ISA suffix rule; getResidual32 has its size FUSED into the name (no
  // underscore) so it stays a distinct named kernel — see kernelGroupKey().
  const ids = result.candidates.map(c => c.porting_item_id);
  assert(result.candidates.length === 3, `3 group children produced (got ${result.candidates.length})`);
  assert(ids.includes("pixel-metrics-8bit__pixel_sad"), "pixel_sad group present");
  assert(ids.includes("pixel-metrics-8bit__pixel_satd"), "pixel_satd group present");
  assert(ids.includes("pixel-metrics-8bit__getResidual32"), "getResidual32 group present (fused size kept)");

  const sad = result.candidates.find(c => c.group === "pixel_sad");
  assert(sad.function_count === 3, `pixel_sad aggregates 3 variants (got ${sad.function_count})`);
  assert(sad.code_range.split(",").length === 3, "pixel_sad code_range is multi-range (3 segments)");
  assert(sad.parent_id === "pixel-metrics-8bit", "child carries parent_id");

  // Discriminating match: sad group hits spec 101 (psadbw), satd group hits 102 (jne)
  const sadHits = sad.matches.map(m => m.spec_id);
  const satd = result.candidates.find(c => c.group === "pixel_satd");
  const satdHits = satd.matches.map(m => m.spec_id);
  assert(sadHits.includes(101) && !sadHits.includes(102), "pixel_sad matches SAD spec only (no flag spec)");
  assert(satdHits.includes(102), "pixel_satd matches flag spec");
}

// ---------------------------------------------------------------------------
// Test 2: segment:false suppresses decomposition
// ---------------------------------------------------------------------------

console.log("\nTest 2: segment:false keeps the item whole");
{
  const input = {
    schema: "x64-to-arm64-porting",
    porting_items: [{
      id: "whole",
      title: "Whole file, do not split",
      file_path: "pixel-a.asm",
      code_range: `1-${asmLineCount}`,
      segment: false,
    }],
  };
  const result = runMatcher(input, "--threshold 50");
  assert(result.candidates.length === 1, "Not decomposed (1 item)");
  assert(result.candidates[0].porting_item_id === "whole", "Original id preserved");
}

// ---------------------------------------------------------------------------
// Test 3: below threshold is left intact (single-blob path)
// ---------------------------------------------------------------------------

console.log("\nTest 3: file below threshold is not decomposed");
{
  const input = {
    schema: "x64-to-arm64-porting",
    porting_items: [{
      id: "small",
      file_path: "pixel-a.asm",
      code_range: `1-${asmLineCount}`,
    }],
  };
  // Default threshold (400) > fixture size -> no decomposition.
  const result = runMatcher(input);
  assert(result.candidates.length === 1, "Not decomposed under default threshold");
  assert(result.candidates[0].porting_item_id === "small", "Original id preserved");
}

// ---------------------------------------------------------------------------
// Test 4: --no-decompose global switch
// ---------------------------------------------------------------------------

console.log("\nTest 4: --no-decompose disables the pass");
{
  const input = {
    schema: "x64-to-arm64-porting",
    porting_items: [{
      id: "forced", file_path: "pixel-a.asm", code_range: `1-${asmLineCount}`, segment: true,
    }],
  };
  const result = runMatcher(input, "--no-decompose");
  assert(result.candidates.length === 1, "--no-decompose overrides segment:true");
}

// ---------------------------------------------------------------------------

try { fs.rmSync(tmp, { recursive: true, force: true }); } catch (e) {}

console.log(`\n${"=".repeat(50)}`);
console.log(`Results: ${passed} passed, ${failed} failed, ${passed + failed} total`);
if (failed > 0) process.exit(1);

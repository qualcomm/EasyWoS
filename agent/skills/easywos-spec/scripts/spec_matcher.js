/**
 * EasyWoS Spec Matcher - Initial Screening Script
 *
 * Performs scope-filtered regex matching of porting_items against a spec collection.
 * Outputs a candidate match list (JSON) for LLM semantic refinement.
 *
 * Usage:
 *   node spec_matcher.js --input <easywos-yaml> --specs <spec-collection-yaml> --output <candidates-json>
 *
 * Dependencies: js-yaml (npm install js-yaml)
 */

const fs = require("fs");
const path = require("path");
const yaml = require("js-yaml");

// ---------------------------------------------------------------------------
// Scope pre-classification
// ---------------------------------------------------------------------------

const INSTRUCTION_RE = /^\s*(?:;[^\n]*\n)?\s*(push|pop|mov|add|sub|inc|dec|mul|imul|div|idiv|neg|not|and|or|xor|shl|shr|sar|cmp|test|jmp|je|jne|jz|jnz|jb|ja|jbe|jae|jl|jg|jle|jge|call|ret|nop|lea|movups|movaps|movdqa|movdqu|movu|movhlps|movlhps|lddqu|addps|addss|subps|mulps|divps|shufps|unpcklps|unpckhps|pslld|psrld|psllw|psrlw|psllq|psrlq|pslldq|psrldq|psraw|psrad|por|pand|pandn|pshufb|pshufd|pshuflw|pshufhw|adc|sbb|loop|rep|stp|ldp|ldr|str|bl|b\.\w+|cbz|cbnz|fadd|fmul|fsub|fdiv|faddp|ld1|st1|ext|dup|movq|movd|pxor|paddb|paddw|paddd|paddq|psubb|psubw|psubd|psubq|psadbw|pmaddwd|pmaddubsw|pmulhw|pmulhuw|pmulhrsw|pmullw|pmulld|pmuludq|packuswb|packsswb|packssdw|packusdw|punpcklbw|punpckhbw|punpcklwd|punpckhwd|punpckldq|punpckhdq|punpcklqdq|punpckhqdq|pabsb|pabsw|pabsd|pavgb|pavgw|pmaxsw|pmaxub|pmaxsb|pmaxuw|pmaxsd|pminsw|pminub|pminsb|pminuw|pminsd|pcmpeqb|pcmpeqw|pcmpeqd|pcmpgtb|pcmpgtw|pcmpgtd|pmovmskb|phaddw|phaddd|phsubw|palignr|pblendw|pblendvb|pmull|aese|aesd|aesmc|sha1c|sha1h|sha256h)\b/i;

const INTRINSIC_CALL_RE = /_mm(?:256|512)?_\w+\s*\(|v(?:ld1|st1|add|sub|mul|dup|get_lane|set_lane|reinterpret|combine)q?_\w+\s*\(/i;

const GENERIC_FUNC_CALL_RE = /\b\w+\s*\([^)]*\)/;

const PREPROCESSOR_RE = /^\s*#\s*(include|define|ifdef|ifndef|if|elif|else|endif|pragma|undef)\b/;

const DIRECTIVE_RE = /^\s*\.(globl|global|type|cfi_\w+|text|data|section|align|byte|long|quad)\b/;

const DECLARATION_RE = /^\s*(my\s*\(|(static\s+)?(const\s+)?(unsigned\s+)?(int|float|double|char|void|__m128|__m256|uint\d+_t|int\d+_t)\s+|\$\w+\s*=|(extern|typedef|struct|union|enum)\s)/i;

const COMMENT_RE = /^\s*(;|\/\/|\/\*|\*|#\s*$)/;

function classifyLine(line) {
  const stripped = line.trim();
  if (!stripped) return "blank";
  if (COMMENT_RE.test(stripped)) return "comment";
  if (PREPROCESSOR_RE.test(stripped)) return "preprocessor";
  if (DIRECTIVE_RE.test(stripped)) return "directive";
  if (DECLARATION_RE.test(stripped)) return "declaration";
  if (INTRINSIC_CALL_RE.test(stripped) && !INSTRUCTION_RE.test(stripped)) return "intrinsic_call";
  if (INSTRUCTION_RE.test(stripped)) return "instruction";
  if (GENERIC_FUNC_CALL_RE.test(stripped)) return "function_call";
  return "expression";
}

function classifyContext(context) {
  return context.split("\n").map((line) => ({
    line,
    scope: classifyLine(line),
  }));
}

// ---------------------------------------------------------------------------
// Scope mapping
// ---------------------------------------------------------------------------

const SCOPE_MAP = {
  instruction: new Set(["instruction"]),
  instruction_operand: new Set(["instruction"]),
  instruction_sequence: new Set(["instruction"]),
  declaration: new Set(["declaration"]),
  perl_declaration: new Set(["declaration"]),
  intrinsic_call: new Set(["intrinsic_call", "function_call"]),
  function_call: new Set(["function_call", "intrinsic_call"]),
  function_declaration: new Set(["declaration", "function_call"]),
  preprocessor: new Set(["preprocessor"]),
  directive: new Set(["directive"]),
  expression: new Set(["expression", "instruction", "declaration", "intrinsic_call", "function_call"]),
  type_or_instance: new Set(["declaration", "expression"]),
  variable_reference: new Set(["expression", "instruction", "declaration"]),
  constant_reference: new Set(["expression", "declaration", "preprocessor"]),
  algorithm_call: new Set(["function_call", "intrinsic_call", "expression"]),
  function_name: new Set(["declaration", "directive", "function_call"]),
};

const ALL_CODE_SCOPES = new Set([
  "instruction", "declaration", "intrinsic_call", "function_call",
  "preprocessor", "directive", "expression",
]);

function getEligibleScopes(ruleScope) {
  if (!ruleScope) return ALL_CODE_SCOPES;
  return SCOPE_MAP[ruleScope] || new Set(["expression"]);
}

// ---------------------------------------------------------------------------
// Matching engine
// ---------------------------------------------------------------------------

function unescapePattern(pattern) {
  // The spec YAML stores patterns with double-escaped backslashes (e.g., "\\\\b" for \b).
  // After YAML parsing, they become "\\b". We need to keep them as-is for regex usage
  // since JS RegExp constructor interprets backslashes in the string.
  // However, if the YAML was double-double-escaped (4 backslashes -> 2 after YAML parse),
  // we need to reduce one level: "\\\\" -> "\\".
  return pattern.replace(/\\\\/g, "\\");
}

function matchRuleAgainstContext(rule, classifiedLines) {
  const pattern = rule.pattern || "";
  const ruleScope = rule.scope || "";
  const ruleType = rule.type || "regex";

  const eligible = getEligibleScopes(ruleScope);
  const eligibleLines = classifiedLines
    .filter((entry) => eligible.has(entry.scope))
    .map((entry) => entry.line);

  if (eligibleLines.length === 0) return false;

  const textBlock = eligibleLines.join("\n");

  if (ruleType === "exact") {
    return textBlock.includes(pattern);
  } else if (ruleType === "prefix") {
    return eligibleLines.some((line) => line.includes(pattern));
  } else {
    // regex — unescape double backslashes from YAML encoding
    const unescaped = unescapePattern(pattern);
    try {
      const re = new RegExp(unescaped, "m");
      return re.test(textBlock);
    } catch (e) {
      // Invalid regex — fallback to literal search
      return textBlock.includes(pattern);
    }
  }
}

function matchItemAgainstSpecs(context, specs) {
  const classifiedLines = classifyContext(context);
  const candidates = [];

  for (const spec of specs) {
    const matchRules = (spec.metadata && spec.metadata.match_rules) || [];
    let rulesHit = 0;
    const matchedPatterns = [];

    for (const rule of matchRules) {
      if (matchRuleAgainstContext(rule, classifiedLines)) {
        rulesHit++;
        matchedPatterns.push(rule.pattern || "");
      }
    }

    if (rulesHit > 0) {
      candidates.push({
        spec_id: spec.id,
        spec_name: spec.name || "",
        rules_hit: rulesHit,
        matched_rules: matchedPatterns,
      });
    }
  }

  // Sort by rules_hit descending
  candidates.sort((a, b) => b.rules_hit - a.rules_hit);
  return candidates;
}

// ---------------------------------------------------------------------------
// Whole-file assembly decomposition (per-kernel grouping)
// ---------------------------------------------------------------------------
//
// Background: the regex matcher above is designed for a single logical unit
// (a function prolog, one SIMD loop body, ~10-60 lines). When a porting_item
// covers an ENTIRE hand-written assembly file (a large file holding many
// independent kernels/procedures) two failure modes appear:
//   1. Match saturation — nearly every spec's match_rules fire somewhere in
//      a very large file, so the candidate list loses all discriminating power.
//   2. Un-actionable tasks — a single task spanning thousands of lines cannot
//      be handed to a leaf skill, and there is no granularity for per-kernel
//      verification.
//
// The fix is a pre-pass that splits a long asm file along its structural
// boundaries (`cglobal` / `cvisible` for NASM-x86inc, `PROC` for MASM), then
// AGGREGATES size/CPU variants of the same kernel into a GROUP. Each group
// becomes a child porting_item with its own multi-range `code_range`, matched
// independently. Downstream stages (matched YAML, dispatcher, tasks.md,
// verification) keep working unchanged — they just see more, smaller items.

const DEFAULT_DECOMPOSE_THRESHOLD = 400; // resolved-context lines

const ASM_FILE_RE = /\.(asm|s|S)$/;

// NASM x86inc kernel entry: `cglobal name, ...` / `cvisible name`
const CGLOBAL_RE = /^\s*(?:cglobal|cvisible)\s+([A-Za-z_][\w]*)/;
// MASM procedure entry: `name PROC`
const MASM_PROC_RE = /^\s*([A-Za-z_][\w@$?]*)\s+PROC\b/i;

function isAsmPath(p) {
  return !!p && ASM_FILE_RE.test(p);
}

/**
 * Reduce a kernel function name to its group key by stripping the
 * UNDERSCORE-DELIMITED size/CPU-variant suffixes that distinguish members of
 * one logical kernel. A dimension fused into the name (no underscore separator)
 * is NOT stripped — such names denote distinct routines and stay separate.
 * Using a generic base name `foo`:
 *   foo_16x16            -> foo
 *   foo_16x16_avx2       -> foo
 *   foo_x4_16x16         -> foo_x4   (x3/x4 batch/arity dimension retained)
 *   foo_normal           -> foo_normal (no recognized variant suffix)
 *   foo32                -> foo32    (fused dimension, kept distinct)
 */
function kernelGroupKey(name) {
  let b = name;
  // CPU / ISA variant suffix (possibly repeated, e.g. _sse2 already handled)
  b = b.replace(/_(mmx2?|sse|sse2|sse3|ssse3|sse4|avx|avx2|avx512|xop|fma3?|neon|aarch64)$/i, "");
  // WxH dimension suffix (e.g. _16x16, _8x8)
  b = b.replace(/_\d+x\d+$/, "");
  // Macro-truncated dimension fragment: templated codegen may emit a name
  // ending in a dangling `_NNx` or a trailing `_`.
  b = b.replace(/_\d+x$/, "");
  b = b.replace(/_x$/, "");
  // trailing underscore-delimited single dimension (e.g. _32, _16)
  b = b.replace(/_\d+$/, "");
  // trailing separators left by macro truncation
  b = b.replace(/_+$/, "");
  return b || name;
}

/**
 * Parse a region of an assembly file into kernels (one entry per
 * cglobal/cvisible/PROC), each with its [start,end] 1-based line range
 * (end exclusive of the next kernel's start) and a short body sample used
 * for spec matching.
 *
 * `rangeStart`/`rangeEnd` are 1-based inclusive bounds within `fileLines`.
 */
function parseKernels(fileLines, rangeStart, rangeEnd, bodySampleLines) {
  const sample = bodySampleLines || 60;
  const boundaries = [];
  for (let ln = rangeStart; ln <= rangeEnd; ln++) {
    const line = fileLines[ln - 1];
    if (line === undefined) break;
    let m = CGLOBAL_RE.exec(line);
    if (m) { boundaries.push({ name: m[1], line: ln }); continue; }
    m = MASM_PROC_RE.exec(line);
    if (m) { boundaries.push({ name: m[1], line: ln }); }
  }
  if (boundaries.length === 0) return [];

  const kernels = [];
  for (let i = 0; i < boundaries.length; i++) {
    const start = boundaries[i].line;
    const end = (i + 1 < boundaries.length ? boundaries[i + 1].line - 1 : rangeEnd);
    const bodyEnd = Math.min(end, start + sample - 1);
    kernels.push({
      name: boundaries[i].name,
      group: kernelGroupKey(boundaries[i].name),
      start,
      end,
      sample: fileLines.slice(start - 1, bodyEnd).join("\n"),
    });
  }
  return kernels;
}

/**
 * Decide whether an item should be decomposed and, if so, return its child
 * group items. Returns null when decomposition does not apply.
 *
 * Triggers (per the configured policy):
 *   - item.segment === false  -> never decompose
 *   - item.segment === true   -> always decompose (if it is an asm file)
 *   - otherwise               -> decompose when file is asm AND the resolved
 *                                context exceeds `threshold` lines
 */
function decomposeItem(item, inputDir, context, threshold) {
  if (item.segment === false) return null;
  const forced = item.segment === true;

  // Decomposition reads structural boundaries from the file itself, so it
  // requires a single-file, single-range item (the common whole-file case).
  if (!item.file_path || !item.code_range) return null;
  if (String(item.code_range).includes(",")) return null; // already multi-range
  if (!isAsmPath(item.file_path)) return null;

  const lineCount = context ? context.split("\n").length : 0;
  if (!forced && lineCount <= threshold) return null;

  const m = /^\s*(\d+)\s*-\s*(\d+)\s*$/.exec(String(item.code_range));
  if (!m) return null;

  const abs = path.resolve(inputDir, item.file_path);
  if (!fs.existsSync(abs)) return null;
  const fileLines = fs.readFileSync(abs, "utf8").split("\n");

  const rangeStart = parseInt(m[1], 10);
  const rangeEnd = Math.min(parseInt(m[2], 10), fileLines.length);

  const kernels = parseKernels(fileLines, rangeStart, rangeEnd);
  if (kernels.length < 2) return null; // nothing meaningful to split

  // Aggregate kernels by group key, preserving first-appearance order.
  const order = [];
  const groups = new Map();
  for (const k of kernels) {
    if (!groups.has(k.group)) { groups.set(k.group, []); order.push(k.group); }
    groups.get(k.group).push(k);
  }

  const children = order.map((gk) => {
    const members = groups.get(gk);
    members.sort((a, b) => a.start - b.start);
    const ranges = members.map((k) => `${k.start}-${k.end}`).join(", ");
    return {
      id: `${item.id}__${gk}`,
      parent_id: item.id,
      title: `${item.title || item.id} — ${gk}`,
      file_path: item.file_path,
      code_range: ranges,
      group: gk,
      functions: members.map((k) => k.name),
      function_count: members.length,
      // Matching context: concatenated body samples, capped by parseKernels.
      context: members.map((k) => k.sample).join(
        "\n; --- variant boundary --- \n"
      ),
    };
  });

  return children;
}

// ---------------------------------------------------------------------------
// CLI argument parsing
// ---------------------------------------------------------------------------

function parseArgs() {
  const args = process.argv.slice(2);
  const parsed = {};
  for (let i = 0; i < args.length; i++) {
    if (args[i] === "--input" && args[i + 1]) parsed.input = args[++i];
    else if (args[i] === "--specs" && args[i + 1]) parsed.specs = args[++i];
    else if (args[i] === "--output" && args[i + 1]) parsed.output = args[++i];
    else if (args[i] === "--threshold" && args[i + 1]) parsed.threshold = parseInt(args[++i], 10);
    else if (args[i] === "--no-decompose") parsed.noDecompose = true;
  }
  if (!parsed.input || !parsed.specs || !parsed.output) {
    console.error("Usage: node spec_matcher.js --input <yaml> --specs <yaml> --output <json> [--threshold N] [--no-decompose]");
    process.exit(1);
  }
  if (!Number.isFinite(parsed.threshold)) parsed.threshold = DEFAULT_DECOMPOSE_THRESHOLD;
  return parsed;
}

// ---------------------------------------------------------------------------
// Context Resolution
// ---------------------------------------------------------------------------

/**
 * Resolve the source bytes for a porting_item.
 *
 * `code_range` accepts three forms (see arm64-porting-report/references/schema.md):
 *   1. Single range:                    "21-30"
 *   2. Multi-range, same file:          "21-30, 47-61"
 *   3. Multi-range with cross-file path: "10-12, arch/x86/crc32_pclmulqdq_tpl.h:140-220"
 *
 * Each segment may optionally be prefixed with "<relative-path>:" to read from
 * a file other than `item.file_path` (resolved relative to inputDir, same rule
 * as file_path itself). Segments without a prefix read from `item.file_path`.
 * Concatenated text from all segments is returned, joined by a marker line so
 * the regex matcher does not bridge across segment boundaries.
 */
function resolveContext(item, inputDir) {
  if (item.context) {
    return item.context;
  }
  if (!item.code_range) {
    return "";
  }

  const fileCache = new Map();
  function readFileLines(relPath) {
    if (fileCache.has(relPath)) return fileCache.get(relPath);
    const abs = path.resolve(inputDir, relPath);
    if (!fs.existsSync(abs)) {
      console.error(`Warning: Source file not found: ${abs} (item: ${item.id})`);
      fileCache.set(relPath, null);
      return null;
    }
    const lines = fs.readFileSync(abs, "utf8").split("\n");
    fileCache.set(relPath, lines);
    return lines;
  }

  const segments = String(item.code_range).split(",").map(s => s.trim()).filter(Boolean);
  const chunks = [];

  for (const seg of segments) {
    // Find the LAST colon — paths on Windows can contain a drive letter colon
    // but that is resolved before getting here; relative paths here use '/'.
    const colonIdx = seg.lastIndexOf(":");
    let relPath, rangeStr;
    if (colonIdx > 0 && /\d+\s*-\s*\d+\s*$/.test(seg.slice(colonIdx + 1))) {
      relPath = seg.slice(0, colonIdx).trim();
      rangeStr = seg.slice(colonIdx + 1).trim();
    } else {
      if (!item.file_path) continue;
      relPath = item.file_path;
      rangeStr = seg;
    }
    const m = /^(\d+)\s*-\s*(\d+)$/.exec(rangeStr);
    if (!m) {
      console.error(`Warning: Malformed code_range segment '${seg}' (item: ${item.id})`);
      continue;
    }
    const lines = readFileLines(relPath);
    if (!lines) continue;
    const start = parseInt(m[1], 10) - 1;
    const end = parseInt(m[2], 10);
    if (start < 0 || end > lines.length || start >= end) {
      console.error(`Warning: code_range '${seg}' exceeds bounds of ${relPath} (${lines.length} lines, item: ${item.id})`);
      continue;
    }
    chunks.push(lines.slice(start, end).join("\n"));
  }

  // Join with a sentinel so multiline regex patterns (if any) cannot bridge
  // across segments. Plain newline join is also safe for line-based regex.
  return chunks.join("\n/* --- code_range segment boundary --- */\n");
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

function main() {
  const args = parseArgs();

  // Load input YAML
  if (!fs.existsSync(args.input)) {
    console.error(`Error: Input file not found: ${args.input}`);
    process.exit(1);
  }
  const inputData = yaml.load(fs.readFileSync(args.input, "utf8"));

  if (inputData.schema !== "x64-to-arm64-porting") {
    console.error("Error: Input YAML schema is not 'x64-to-arm64-porting'");
    process.exit(1);
  }

  const portingItems = inputData.porting_items || [];
  if (portingItems.length === 0) {
    console.error("No porting items found.");
    fs.writeFileSync(args.output, JSON.stringify({ candidates: [] }, null, 2), "utf8");
    process.exit(0);
  }

  const inputDir = path.dirname(path.resolve(args.input));

  // Load spec collection
  if (!fs.existsSync(args.specs)) {
    console.error(`Error: Spec collection not found: ${args.specs}`);
    process.exit(1);
  }
  const specsData = yaml.load(fs.readFileSync(args.specs, "utf8"));
  const specs = specsData.specs || [];

  // Run matching. Whole-file assembly items (> threshold lines) are first
  // decomposed into per-kernel GROUP children; each group is matched
  // independently so spec selection stays discriminating and the resulting
  // tasks are individually actionable. Smaller items keep the single-blob path.
  const results = [];
  let decomposedCount = 0;
  for (const item of portingItems) {
    const context = resolveContext(item, inputDir);

    const children = args.noDecompose
      ? null
      : decomposeItem(item, inputDir, context, args.threshold);

    if (children && children.length) {
      decomposedCount++;
      for (const child of children) {
        results.push({
          porting_item_id: child.id,
          parent_id: child.parent_id,
          group: child.group,
          code_range: child.code_range,
          functions: child.functions,
          function_count: child.function_count,
          matches: matchItemAgainstSpecs(child.context, specs),
        });
      }
    } else {
      results.push({
        porting_item_id: item.id || "unknown",
        matches: matchItemAgainstSpecs(context, specs),
      });
    }
  }

  // Write output
  const outputDir = path.dirname(args.output);
  if (!fs.existsSync(outputDir)) {
    fs.mkdirSync(outputDir, { recursive: true });
  }
  fs.writeFileSync(args.output, JSON.stringify({ candidates: results }, null, 2), "utf8");

  const suffix = decomposedCount
    ? ` (${decomposedCount} whole-file item(s) decomposed into per-kernel groups)`
    : "";
  console.log(`Screening complete: ${results.length} items processed, output: ${args.output}${suffix}`);
}

main();

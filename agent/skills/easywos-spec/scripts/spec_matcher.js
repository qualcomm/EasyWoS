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
const crypto = require("crypto");
const yaml = require("js-yaml");

// ---------------------------------------------------------------------------
// Scope pre-classification
// ---------------------------------------------------------------------------

const INSTRUCTION_RE = /^\s*(?:;[^\n]*\n)?\s*(push|pop|mov|add|sub|inc|dec|mul|imul|div|idiv|neg|not|and|or|xor|shl|shr|sar|cmp|test|jmp|je|jne|jz|jnz|jb|ja|jbe|jae|jl|jg|jle|jge|call|ret|nop|lea|movups|movaps|movdqa|movdqu|movu|movhlps|movlhps|lddqu|addps|addss|subps|mulps|divps|shufps|unpcklps|unpckhps|pslld|psrld|psllw|psrlw|psllq|psrlq|pslldq|psrldq|psraw|psrad|por|pand|pandn|pshufb|pshufd|pshuflw|pshufhw|adc|sbb|loop|rep|stp|ldp|ldr|str|bl|b\.\w+|cbz|cbnz|fadd|fmul|fsub|fdiv|faddp|ld1|st1|ext|dup|movq|movd|pxor|paddb|paddw|paddd|paddq|psubb|psubw|psubd|psubq|psadbw|pmaddwd|pmaddubsw|pmulhw|pmulhuw|pmulhrsw|pmullw|pmulld|pmuludq|packuswb|packsswb|packssdw|packusdw|punpcklbw|punpckhbw|punpcklwd|punpckhwd|punpckldq|punpckhdq|punpcklqdq|punpckhqdq|pabsb|pabsw|pabsd|pavgb|pavgw|pmaxsw|pmaxub|pmaxsb|pmaxuw|pmaxsd|pminsw|pminub|pminsb|pminuw|pminsd|pcmpeqb|pcmpeqw|pcmpeqd|pcmpgtb|pcmpgtw|pcmpgtd|pmovmskb|phaddw|phaddd|phsubw|palignr|pblendw|pblendvb|pmull|aese|aesd|aesmc|sha1c|sha1h|sha256h|udot|sdot|usdot|usmmla|uabd|sabd|uadalp|uaddlp|uaddlv|addv|smull2|smlal|smlal2|umull|umull2|uxtl|sxtl|uaddl|uaddl2|saddl|saddl2|uaddw|uaddw2|saddw|saddw2|usubl|usubl2|ssubl|ssubl2|zip1|zip2|uzp1|uzp2|trn1|trn2|sqrshrn|sqrshrun|uqrshrn|srshr|sshr|ushr|sqxtn|sqxtun|uqxtn|xtn|movi|smax|smin|umax|umin)\b/i;

const INTRINSIC_CALL_RE = /_mm(?:256|512)?_\w+\s*\(|v(?:ld1|st1|add|sub|mul|dup|get_lane|set_lane|reinterpret|combine)q?_\w+\s*\(/i;

// A quoted C string literal whose contents are a single AArch64 asm line, as
// emitted by GCC/Clang inline asm: "pmull\tv0.1q, v8.1d, v5.1d\n\t". The
// mnemonic sits just inside the opening quote; operands follow a tab, a
// literal "\t"/"\n", or spaces. Matches the inline-asm instruction stream only,
// NOT ordinary C string literals (which do not begin with an asm mnemonic
// followed by an asm operand separator).
const INLINE_ASM_LINE_RE = /^\s*"\s*(?:ld1|st1|ldp|stp|ldr|str|movi|mov|dup|ext|eor|and|orr|bic|add|sub|shl|ushr|sshr|shrn|rbit|rev\d*|tbl|tbx|zip1|zip2|uzp1|uzp2|trn1|trn2|pmull2|pmull|aese|aesd|aesmc|aesimc|sha1[a-z]*|sha256[a-z]*|cmeq|cmgt|cmhi|umull2|umull|smull2|smull|mul|mla|mls|neg|not|cnt|addv|uaddlv|bsl|zip|ins|smov|umov|fmov)\b[^"]*(?:\\t|\\n|\s)/i;

// The asm-block framing lines: the `asm(`/`__asm__ __volatile__(` opener and
// the `: "+r"(...)`/`: "memory","cc",...` operand/clobber constraint lines.
const INLINE_ASM_FRAME_RE = /^\s*(?:__asm__|asm)\b.*\(|^\s*:\s*(?:\[|"[+=]?r"|"memory"|"cc"|"v\d)/;

const GENERIC_FUNC_CALL_RE = /\b\w+\s*\([^)]*\)/;

const PREPROCESSOR_RE = /^\s*#\s*(include|define|ifdef|ifndef|if|elif|else|endif|pragma|undef)\b/;

const DIRECTIVE_RE = /^\s*\.(globl|global|type|cfi_\w+|text|data|section|align|byte|long|quad)\b/;

const DECLARATION_RE = /^\s*(my\s*\(|(static\s+)?(const\s+)?(unsigned\s+)?(int|float|double|char|void|__m128|__m256|uint\d+_t|int\d+_t)\s+|\$\w+\s*=|(extern|typedef|struct|union|enum)\s)/i;

const COMMENT_RE = /^\s*(;|\/\/|\/\*|\*|#\s*$)/;

function classifyLineScopes(line) {
  const stripped = line.trim();
  if (!stripped) return ["blank"];
  if (COMMENT_RE.test(stripped)) return ["comment"];

  const scopes = new Set();
  if (PREPROCESSOR_RE.test(stripped)) scopes.add("preprocessor");
  if (DIRECTIVE_RE.test(stripped)) scopes.add("directive");
  if (INLINE_ASM_LINE_RE.test(stripped) || INLINE_ASM_FRAME_RE.test(stripped)) scopes.add("inline_asm");
  if (DECLARATION_RE.test(stripped)) scopes.add("declaration");
  if (INTRINSIC_CALL_RE.test(stripped)) {
    scopes.add("intrinsic_call");
    scopes.add("function_call");
  } else if (GENERIC_FUNC_CALL_RE.test(stripped)) {
    scopes.add("function_call");
  }
  if (INSTRUCTION_RE.test(stripped)) scopes.add("instruction");

  // A declaration or call can also contain a matchable expression. Keeping
  // all applicable scopes prevents priority ordering from hiding an intrinsic
  // such as `const int mask = _mm_movemask_epi8(v);` behind "declaration".
  if (!["preprocessor", "directive", "inline_asm", "instruction"].some((s) => scopes.has(s))) {
    scopes.add("expression");
  }
  if (scopes.size === 0) scopes.add("expression");
  return [...scopes];
}

function classifyLine(line) {
  return classifyLineScopes(line)[0];
}

function classifyContext(context, locations = []) {
  return context.split("\n").map((line, index) => ({
    line,
    scopes: classifyLineScopes(line),
    file: locations[index] && locations[index].file ? locations[index].file : null,
    line_number: locations[index] && Number.isInteger(locations[index].line_number)
      ? locations[index].line_number
      : null,
    context_line: index + 1,
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
  expression: new Set(["expression", "instruction", "declaration", "intrinsic_call", "function_call", "inline_asm"]),
  type_or_instance: new Set(["declaration", "expression"]),
  variable_reference: new Set(["expression", "instruction", "declaration"]),
  constant_reference: new Set(["expression", "declaration", "preprocessor"]),
  algorithm_call: new Set(["function_call", "intrinsic_call", "expression"]),
  function_name: new Set(["declaration", "directive", "function_call"]),
  inline_asm: new Set(["inline_asm"]),
};

const ALL_CODE_SCOPES = new Set([
  "instruction", "declaration", "intrinsic_call", "function_call",
  "preprocessor", "directive", "expression", "inline_asm",
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

function lineMatchesRule(rule, line) {
  const pattern = rule.pattern || "";
  const ruleType = rule.type || "regex";

  if (ruleType === "exact" || ruleType === "prefix") return line.includes(pattern);
  const unescaped = unescapePattern(pattern);
  try {
    return new RegExp(unescaped, "m").test(line);
  } catch (e) {
    return line.includes(pattern);
  }
}

function findRuleMatches(rule, classifiedLines) {
  const ruleScope = rule.scope || "";

  const eligible = getEligibleScopes(ruleScope);
  const eligibleLines = classifiedLines.filter((entry) =>
    entry.scopes.some((scope) => eligible.has(scope))
  );

  if (eligibleLines.length === 0) return [];

  const matches = eligibleLines.filter((entry) => lineMatchesRule(rule, entry.line));
  if (matches.length > 0) return matches;

  // Preserve support for the few multiline regex rules in existing specs.
  if ((rule.type || "regex") === "regex") {
    const textBlock = eligibleLines.map((entry) => entry.line).join("\n");
    try {
      if (new RegExp(unescapePattern(rule.pattern || ""), "m").test(textBlock)) {
        return [eligibleLines[0]];
      }
    } catch (e) {
      return [];
    }
  }
  return [];
}

function matchRuleAgainstContext(rule, classifiedLines) {
  return findRuleMatches(rule, classifiedLines).length > 0;
}

function evaluateRuleGroup(group, classifiedLines) {
  const allOf = group.all_of || [];
  const anyOf = group.any_of || [];
  const noneOf = group.none_of || [];
  const allMatches = allOf.map((rule) => ({ rule, hits: findRuleMatches(rule, classifiedLines) }));
  const anyMatches = anyOf.map((rule) => ({ rule, hits: findRuleMatches(rule, classifiedLines) }));
  const noneMatches = noneOf.map((rule) => ({ rule, hits: findRuleMatches(rule, classifiedLines) }));

  const passes = allMatches.every((entry) => entry.hits.length > 0) &&
    (anyMatches.length === 0 || anyMatches.some((entry) => entry.hits.length > 0)) &&
    noneMatches.every((entry) => entry.hits.length === 0);

  return {
    passes,
    positiveMatches: [...allMatches, ...anyMatches].filter((entry) => entry.hits.length > 0),
  };
}

function evidenceForRule(rule, hits, specId, itemId, startIndex, groupId = null) {
  const safeItem = String(itemId || "item").replace(/[^A-Za-z0-9_.-]+/g, "-");
  return hits.map((hit, offset) => ({
    evidence_id: `match-${safeItem}-${specId}-${startIndex + offset + 1}`,
    spec_id: specId,
    rule_id: rule.id || groupId || null,
    group_id: groupId,
    file: hit.file,
    line: hit.line_number,
    context_line: hit.context_line,
    scopes: hit.scopes,
    pattern: rule.pattern || "",
    excerpt: hit.line.trim(),
  }));
}

function matchItemAgainstSpecs(context, specs, locations = [], itemId = "item") {
  const classifiedLines = classifyContext(context, locations);
  const candidates = [];

  for (const spec of specs) {
    const matchRules = (spec.metadata && spec.metadata.match_rules) || [];
    const matchGroups = (spec.metadata && spec.metadata.match_groups) || [];
    let rulesHit = 0;
    const matchedPatterns = [];
    const matchedEvidence = [];

    for (const rule of matchRules) {
      const hits = findRuleMatches(rule, classifiedLines);
      if (hits.length > 0) {
        rulesHit++;
        matchedPatterns.push(rule.pattern || "");
        matchedEvidence.push(...evidenceForRule(
          rule, hits, spec.id, itemId, matchedEvidence.length
        ));
      }
    }

    const matchedGroups = [];
    for (const group of matchGroups) {
      const result = evaluateRuleGroup(group, classifiedLines);
      if (!result.passes) continue;
      matchedGroups.push(group.id || "unnamed-group");
      for (const entry of result.positiveMatches) {
        rulesHit++;
        matchedPatterns.push(entry.rule.pattern || "");
        matchedEvidence.push(...evidenceForRule(
          entry.rule, entry.hits, spec.id, itemId, matchedEvidence.length, group.id || null
        ));
      }
    }

    if (rulesHit > 0) {
      candidates.push({
        spec_id: spec.id,
        spec_name: spec.name || "",
        rules_hit: rulesHit,
        matched_rules: matchedPatterns,
        matched_groups: matchedGroups,
        evidence: matchedEvidence,
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
    const contextLines = [];
    const locations = [];
    members.forEach((k, memberIndex) => {
      const sampleLines = k.sample.split("\n");
      sampleLines.forEach((line, offset) => {
        contextLines.push(line);
        locations.push({ file: item.file_path, line_number: k.start + offset });
      });
      if (memberIndex + 1 < members.length) {
        contextLines.push("; --- variant boundary ---");
        locations.push({ file: item.file_path, line_number: null });
      }
    });
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
      context: contextLines.join("\n"),
      locations,
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
function resolveContextDetailed(item, inputDir) {
  if (item.context) {
    const lines = String(item.context).split("\n");
    let firstLine = null;
    const rangeMatch = /^\s*(\d+)\s*-/.exec(String(item.code_range || ""));
    if (rangeMatch) firstLine = parseInt(rangeMatch[1], 10);
    return {
      context: String(item.context),
      locations: lines.map((line, index) => ({
        file: item.file_path || null,
        line_number: firstLine === null ? null : firstLine + index,
      })),
    };
  }
  if (!item.code_range) {
    return { context: "", locations: [] };
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
  const locations = [];

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
    const selected = lines.slice(start, end);
    if (chunks.length > 0) {
      chunks.push("/* --- code_range segment boundary --- */");
      locations.push({ file: null, line_number: null });
    }
    chunks.push(...selected);
    selected.forEach((line, index) => locations.push({
      file: relPath,
      line_number: start + index + 1,
    }));
  }

  return { context: chunks.join("\n"), locations };
}

function resolveContext(item, inputDir) {
  return resolveContextDetailed(item, inputDir).context;
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
    const resolved = resolveContextDetailed(item, inputDir);
    const context = resolved.context;

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
          matches: matchItemAgainstSpecs(child.context, specs, child.locations, child.id),
        });
      }
    } else {
      results.push({
        porting_item_id: item.id || "unknown",
        matches: matchItemAgainstSpecs(context, specs, resolved.locations, item.id || "unknown"),
      });
    }
  }

  // Write output
  const outputDir = path.dirname(args.output);
  if (!fs.existsSync(outputDir)) {
    fs.mkdirSync(outputDir, { recursive: true });
  }
  const sha256 = (file) => crypto.createHash("sha256").update(fs.readFileSync(file)).digest("hex");
  fs.writeFileSync(args.output, JSON.stringify({
    matcher: {
      schema_version: 1,
      executed_at: new Date().toISOString(),
      script: path.resolve(__filename),
      script_sha256: sha256(__filename),
      input: path.resolve(args.input),
      input_sha256: sha256(args.input),
      specs: path.resolve(args.specs),
      specs_sha256: sha256(args.specs),
    },
    candidates: results,
  }, null, 2), "utf8");

  const suffix = decomposedCount
    ? ` (${decomposedCount} whole-file item(s) decomposed into per-kernel groups)`
    : "";
  console.log(`Screening complete: ${results.length} items processed, output: ${args.output}${suffix}`);
}

if (require.main === module) main();

module.exports = {
  classifyLine,
  classifyLineScopes,
  classifyContext,
  findRuleMatches,
  matchRuleAgainstContext,
  evaluateRuleGroup,
  matchItemAgainstSpecs,
  resolveContext,
  resolveContextDetailed,
  decomposeItem,
  main,
};

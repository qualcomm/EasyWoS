---
name: leaf-skill-creator
description: >-
  Creates new leaf skills for the expert skilltree, or adds missing spec.yaml
  files to existing leaf skills. Enforces the standard directory structure
  (SKILL.md + references/specs/*.md + *.yaml) and guides LLM to auto-generate
  structured spec.yaml files from natural-language spec.md content.
  Two modes: create (new leaf skill) and add-yaml (supplement existing).
tags:
  - leaf-skill
  - scaffold
  - spec-yaml
  - creation
  - arm64
---

# Leaf Skill Creator

## Overview

This skill guides the creation of new leaf skills and the generation of
structured `spec.yaml` files from natural-language `spec.md` content.

**Two modes:**
- **Create mode**: `/leaf-skill-creator <name>` — create a new leaf skill from scratch
- **Add-yaml mode**: `/leaf-skill-creator <name> --add-yaml` — add missing .yaml files to an existing leaf skill

---

## 1. Leaf Skill Standard Directory Structure

Every leaf skill MUST have this structure:

```
skills/<leaf-skill-name>/
├── SKILL.md                          # Skill metadata and general instructions
└── references/
    └── specs/
        ├── <topic-a>.md              # Detailed porting logic for topic A
        ├── <topic-a>.yaml            # Structured matching metadata for topic A
        ├── <topic-b>.md              # Detailed porting logic for topic B
        └── <topic-b>.yaml            # Structured matching metadata for topic B
```

Rules:
- Each `.md` file describes one cohesive set of porting rules (a "dimension")
- Each `.md` MUST have a corresponding `.yaml` with the same basename
- Multiple .md/.yaml pairs are allowed (one per porting dimension)
- The `.md` contains human-readable migration logic organized by section headers
- The `.yaml` contains machine-processable match_rules for the initial screening script

---

## 2. spec.yaml Format Specification

Each `.yaml` file MUST conform to this format (same as `arm64-limitations-spec-list.yaml`):

```yaml
version: "1.0"
generated_from: skills/<leaf-skill-name>/references/specs/<topic>.md
description: >
  <Brief description of this spec set — what porting domain it covers>

specs:
  - id: 1
    name: <kebab-case-spec-name>
    category: <category-tag>
    description: >
      <One-paragraph summary of the migration guidance>
    metadata:
      match_rules:
        - pattern: "<regex, literal, or prefix pattern>"
          type: <regex|exact|prefix>
          scope: <instruction|declaration|intrinsic_call|function_call|preprocessor|directive|expression>
          description: <What this pattern detects>
    x64_constructs:
      - <x64 code pattern or API that triggers this spec>
    arm64_constructs:
      - <ARM64 replacement code or API>
    pitfalls:
      - <Common mistake to avoid during this migration>
    validation_criteria:
      - <How to verify the migration is correct>
```

### Field descriptions

| Field | Required | Description |
|-------|----------|-------------|
| `version` | Yes | Always `"1.0"` |
| `generated_from` | Yes | Path to the source .md file |
| `description` | Yes | What this spec set covers |
| `specs[].id` | Yes | Local integer ID (unique within this file, starts at 1) |
| `specs[].name` | Yes | Kebab-case identifier |
| `specs[].category` | Yes | Grouping tag (e.g., `register-width`, `horizontal-reduction`) |
| `specs[].description` | Yes | Migration guidance summary |
| `specs[].metadata.match_rules` | Yes | Array of patterns for initial screening |
| `specs[].x64_constructs` | Yes | x64 code/APIs that this spec addresses |
| `specs[].arm64_constructs` | Yes | ARM64 replacements |
| `specs[].pitfalls` | Yes | Common migration mistakes |
| `specs[].validation_criteria` | Yes | Verification checks |

### match_rules pattern guidelines

- `type: regex` — Use for flexible pattern matching (escape special chars with `\\`)
- `type: exact` — Use for exact string match (e.g., specific function name)
- `type: prefix` — Use for prefix matching (e.g., `_mm256_` matches all AVX2 intrinsics)
- `scope` — Restricts where the pattern is searched (comment lines are always excluded)

### Keep every spec GENERAL (the rule, not the incident)

A spec exists to guide a **whole class** of future ports, not to record what
happened on one project. Enforce this when writing or extending any spec:

- **`description` states the transferable rule + mechanism** — the x64 construct →
  the ARM64 construct and *why* (the hardware capability or latency/throughput fact
  that drives it). A specific project or measured number is allowed only as a
  one-clause *evidence* citation, never as the rule. Good: "prefer `vcntq_u8` for a
  per-byte popcount — ARM has hardware popcount, unlike pre-AVX512 x86." Overfit:
  "sse-popcount runs 12% faster."
- **`match_rules` fire on the CONSTRUCT, not a codebase** — regex the x86 source
  pattern (e.g. `_mm_mul_epu32`, `_mm_add_ps`, `_mm_cmpestrm`) and a NEON-output
  self-check, so the spec surfaces on *any* project using that construct.
- **Regime-dependent wins state the condition as a decision rule** others can
  evaluate ("estimate+NR wins *when the reciprocal is the loop bottleneck*"), not a
  bare verdict.
- **Do not overfit the magnitude.** Report a measured speedup as an honest
  direction/range with its governing regime; prefer the mechanism over the number
  (a hand-run can inflate a speedup by measuring against a strawman baseline). If
  unsure whether a lesson generalizes, widen it or keep it a candidate in
  `PERF-PROGRESS.md` — an over-narrow spec that only matches your one test case is
  nearly worthless to the next port.

(See `arm64-port-orchestrator/SKILL.md` §8.5 Capture stage for the full promotion
rules — route by kind, verify red→green at the matcher, regenerate the combined
collection.)

---

## 3. Create Mode: `/leaf-skill-creator <name>`

Full flow for creating a new leaf skill:

### Step 1: Create directory structure

```
skills/<name>/
├── SKILL.md
└── references/
    └── specs/
```

### Step 2: Create SKILL.md

Generate skill metadata with name, description, and tags appropriate to the
porting domain.

### Step 3: Create spec .md files

For each porting dimension, create a `.md` file in `references/specs/`.
Each `.md` MUST be organized with one H2 section per spec rule:

```markdown
## <Spec Name>

**x64**: <what the x64 code does>

**ARM64**: <what the ARM64 replacement is>

**Workaround**: <detailed migration steps with code examples>

**Pitfalls**:
- <common mistake 1>

**Validation**:
- <how to verify correctness>
```

### Step 4: Generate .yaml files from .md

For EACH `.md` file in `references/specs/`, generate a corresponding `.yaml`:

1. Read the `.md` file
2. Identify each H2 section as a discrete spec
3. For each spec:
   - `name`: derive kebab-case from section title
   - `category`: infer from content (register-width, intrinsic-mapping, etc.)
   - `description`: summarize the migration guidance in one paragraph
   - `match_rules`: generate patterns that detect the x64 constructs mentioned
   - `x64_constructs`: extract from the "x64" paragraph
   - `arm64_constructs`: extract from the "ARM64" paragraph
   - `pitfalls`: extract from "Pitfalls" section
   - `validation_criteria`: extract from "Validation" section
4. Assign sequential `id` starting from 1
5. Write the `.yaml` file with same basename as the `.md`

### Step 5: Post-creation action

After all .yaml files are generated:

```
Run: node skills/dispatcher-skill/scripts/combine-specs.js
```

This rebuilds the combined spec collection to include the new leaf skill's specs.

---

## 4. Add-Yaml Mode: `/leaf-skill-creator <name> --add-yaml`

For existing leaf skills that have `.md` files but missing corresponding `.yaml`:

### Step 1: Scan references/specs/

List all `.md` files in `skills/<name>/references/specs/`.

### Step 2: Identify missing .yaml files

For each `.md` file, check if a `.yaml` with the same basename exists.
Collect the list of `.md` files that lack a `.yaml` counterpart.

### Step 3: Generate missing .yaml files

For each missing `.yaml`, follow the same generation process as Create Mode Step 4.
Existing `.yaml` files are NOT modified.

### Step 4: Post-creation action

```
Run: node skills/dispatcher-skill/scripts/combine-specs.js
```

---

## 5. Example: arm64-limitations.md → arm64-limitations.yaml

**Source** (excerpt from `skills/intrinsics-x64-to-arm64/references/specs/arm64-limitations.md`):

```markdown
## No 256-bit Registers

**x64**: `__m256i` processes 32 bytes in a single register.

**ARM64**: Maximum native width is 128-bit. No 256-bit register.

**Workaround**: Use 4 × 128-bit registers per loop iteration (64 bytes).

**Pitfalls**:
- Do NOT use a single 128-bit register — throughput will halve

**Validation**:
- ARM64 loop processes >= 64 bytes per iteration
- No __m256i or _mm256_* remain in ARM64 path
```

**Generated** (excerpt from `arm64-limitations.yaml`):

```yaml
version: "1.0"
generated_from: skills/intrinsics-x64-to-arm64/references/specs/arm64-limitations.md
description: >
  ARM64 NEON limitations and workarounds for SSE/AVX patterns.

specs:
  - id: 1
    name: no-256-bit-registers
    category: register-width
    description: >
      ARM64 NEON maximum native width is 128-bit. No 256-bit register exists.
      Use 4x128-bit registers per iteration (64 bytes) to match AVX2 throughput.
    metadata:
      match_rules:
        - pattern: "\\b__m256i\\b"
          type: regex
          scope: declaration
          description: Any use of 256-bit integer register type
        - pattern: "\\b__m256d?\\b"
          type: regex
          scope: declaration
          description: Any use of 256-bit float register type
        - pattern: "_mm256_"
          type: prefix
          scope: intrinsic_call
          description: Any AVX2 256-bit intrinsic function call
    x64_constructs:
      - __m256i
      - _mm256_loadu_si256
      - _mm256_storeu_si256
    arm64_constructs:
      - "4 x uint8x16_t (or typed equivalent)"
      - "vld1q_u8(ptr + 0/16/32/48)"
    pitfalls:
      - Do NOT use a single 128-bit register to replace 256-bit — throughput will halve
    validation_criteria:
      - ARM64 main loop processes >= 64 bytes per iteration (4 x vld1q_u8)
      - No __m256i or _mm256_* intrinsics remain in ARM64 code path
```

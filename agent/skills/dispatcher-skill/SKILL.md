---
name: dispatcher-skill
description: >-
  Expert skilltree layer-1 dispatcher. Receives porting task commands from
  tasks.md, parses arguments, loads porting_item data and spec descriptions,
  then routes to the appropriate leaf skill for actual migration execution.
  Invoked as: /dispatcher-skill <porting_item_id> --specs <ids> --source <path>
  or /dispatcher-skill <porting_item_id> --mode llm-freeform --source <path>.
  Does NOT contain migration logic itself — only routing and data assembly.
tags:
  - dispatcher
  - skilltree
  - routing
  - arm64
  - porting
---

# Dispatcher Skill: Expert Skilltree Layer-1

## Overview

This skill is the routing layer of the expert skilltree. It receives porting
commands from tasks.md, loads the relevant data, and dispatches to the correct
leaf skill for execution.

```
tasks.md command → Dispatcher (parse + load + route) → Leaf Skill (execute migration)
```

---

## 1. Argument Parsing

### 1.1 Invocation format

**Standard (with matched specs):**
```
/dispatcher-skill <porting_item_id> --specs <comma-separated-spec-ids> --source <matched-yaml-path>
```

**No match (freeform):**
```
/dispatcher-skill <porting_item_id> --mode llm-freeform --source <matched-yaml-path>
```

### 1.2 Parameter extraction

| Parameter | Required | Description |
|-----------|----------|-------------|
| `<porting_item_id>` | Yes | ID of the porting_item to process (first positional arg) |
| `--specs <ids>` | One of specs/mode | Comma-separated global spec IDs from combined collection |
| `--mode llm-freeform` | One of specs/mode | Freeform mode (no spec matched) |
| `--source <path>` | Yes | Path to the matched YAML file |

### 1.3 Validation rules

1. `porting_item_id` MUST be present (first argument)
2. `--source` MUST be present
3. Exactly ONE of `--specs` or `--mode` MUST be present (mutually exclusive)
4. If `--specs` is present, value must be non-empty comma-separated integers
5. If validation fails, report error and stop

---

## 2. Data Loading & Assembly

### 2.1 Load porting_item from matched YAML

1. Read the file at `--source` path
2. Find the porting_item whose `id` matches `<porting_item_id>`
3. Extract: `context`, `semantics`, `constraints`, `register_mapping`, `code_range`, `match_confidence`
4. If not found → report error: "porting_item '<id>' not found in <source>"

### 2.2 Resolve spec routing via combined collection

For each spec_id in `--specs`:

1. Read `skills/combined-spec-summary.yaml`
2. Find the spec entry with matching global `id`
3. Extract three routing fields:
   - `source` → leaf skill directory name (e.g., `"intrinsics-x64-to-arm64"`)
   - `source_sub_dimension` → file pair basename (e.g., `"arm64-limitations"`)
   - `source_id` → local spec id within that file

### 2.3 Load spec description from leaf skill yaml

For each resolved spec:

1. Locate: `skills/<source>/references/specs/<source_sub_dimension>.yaml`
2. Find the spec entry with `id` == `source_id`
3. Extract: `name`, `description`, `x64_constructs`, `arm64_constructs`, `pitfalls`, `validation_criteria`

### 2.4 Load porting logic from leaf skill md

For each resolved spec:

1. Locate: `skills/<source>/references/specs/<source_sub_dimension>.md`
2. Find the markdown section corresponding to the spec name
3. Extract the full section content as `porting_logic`

### 2.5 Assemble data contract

Combine all loaded data into the standardized contract:

```yaml
porting_item:
  id: <porting_item_id>
  context: <source code from matched YAML>
  semantics: <description>
  constraints: <list>
  register_mapping: <mapping>
  code_range: <range>

matched_specs:
  - id: <global_spec_id>
    name: <spec_name>
    source: <leaf-skill-name>
    source_sub_dimension: <file-basename>
    source_id: <local-id>
    description: <spec description from yaml>
    porting_logic: <detailed migration guidance from md>

match_confidence:
  rules_hit: <count>
  scope_verified: <bool>
  llm_confidence: <level>
```

### 2.6 Freeform mode data contract

When `--mode llm-freeform`:

```yaml
porting_item:
  id: <porting_item_id>
  context: <source code>
  semantics: <description>
  constraints: <list>
  register_mapping: <mapping>
  code_range: <range>

matched_specs: []

directive: Load arm64-baseline-porting skill as constraint framework
```

---

## 3. Routing Logic

### 3.1 Route via source field

`source` → leaf skill directory: `skills/<source>/`

### 3.2 Route via source_sub_dimension

`source_sub_dimension` → file pair:
- `skills/<source>/references/specs/<source_sub_dimension>.yaml`
- `skills/<source>/references/specs/<source_sub_dimension>.md`

### 3.3 Freeform mode routing

When `--mode llm-freeform`:
- Load `skills/arm64-baseline-porting/SKILL.md`
- Apply all baseline constraints (16-byte alignment, flag discipline, etc.)
- Execute migration using LLM's own knowledge within those constraints

### 3.4 Inline asm detection override

Before routing, check if `porting_item.context` contains `__asm` or `__asm__`:
- If YES → override routing to `skills/arm64-inlineasm-to-intrinsics/` regardless of spec mapping
- Pass the original matched_specs as supplementary context

### 3.5 Leaf skill not found fallback

If the resolved `source` leaf skill directory does not exist:
- Log warning: "Leaf skill '<source>' not found, falling back to baseline"
- Execute as freeform mode with `arm64-baseline-porting` constraints
- Pass the spec `description` and `porting_logic` as supplementary guidance

---

## 4. Multi-Spec Combination

### 4.1 Same source — merge

When multiple spec_ids resolve to the same `source` (same leaf skill):
- Combine all porting_logic sections into `matched_specs` array
- Route to that single leaf skill with all specs as context

### 4.2 Cross-source — primary selection

When spec_ids resolve to different `source` values:
1. Group specs by `source`
2. Select primary: the source group with highest total `rules_hit` (from match_confidence)
3. Route to primary leaf skill
4. Include non-primary specs in `matched_specs` as supplementary guidance (marked as `supplementary: true`)

---

## 5. Confidence & Output

### 5.1 Normal output

After leaf skill executes, output the ARM64 code directly.

### 5.2 Low confidence handling

If `match_confidence.llm_confidence` == `"low"`:
- Execute routing and migration normally
- Append to output: `\n\n[NEEDS REVIEW] — Low confidence match. Human verification recommended.`

### 5.3 Error handling

| Error | Action |
|-------|--------|
| porting_item not found in source YAML | Report error, stop |
| Spec ID not found in combined collection | Report error, stop |
| Leaf skill directory missing | Fallback to baseline (Section 3.5) |
| spec.yaml file missing in leaf skill | Fallback to baseline, log warning |
| spec.md section not found | Use yaml description only, log warning |

---

## 6. Spec Collection Management

The combined spec collection at `skills/combined-spec-summary.yaml` is generated by:

```bash
node skills/dispatcher-skill/scripts/combine-specs.js
```

**MUST be re-run when:**
- A new leaf skill is created (with new `references/specs/*.yaml` files)
- Any existing leaf skill's `*.yaml` file is modified
- After running `leaf-skill-creator` in either create or add-yaml mode

The script scans `skills/*/references/specs/*.yaml` and aggregates all specs
with globally unique IDs, preserving `source`, `source_sub_dimension`, and `source_id`.

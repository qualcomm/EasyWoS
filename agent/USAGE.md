# easywos-skills — Usage Guide

Expert Agent Skills for porting x86/x64 code to **Windows on Snapdragon (ARM64 / ARM64EC)**.

This repo is a *skilltree*: a thin orchestration layer that turns an EasyWoS scan
of an x64 codebase into an executable, spec-matched porting plan, plus a library
of leaf skills that do the actual x64→ARM64 translation. The skills are consumed
by an AI coding agent (Claude Code / Claude Agent SDK) — you point the agent at
your code, and the skills supply the routing, the migration recipes, and the
verification workflow.

---

## 1. What's in here

```
easywos-skills/
├── skills/
│   ├── easywos-spec/            # ORCHESTRATOR: scan YAML → matched YAML → tasks.md
│   ├── dispatcher-skill/        # ROUTER (layer-1): tasks.md command → leaf skill
│   ├── arm64-baseline-porting/  # FALLBACK: ARM64 invariants for freeform/no-match
│   │
│   │   # ── leaf skills (the actual migration recipes) ──
│   ├── sse-avx-to-neon/             # SSE/AVX intrinsics → NEON; CRC32 PCLMULQDQ → PMULL
│   ├── intrinsics-x64-to-arm64/     # SSE/AVX C++ → NEON, guard/limitation hygiene
│   ├── asm-x64-to-arm64/            # x64 asm (inline + MASM .asm) → AArch64
│   ├── arm64-inlineasm-to-intrinsics/  # ARM64 NEON inline asm → C intrinsics + gtest
│   ├── enable-windows-arm64/        # add ARM64 configs to a project's build system
│   ├── jit-arm64ec-virtualalloc-fix-skill/  # ARM64EC JIT code-page allocation bug
│   │
│   │   # ── authoring / reporting ──
│   ├── arm64-porting-report/        # generate the EasyWoS-style porting YAML
│   ├── leaf-skill-creator/          # scaffold a new leaf skill (+ spec.yaml)
│   │
│   └── combined-spec-summary.yaml   # GENERATED index of all leaf specs (gitignored)
└── README.md / USAGE.md
```

Two roles:

- **Orchestration** (`easywos-spec`, `dispatcher-skill`, `arm64-baseline-porting`)
  decides *what* to port and *which recipe* to use. It does not contain
  migration logic.
- **Leaf skills** own the migration logic. Each holds one or more *specs* — a
  matched `.yaml` (machine-readable: match rules, x64/arm64 constructs,
  pitfalls, validation) and a `.md` (the human/agent-readable recipe).

---

## 2. Install

The skills are loaded from a Claude Code skills directory. Install all skills
from this repo with:

```bash
npx skills add https://github.com/qualcomm/easywos-skills.git
```

Re-run after the repo updates to pick up new/changed specs.

### Prerequisites

| For | You need |
|-----|----------|
| Running the pipeline scripts | Node.js (the `scripts/` use `js-yaml`; `npm install` in `skills/easywos-spec/scripts/`) |
| Orchestration with OpenSpec | OpenSpec CLI (`openspec`), and the activation rule wired in `openspec/config.yaml` |
| Building/verifying ARM64 output | A native ARM64 host (Windows on ARM, or aarch64 Linux), MSVC ARM64 toolchain (VS 2019+) or GCC/Clang, CMake 3.14+ |

One-time environment check for the OpenSpec integration:

```bash
node skills/easywos-spec/scripts/setup.js
```

This verifies `js-yaml`, validates the spec collection, ensures
`openspec/config.yaml` has the easywos-spec activation rule, and sanity-checks
the matcher.

---

## 3. The pipeline (the main workflow)

```
EasyWoS scan YAML
   │  ① arm64-porting-report  (produce the scan, if you don't have one)
   ▼
easywos-spec orchestrator
   │  ② preflight   – verify leaf skills present; regenerate combined-spec-summary.yaml
   │  ③ script screening   – spec_matcher.js: regex-match each item's x64 source vs every spec
   │  ④ LLM refinement     – prune false positives, split variant_groups, assign confidence
   │  ▼
   <name>-matched.yaml      – original scan + port_spec_ids + match_confidence per item
   │  ⑤ tasks.md generation – one /dispatcher-skill command per porting item
   ▼
dispatcher-skill (per item)
   │  ⑥ load porting_item + resolve specs → route to leaf skill(s)
   ▼
leaf skill  → ARM64 source output (C/intrinsics or .asm)
   │  ⑦ unit-test verification (gtest + CMake + build/run)
   ▼
verified ARM64 port
```

### Step by step

**① Get a scan.** If you don't already have an EasyWoS porting YAML, ask the
agent to generate one (`arm64-porting-report` skill): it inventories the x64
hot kernels into `porting_items` with `file_path`, `code_range`, `semantics`,
`constraints`, and (for fast-path families) `variant_group` / `target_feature`.

**②–⑤ Run the orchestrator.** With OpenSpec, the easywos-spec skill fires when
`tasks.md` is generated for a change (wired via `openspec/config.yaml`
`rules.tasks`). It:

- runs a **dependency preflight** (and regenerates the generated spec index —
  see §4);
- runs **script screening** — `spec_matcher.js` scope-classifies each item's
  resolved source and regex-matches it against every spec's `match_rules`,
  emitting a candidate list;
- performs **LLM semantic refinement** — drops scope/semantic false positives,
  collapses redundant specs, splits `variant_group` items by `target_feature`,
  and assigns `port_spec_ids` + `match_confidence` (high/medium/low; low →
  `[NEEDS REVIEW]`);
- writes **`<scan>-matched.yaml`** (the scan augmented per item), then a
  **`tasks.md`** whose "Dispatcher Execution" section has one command per item.

You can also run the matcher directly:

```bash
node skills/easywos-spec/scripts/spec_matcher.js \
  --input  <scan.yaml> \
  --specs  skills/combined-spec-summary.yaml \
  --output candidates.json
```

**⑥ Dispatch.** Each tasks.md line is a dispatcher invocation:

```bash
# matched item (one or more specs)
/dispatcher-skill <item-id> --specs 86,87,90 --source <scan>-matched.yaml
# unmatched item
/dispatcher-skill <item-id> --mode llm-freeform --source <scan>-matched.yaml
```

The dispatcher loads the porting item, resolves each spec id via
`combined-spec-summary.yaml` to its leaf skill + file, loads that recipe, and
routes (multi-spec merge, cross-source primary selection, inline-asm override,
or baseline fallback). It contains no migration logic itself.

**⑦ Verify.** After the leaf skills emit ARM64 source, the unit-test workflow
generates gtest fixtures (one per item), a clean-C-ABI test seam, CMake, and a
build/run script. Two flows — intrinsics (`references/unit-test-workflow-intrinsics.md`)
and assembly (`references/unit-test-workflow.md`) — selected by the leaf-skill
output language. Templates live under `skills/easywos-spec/references/`.

---

## 4. The generated spec index

`skills/combined-spec-summary.yaml` is **generated**, not hand-edited (it is
gitignored). It aggregates every leaf skill's `references/specs/*.yaml` into one
table with globally unique ids and `source` / `source_sub_dimension` /
`source_id` routing fields. Regenerate it whenever specs change:

```bash
node skills/dispatcher-skill/scripts/combine-specs.js
```

Re-run after: creating a leaf skill, editing any leaf `*.yaml`, or running
`leaf-skill-creator`. The dispatcher and the matcher both read this file, so a
stale index means stale routing.

---

## 5. Using a single skill directly (without the full pipeline)

You don't have to run the whole pipeline. Each skill is independently useful —
just describe the task and the matching skill activates:

- *"Port this SSE kernel to NEON"* → `sse-avx-to-neon` / `intrinsics-x64-to-arm64`
- *"Translate this MASM .asm to AArch64"* → `asm-x64-to-arm64`
- *"Rewrite this ARM64 inline asm block as intrinsics, with a gtest"* → `arm64-inlineasm-to-intrinsics`
- *"Add ARM64 support to this CMake/VS project"* → `enable-windows-arm64`
- *"Generate an ARM64 porting report for this repo"* → `arm64-porting-report`
- *"This ARM64EC JIT is allocating code pages wrong"* → `jit-arm64ec-virtualalloc-fix-skill`

When no specific spec matches, `arm64-baseline-porting` supplies the mandatory
ARM64 invariants (Windows ARM64 ABI, weak memory ordering, 128-bit NEON width,
ARM64EC shims, short-buffer/tail guards, MSVC intrinsic portability) so freeform
output still stays correct.

---

## 6. Anatomy of a leaf skill (and how to add one)

```
skills/<leaf-skill>/
├── SKILL.md                    # when-to-use + the recipe overview
└── references/specs/
    ├── <dimension>.md          # human/agent recipe for a group of specs
    └── <dimension>.yaml        # machine-readable: each spec's match_rules,
                                #   x64_constructs, arm64_constructs,
                                #   pitfalls, validation_criteria
```

Keep the `.md` and `.yaml` in 1:1 correspondence. The `.yaml` `match_rules`
must key on **x86 source** patterns (the matcher screens the source, not the
not-yet-written ARM output) — a rule that matches only NEON output never fires.

Scaffold a new one with the `leaf-skill-creator` skill (create mode), or add a
missing `spec.yaml` to an existing skill (add-yaml mode). Then regenerate the
combined index (§4).

---

## 7. Conventions & gotchas

- **`combined-spec-summary.yaml` is generated** — never edit by hand; regenerate
  after spec changes.
- **Match rules target x86 source.** If a spec's purpose is a performance/output
  pattern, it still needs an x86-source trigger or it will match zero items.
- **`variant_group` items share source bytes.** The screener can't distinguish a
  `+crc` baseline from a `+pmull` fast path (same source); LLM refinement splits
  them by `target_feature`.
- **Low confidence → `[NEEDS REVIEW]`.** Those items are dispatched but flagged
  for human verification.
- **ARM64 output must build on MSVC, not just clang.** Mind MSVC-only pitfalls
  (NEON brace-init, `poly64_t`/`poly128_t`, `vmull_p64` lane form, no
  `<arm_acle.h>`); SVE2 is unsupported on MSVC. See `arm64-baseline-porting`.
- **Short-buffer guards.** Fixed-stride SIMD kernels must guard `len < STRIDE`
  before any unconditional vector load, or short inputs read OOB / underflow
  `size_t` → segfault.

---

## 8. Reference material

- **End-to-end demos:** `skills/easywos-spec/demo/` (incl. a full zlib-ng
  porting record) and `references/demo-without-openspec.md`.
- **Output formats & templates:** `skills/easywos-spec/references/`
  (`matched-yaml-example.md`, `script-output-format.md`, CMake / build-script /
  unit-test workflow templates).
- **Orchestration contracts:** `skills/easywos-spec/SKILL.md` (pipeline) and
  `skills/dispatcher-skill/SKILL.md` (routing protocol).

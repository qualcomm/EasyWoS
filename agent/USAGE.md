# easywos-skills — Usage Guide

Expert Agent Skills for porting x86/x64 code to **Windows on Snapdragon (ARM64 / ARM64EC)**.

**EasyWoS is an end-to-end porting solution, not a collection of one-off
converters.** It takes a project from *un-analyzed x64 source* to a *ported,
verified, measured ARM64 build* — and every stage in between is part of the
product:

```
scan → plan → route → port → verify → integrate → build → test → fix → profile → optimize → capture
```

You do not have to know which kernels need porting, which recipe applies, how to
test the result, or whether the result is actually faster. The pipeline answers
each of those in turn, and refuses to advance on an unverified stage: a fixture
that was never seen failing does not count as passing, and a kernel that is
correct but slower than the code it replaced is treated as a defect, not a
delivery.

### How to read this document

- **§1–§8 are what a user needs**: scope, benefits, model status, install, quick
  start, single-skill use, profiling, FAQ. If you only want to port a project,
  stop after §8.
- **§9–§14 are the internals**: repo layout, what the pipeline does inside, the
  generated spec index, how to add a skill, the gotcha list. Read these when you
  want to extend EasyWoS, debug routing, or contribute a spec.

---

## 1. Scope: when EasyWoS is the right tool

The one-line test: if you can paste the code into an LLM and get back a port
you're satisfied with in one shot, you don't need EasyWoS. EasyWoS is aimed at
complex ports — the "I can't trust this even though it looks fine" case, where the
result looks right, compiles, even passes unit tests, but is either wrong or
correct-yet-slower than the code it replaced.

### Where it fits (the complex cases)

| Case | Why a pipeline beats asking a model |
|------|-------------------------------------|
| **x64 assembly porting** (inline `__asm` / MASM `.asm` → AArch64) | Semantics, flags, calling convention, and parallelism width all have to line up. The common failure here isn't a compile error — it's a silently narrowed register width that no correctness check catches. |
| **x64 intrinsics porting** (SSE/AVX/AVX2 → NEON) | Many x86 instructions have **no one-to-one NEON mapping**: `movemask`, `pcmpestrm`, `gather`, `mulhi`, `pshufb`'s zeroing semantics, `palignr`, and more. Each class has an established recipe; a lookup table won't do it. |
| **Dense detail that improvisation always gets wrong** | The two x64 ABI variants, carry-flag polarity, addressing modes, MASM dialect, guard patterns (many interlocking rules — not a table lookup). |
| **What functional tests can't catch** | Memory ordering / atomics, narrowed parallelism width, a silent scalar fallback where no ARM path exists (unit tests all green; the defect only shows up under threading or in the profile). |
| **Headroom worth going after** | DotProd/i8mm dispatch, NEON performance patterns, the profiling loop (not "is the port correct" but "can it still be faster"). |

### Where it doesn't fit

- Plain C/C++ with no architecture dependency. Just build it with another toolchain.
- A handful of genuinely one-to-one intrinsics, e.g. `_mm_add_ps` → `vaddq_f32`.
- A single isolated function whose output you can review yourself.
- Looking up what one x86 instruction maps to on ARM64. That's a question, not a pipeline.

A rough size heuristic: for a simple project, a port that touches only a few
functions, or straightforward call relationships, the pipeline usually costs more
than it returns. Once assembly, hard instructions, or "I need to prove to someone
that this port is correct and faster" enter the picture, use the pipeline.

---

## 2. What you get out of it

### Benefit 1: a port you're willing to ship

The pipeline puts hard gates in two places, and this is the real difference from
asking a model:

- **The negative-control gate** — a fixture only counts once it has been observed
  going **red**. A green that was never seen failing is treated as unverified,
  because an always-green test may not be running at all.
- **The performance gate** — a correct-but-slower kernel is a **defect**, not a
  delivery. The comparison baseline must be the real fallback build, not a
  hand-written naive version.

In practice these gates have caught several classes of problem that correctness
tests miss — e.g. `_mm_shuffle_epi8` and `vqtbl1q` zero on different conditions
(behavior diverges for indices 16–127), and libraries that have no SIMD path at
all on ARM64 and silently fall back to scalar.

### Benefit 2: lessons accumulate instead of starting over

Every confirmed lesson gets written back into a leaf spec
(`references/specs/*.yaml` / `.md`). The matcher on your next project hits that
spec directly, so **you don't step in the same hole twice**. That's the
difference between a skilltree and re-asking: ask a model and you get the quality
of this one conversation; run the pipeline and you get everything every previous
run has deposited.

Examples already captured in specs (all measured, not inferred):

- Hard instructions: for something like `pcmpestrm` with **no NEON equivalent**,
  the right move is to **substitute the algorithm**, not emulate the instruction.
- Native instructions: for `popcount` or 64-bit multiply-high, ARM64's native
  instructions (`vcntq_u8`, `UMULH`) beat a faithful transliteration of x86's
  shuffle-LUT or four-`vmull` approach.
- Dependency chains: a single-accumulator float reduction is **latency-bound** and
  should be split into several independent accumulators with `vfmaq_f32`.
- Trade-offs: whether `vrsqrte` + Newton iteration beats full-precision
  `vsqrtq`/`vdivq` **depends on whether it's the bottleneck** — we have measured
  data both ways, so the spec states the criterion rather than a slogan.

### Benefit 3: reproducible, auditable artifacts

One run leaves behind: the scan YAML → `-matched.yaml` (with `port_spec_ids` and
confidence) → `tasks.md` → a gtest fixture per kernel → profiling reports (flame
graph + HTML). Progress is recorded under `openspec/changes/<change-name>/`, so an
interrupted run resumes. This is what lets you **show** someone why the port is
correct and why it's faster, instead of saying "the model wrote it this way."

### Benefit 4: low confidence is surfaced, not buried

Low-confidence matches are still dispatched, but tagged `[NEEDS REVIEW]`. Missing
dependencies, toolchain gaps, ambiguous build commands, and non-converging loops
**stop unconditionally and cannot be suppressed**. The pipeline would rather stop
and ask than guess — because guessing in exactly those spots produces the
plausible-looking wrong port.

---

## 3. Model support today

EasyWoS is **skills + orchestration logic**; the model is a swappable runtime. The
skill content is Markdown and YAML and binds to no particular model API.

| Item | Status |
|----|------|
| Validated today | **Claude Code + Opus**, **Codex + GPT**, and **OpenCode + DeepSeek**. End-to-end runs, spec capture, and measurements have been produced on all three harness/model pairs. |
| What the model needs | Long context — the scan YAML, spec recipes, and source have to fit together, and 1M context is recommended; reliable tool use (read/write files, run builds, run tests, run profiles); and enough instruction-following to hold the "don't claim it unverified" line. **Models with weak tool use fail in the outer build→test→fix loop**, not at translation. |
| Planned next | We are actively trying more harness/model pairs; **Qwen + Qwen Code** and **Kimi K3 + Kimi Code** are next up for validation. |
| What changing models costs | Nothing in the skill content. But every agent harness has its own preferences and defaults, so harnesses can diverge in how they call tools and how they honor the flow and rules EasyWoS defines. Supporting a new harness therefore means adjusting some of EasyWoS's design rules to match it. |

> To be clear: harness/model pairs beyond the three validated above — including
> Qwen + Qwen Code and Kimi K3 + Kimi Code — have **not been tested yet**. The
> "planned next" row is a roadmap, not a result. We'll fill in actual findings
> here once those end-to-end runs are done.

---

## 4. Install

The skills are loaded from a Claude Code skills directory. This repo now lives
as a subdirectory inside the `qualcomm/EasyWoS` repo, at `agent/` (i.e.
`agent/skills/...`), so install with a subpath pointing at that directory.
`--all` installs every skill to every detected agent without the per-skill
confirmation prompts:

```bash
npx skills add qualcomm/EasyWoS/agent --all
```

Equivalently, with a full URL:

```bash
npx skills add https://github.com/qualcomm/EasyWoS/tree/main/agent --all
```

To install everything but restrict which agent it's installed to (e.g. only
Claude Code), use `-s "*" -a claude-code -y` instead of `--all`. Use double
quotes, not single quotes — `cmd.exe` does not strip single quotes, so `-s '*'`
is passed through literally and matches no skill.

Re-run after the repo updates to pick up new/changed specs.

### Prerequisites

| For | You need |
|-----|----------|
| Running the pipeline scripts | Node.js (the `scripts/` use `js-yaml`; `npm install` in `skills/easywos-spec/scripts/`) |
| Orchestration with OpenSpec | OpenSpec CLI (`openspec`), and the activation rule wired in `openspec/config.yaml` |
| Building/verifying ARM64 output | A native ARM64 host (Windows on ARM, or aarch64 Linux), MSVC ARM64 toolchain (VS 2019+) or GCC/Clang, CMake 3.14+ |
| Profiling (`skillsthe profiling skills under /`) | Python 3.8+; an **elevated shell** for `etl-generator` only (kernel CPU sampling needs the NT Kernel Logger); Node.js to serve the interactive flame graph |

---

## 5. Quick start — port a whole project

You interact with EasyWoS by **talking to the agent**, not by running scripts (the
scripts in §11 exist for debugging). One command drives everything — scan, plan,
port, verify, integrate, build, run the project's own tests, fix, profile,
archive:

```
/arm64-port-orchestrator C:/src/my-project
```

That is the whole invocation. Everything beyond it is optional tuning, documented
in the skill's own §0.

- **End-to-end execution** follows the flow below, with no human intervention
  needed unless it hits something it cannot judge on its own.

  ```
  scan → plan → route → port → verify → integrate → build → test → fix → profile → optimize → capture
  ```

- **Unconditional stops**: a missing dependency, a toolchain gap, an ambiguous
  build/test command, a loop that will not converge. Those stops are **not
  suppressible**, because guessing there produces a plausible-looking wrong port.
  If a run is interrupted, it can resume from the phase it reached — progress is
  recorded under `openspec/changes/<change-name>/`.

**What the user needs to supply:** the pipeline is autonomous about method, but it
will not guess at facts it cannot observe. Have these ready, or expect to be asked:

- **How to build and test for ARM64**, when it cannot be auto-detected. If the
  project has no ARM64 configuration at all, say so — `enable-windows-arm64` adds
  one.
- **A terminating workload**, if you want the performance loop. A server that
  never exits cannot be profiled directly (see §7).
- **An ARM64 host.** Cross-compiling is fine, but the verification gtests and the
  profile must execute on ARM64.

Smaller entry points also exist — dispatch individual kernels from a scan you
already have, port one piece of code with a single leaf skill (§6), or just
profile a binary (§7).

---

## 6. Using a single skill directly (without the full pipeline)

You don't have to run the whole pipeline. Each skill is independently useful —
just describe the task and the matching skill activates:

- *"Port this SSE kernel to NEON"* → `sse-avx-to-neon` / `intrinsics-x64-to-arm64`
- *"Translate this MASM .asm to AArch64"* → `asm-x64-to-arm64`
- *"Rewrite this ARM64 inline asm block as intrinsics, with a gtest"* → `arm64-inlineasm-to-intrinsics`
- *"Add ARM64 support to this CMake/VS project"* → `enable-windows-arm64`
- *"Generate an ARM64 porting report for this repo"* → `arm64-porting-report`
- *"This ARM64EC JIT is allocating code pages wrong"* → `jit-arm64ec-virtualalloc-fix-skill`
- *"Profile this program and tell me where the CPU goes"* → `skillsthe profiling skills under /` (see §7)

When no specific spec matches, `arm64-baseline-porting` supplies the mandatory
ARM64 invariants (Windows ARM64 ABI, weak memory ordering, 128-bit NEON width,
ARM64EC shims, short-buffer/tail guards, MSVC intrinsic portability) so freeform
output still stays correct.

---

## 7. The profiling pipeline

```
etl-generator  →  perf-sampling-parser  →  perf-optimizer
  (capture)         (per-process CPU +        (root-cause + source scan +
                     speedscope export)        HTML report)
```

| Skill | Role |
|-------|------|
| `etl-generator` | Run a target program under PerfView's CPU sampler → merged `.etl`. **Needs an elevated shell.** |
| `perf-sampling-parser` | Parse an `.etl`: rank processes by CPU, export a SpeedScope flame graph for the chosen process(es). |
| `perf-optimizer` | Attribute hot leaves to the true root-cause module, scan the source for x64-SIMD/ARM64-NEON gaps, assemble an HTML report. |

`perf-optimizer` invokes `perf-sampling-parser` automatically when handed an
`.etl` instead of a SpeedScope JSON; `perf-sampling-parser` and `etl-generator`
share the bundled `PerfView.exe`. The suite vendors PerfView + TraceEvent and a
speedscope web bundle — see `skills/PROFILING-THIRD-PARTY-NOTICES.md`.

Two things worth knowing before trusting a profile:

- **PerfView's `run` verb stops when the target exits**, so a long-running server
  cannot be profiled directly. Kernel CPU sampling is system-wide: profile a
  wrapper that *does* exit, and the server's stacks are captured anyway.
- **A symbol missing from the flame graph proves nothing.** It conflates
  never-called, inlined, renamed, and unsymbolized. To claim a port removed a hot
  spot, profile the **pre-port** build on a workload that actually exercises the
  kernel.

---

## 8. FAQ for new users

**Q: Do I need an ARM64 machine?**
Cross-compiling is fine, but **the verification gtests and the profiling must run
on real ARM64**. Without an ARM64 host you can still get the ported output — you
just can't get the "verified" conclusion.

**Q: Does profiling require admin rights?**
Only `etl-generator` does — kernel CPU sampling goes through the NT Kernel Logger.
Parsing and reporting don't.

**Q: Is OpenSpec required?**
No. OpenSpec orchestrates changes and records progress; you can run without it —
see `skills/easywos-spec/references/demo-without-openspec.md`.

**Q: I only want to port one function. Do I have to run the whole pipeline?**
No. Every skill can be invoked on its own (§6); just describe the task.

**Q: The matcher matched zero specs. Is a spec missing?**
Check the **warnings** first. Something like `code_range exceeds bounds` means the
screened source may not be the code you think it is — the zero-match is a bad
range, not a spec gap. Clear the warnings before concluding anything.

**Q: The matcher matched *everything*, so the result is useless.**
That's the signature of a whole-file assembly item being screened as one blob — a
large file trips nearly every spec somewhere. Decomposition normally prevents it
(§10). If it didn't fire, check whether the item sets `segment: false`, whether
`--no-decompose` was passed, or whether the file is under the 400-line threshold.

**Q: One kernel fails its gtest. Does the whole run stop?**
No. The item gets a feedback file and is re-dispatched to the same leaf skill, up
to a retry budget; if it still fails it is marked for review and the rest of the
batch proceeds (§10, step ⑦′).

**Q: Is EasyWoS Windows-only, or does Linux/aarch64 work?**
The porting recipes are OS-agnostic and build verification works on both Windows
ARM64 and aarch64 Linux. But **the profiling pipeline is Windows-only** (it's
built on PerfView / ETW).

**Q: Does the output really have to build on MSVC?**
Yes — passing on clang alone isn't enough. Mind the MSVC-only pitfalls: NEON
brace-init, `poly64_t` / `poly128_t`, `vmull_p64`'s lane form, no
`<arm_acle.h>`, no SVE2. Also, `clang-cl` defines `_MSC_VER`, so
`#if defined(_MSC_VER)` alone does not identify real MSVC.

**Q: Why must the port come from a leaf skill instead of the agent writing it?**
Because the "spec-driven → profile → fix-the-spec" loop depends on it. When
hand-written output goes wrong, you can't tell a **spec gap** apart from a
**one-off coding slip**, and the lesson never accumulates (see §2, Benefit 2).

**Q: My target is a long-running service, so I can't profile it. Now what?**
Kernel CPU sampling is **system-wide**. Profile a wrapper or load-generator that
*does* exit, and the service's stacks get captured anyway. PerfView's `run` verb
stops collecting when the target exits, which is why pointing it at a resident
process directly doesn't work.

**Q: That function disappeared from the flame graph — does that mean the port worked?**
You can't conclude that. A missing symbol conflates never-called, inlined,
renamed, and unsymbolized. To claim a port removed a hot spot, profile the
**pre-port** build as a control, on a workload that actually exercises the kernel.

**Q: Why is my A/B performance comparison so noisy?**
ARM64 mobile devices downclock noticeably under sustained load. Warm up before an
A/B, leave cooldown time between runs, and use exactly the same workload and
timing method on both sides. Otherwise you're measuring temperature, not code.

**Q: I edited a spec `.yaml` and nothing changed.**
Regenerate the combined index: `node skills/dispatcher-skill/scripts/combine-specs.js`
(§11). Prose edits to a leaf `SKILL.md` take effect immediately, but a `.yaml`
edit without a regenerate is a dormant fix.

**Q: Will it change my repo and commit on its own?**
It pauses for confirmation at the phase gates — after the scan report, after the
task list, before the performance loop, and before archiving. Integrating the
ported kernels into the real build is part of the flow, but you control the pace.

---

---

# Internals (read when extending, debugging, or contributing)

The sections below describe how EasyWoS itself is organized and how it runs. If
you're only using it to port a project, you don't need to read this far.

---

## 9. What's in here, and the four roles

```
easywos-skills/
├── skills/
│   ├── arm64-port-orchestrator/ # TOP-LEVEL LOOP: propose→apply→integrate→build→test→fix→profile→archive
│   ├── easywos-spec/            # ORCHESTRATOR: scan YAML → matched YAML → tasks.md (+ per-kernel verify/retry loop)
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
│   │   # ── profiling pipeline (measure the port), now flat skills ──
│   ├── etl-generator/               # run a target under PerfView's CPU sampler → .etl
│   ├── perf-sampling-parser/        # .etl → per-process CPU ranking + SpeedScope flame graph
│   ├── perf-optimizer/              # flame graph → root-cause module + source gap scan + HTML report
│   │
│   │   # ── authoring / reporting ──
│   ├── arm64-porting-report/        # generate the EasyWoS-style porting YAML
│   ├── leaf-skill-creator/          # scaffold a new leaf skill (+ spec.yaml)
│   │
│   └── combined-spec-summary.yaml   # GENERATED index of all leaf specs (gitignored)
└── README.md / USAGE.md / USAGE.zh-CN.md
```

This repo is a *skilltree*: a thin orchestration layer that turns an EasyWoS scan
of an x64 codebase into an executable, spec-matched porting plan, plus a library
of leaf skills that do the actual x64→ARM64 translation, plus a profiling
pipeline that measures whether the port paid off and feeds each confirmed lesson
back into the specs — so the next project starts from a higher baseline. Four
roles:

- **Top-level loop** (`arm64-port-orchestrator`) drives the *entire* end-to-end
  process for a whole project — OpenSpec propose → easywos-spec task generation →
  OpenSpec apply → integrate the ported kernels into the project's real build →
  build the WHOLE project for ARM64 → run the project's OWN tests/bench →
  auto-fix loop over integrated failures → **post-port performance loop (§8.5)** →
  archive. It is the layer *above* `easywos-spec`: it invokes the skills below
  rather than reimplementing them. Use it when you want a hands-off "port this
  project to ARM64" run. See `references/outer-loop.md` for the build→test→fix
  algorithm and `references/perf-optimize-loop.md` for the performance loop.
- **Orchestration** (`easywos-spec`, `dispatcher-skill`, `arm64-baseline-porting`)
  decides *what* to port and *which recipe* to use, and owns the per-kernel
  verify→retry loop (`easywos-spec` §8). It does not contain migration logic.
- **Leaf skills** own the migration logic. Each holds one or more *specs* — a
  matched `.yaml` (machine-readable: match rules, x64/arm64 constructs,
  pitfalls, validation) and a `.md` (the human/agent-readable recipe).
- **Profiling** (`skillsthe profiling skills under /`) measures the ported binary: capture a
  trace, rank CPU by process, export a flame graph, attribute hot leaves to a
  root-cause module, and scan the source for x64-SIMD-without-NEON gaps. Usable
  standalone (§7), and invoked automatically by the orchestrator's §8.5.

---

## 10. The pipeline (what happens inside)

```
EasyWoS scan YAML
   │  ① arm64-porting-report  (produce the scan, if you don't have one)
   ▼
easywos-spec orchestrator
   │  ② preflight   – verify leaf skills present; regenerate combined-spec-summary.yaml
   │  ②′ decomposition – whole asm file → per-kernel group children (§1.4)
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
   │  ⑦ unit-test verification (gtest + CMake + build/run + negative control)
   │  ⑦′ verify→retry loop – feedback file → re-dispatch, ≤K attempts (easywos-spec §8)
   ▼
verified ARM64 port
   │  ⑧ profile against the REAL fallback (orchestrator §8.5 / the profiling skills)
   ▼
verified AND measured ARM64 port
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
  see §11);
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
  --output candidates.json \
  [--threshold N] [--no-decompose]
```

`--threshold` / `--no-decompose` control the decomposition pre-pass (below);
`--input`, `--specs` and `--output` are required.

> Clear any matcher **warning** (e.g. `code_range exceeds bounds`) before
> interpreting its output. A warning means the screened source may not be the
> code you think it is, and a zero-match result then looks like a spec gap when
> it is really a bad range.

**Whole-file assembly decomposition (the pre-pass before screening).** When a
porting item names an *entire* `.asm`/`.s`/`.S` file, matching it as one unit
fails twice over: a large file trips nearly every spec's `match_rules` somewhere,
so the candidate list loses all discriminating power, and "port lines 1–N of this
file" is not a task a leaf skill can act on or a gtest can cover per kernel. So
the matcher first splits the file into per-kernel groups (`easywos-spec` §1.4):

- **Triggered** automatically for an asm file whose resolved context exceeds
  **400 lines** (`--threshold`), or unconditionally when the item sets
  `segment: true`. Set `segment: false` to keep a file whole; `--no-decompose`
  disables it globally.
- **Split** on kernel entry points — `cglobal`/`cvisible` (NASM x86inc) or
  `<name> PROC` (MASM) — then ISA/size variants of one logical kernel are merged
  under a normalized group key (`foo_16x16_sse2` + `foo_8x8_avx2` → group `foo`),
  while a batch/arity suffix is kept (`foo_x4`) and a fused trailing number stays
  distinct (`foo8`, `foo16` → separate kernels).
- **Emits** one group child per group, id `<parent_id>__<group>`, each screened,
  dispatched and verified as an ordinary item.

**⑥ Dispatch.** Each tasks.md line is a dispatcher invocation:

```bash
# matched item (one or more specs)
/dispatcher-skill <item-id> --specs 86,87,90 --source <scan>-matched.yaml
# unmatched item
/dispatcher-skill <item-id> --mode llm-freeform --source <scan>-matched.yaml
```

The dispatcher loads the porting item, resolves each spec id via
`combined-spec-summary.yaml` to its leaf skill + file, loads that recipe, and
routes (multi-spec merge, cross-source primary selection, or baseline fallback).
It contains no migration logic itself.

**⑦ Verify.** After the leaf skills emit ARM64 source, the unit-test workflow
generates gtest fixtures (one per item), a clean-C-ABI test seam, CMake, and a
build/run script. Two flows — intrinsics (`references/unit-test-workflow-intrinsics.md`)
and assembly (`references/unit-test-workflow.md`) — selected by the leaf-skill
output language. Templates live under `skills/easywos-spec/references/`.

A fixture only counts as passing once it has been **observed failing** under a
deliberate perturbation (the negative-control gate, `easywos-spec` §7.6). Greens
that were never shown red are treated as unverified.

**⑦′ Retry on failure.** A failing item is not abandoned. `easywos-spec` §8 owns a
per-item **verify→retry loop**: it writes a feedback file describing the failure,
re-dispatches the item to the same leaf skill with `--feedback`, and repeats up to
a retry budget. An item that exhausts the budget is marked for review and does
**not** block the rest of the batch. There is also a scripted driver for this loop
at `skills/easywos-spec/references/port-loop.workflow.js`, which takes a matched
YAML plus a build command and runs dispatch → build → negative-control + gtest →
feedback retry across all items (`dryRun: true` prints commands without mutating
anything).

**⑧ Measure.** Correctness is not the whole bar: a port can be perfectly correct
and *slower* than the code it replaced. The orchestrator's §8.5 profiles the hot
leaves, optimizes, re-verifies, and (on real ports) captures each confirmed
lesson back into a leaf spec. Compare against the **real fallback build**, not a
hand-written baseline.

---

## 11. The generated spec index

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

> Only `references/specs/*.yaml` is aggregated. Prose edits to a leaf `SKILL.md`
> take effect immediately (the skill file *is* the skill) and are never a
> "dormant fix" — but a `.yaml` edit that is not followed by a regenerate is.

---

## 12. Anatomy of a leaf skill (and how to add one)

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
combined index (§11).

**Keep specs general.** A spec is shared infrastructure: express the *pattern*
(what the x86 construct is and what the ARM64 equivalent is), not the project
that happened to expose it. Project-specific specs match nothing elsewhere.

**Route a lesson by its kind.** A technical intrinsic/mnemonic lesson belongs in
a leaf spec. A process or verification lesson belongs in the orchestrator's
always-loaded discipline section, not buried in one leaf.

---

## 13. Conventions & gotchas

- **`combined-spec-summary.yaml` is generated** — never edit by hand; regenerate
  after spec changes.
- **Match rules target x86 source.** If a spec's purpose is a performance/output
  pattern, it still needs an x86-source trigger or it will match zero items.
- **Inline asm is spec-routed.** ARM64 inline-asm kernels match through the normal
  pipeline (matcher scope `inline_asm`); the `__asm__` context check is only a
  subordinate fallback for when no spec resolved to the inline-asm skill.
- **`variant_group` items share source bytes.** The screener can't distinguish a
  `+crc` baseline from a `+pmull` fast path (same source); LLM refinement splits
  them by `target_feature`.
- **A whole asm file is decomposed, not matched as one blob.** Above 400 lines
  (`--threshold`) an `.asm`/`.s`/`.S` item is split into per-kernel group children
  first, because a large file trips nearly every spec and destroys the candidate
  list's discriminating power. Force it with `segment: true`, prevent it with
  `segment: false`, disable globally with `--no-decompose`. If a decomposed run
  produces surprising group names, check the group-key normalization rules in
  `easywos-spec` §1.4.2 before assuming a spec gap.
- **Low confidence → `[NEEDS REVIEW]`.** Those items are dispatched but flagged
  for human verification.
- **The port must come from the leaf skills**, not hand-written by the agent —
  otherwise the "spec-driven → profile → fix-the-spec" loop is invalidated and a
  spec gap cannot be told apart from an ad-hoc coding artifact.
- **ARM64 output must build on MSVC, not just clang.** Mind MSVC-only pitfalls
  (NEON brace-init, `poly64_t`/`poly128_t`, `vmull_p64` lane form, no
  `<arm_acle.h>`); SVE2 is unsupported on MSVC. Note `clang-cl` defines
  `_MSC_VER` but ships clang's headers, so `#if defined(_MSC_VER)` alone does not
  identify real MSVC. See `arm64-baseline-porting`.
- **Short-buffer guards.** Fixed-stride SIMD kernels must guard `len < STRIDE`
  before any unconditional vector load, or short inputs read OOB / underflow
  `size_t` → segfault.
- **Don't narrow the parallelism width.** "Preserve semantics, not assembly
  appearance" frees you from the asm's *textual form*, not from how much data it
  processes per iteration. A one-item-at-a-time port of an N-wide kernel can be
  fully correct and still lose to compiler-optimized scalar C — a defect no
  correctness check can catch.

---

## 14. Reference material

- **End-to-end demos:** `skills/easywos-spec/demo/`
  (`zlib-porting-example-record.md`, `complete_smallest_demo_without_openspec.md`)
  and `references/demo-without-openspec.md`.
- **Output formats & templates:** `skills/easywos-spec/references/`
  (`matched-yaml-example.md`, `script-output-format.md`, CMake / build-script /
  unit-test workflow templates, and `port-loop.workflow.js` — the scripted
  verify→retry driver).
- **Orchestration contracts:** `skills/easywos-spec/SKILL.md` (pipeline) and
  `skills/dispatcher-skill/SKILL.md` (routing protocol).
- **Outer + performance loops:** `skills/arm64-port-orchestrator/references/`
  (`outer-loop.md`, `perf-optimize-loop.md`, `build-test-detection.md`,
  `verification-measurement-discipline.md`).
- **Profiling:** `skills/PROFILING-README.md`.

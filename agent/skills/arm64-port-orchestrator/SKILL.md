---
name: arm64-port-orchestrator
description: >-
  Top-level loop-engineering orchestrator for x64-to-ARM64 porting of any open
  source project. Drives the whole pipeline end to end — scan, OpenSpec propose,
  easywos-spec task generation, OpenSpec apply (per-kernel port + verify/retry),
  wiring the ported kernels into the project's real build, building the WHOLE
  project for ARM64, running the project's OWN test/bench suites, an auto-fix
  loop over integrated build/test failures, and OpenSpec archive on green. Use
  when the user wants to "port <project> to ARM64 end to end", "automate the
  whole openspec-to-build-and-test loop", "loop engineering for arm64 porting",
  or hand a project directory and ask for a hands-off ARM64 port. It is the
  layer ABOVE easywos-spec: it invokes easywos-spec, dispatcher-skill,
  enable-windows-arm64 and the leaf skills rather than reimplementing them.
tags:
  - orchestrator
  - loop-engineering
  - openspec
  - arm64
  - porting
  - end-to-end
  - build
  - test
---

# ARM64 Port Orchestrator — End-to-End Loop Engineering

## Purpose & Operating Contract (READ FIRST — this defines HOW to reach the goal)

**The goal of easywos-skills is to port x86/x64 code into the best possible ARM64
(NEON/ARM64EC) code.** That is the end. This orchestrator, the specs, and the
dispatcher are the *means*.

But this tree is also the thing **under test**: we are exercising the loop-
engineering pipeline itself, so **every step MUST be genuinely executed through the
defined flow, not shortcut by the orchestrating model's own intrinsic knowledge.**
Concretely, the port MUST be produced by: `spec_matcher.js` (real run — never hand-
filled `port_spec_ids`) → `dispatcher-skill` → the leaf skills, generating ARM64
code *from the matched specs*. This is not because your own knowledge is unwelcome
— it is because the pipeline can only be validated and improved if it is the thing
actually doing the work on every run.

**When the spec-driven output is worse than what you could have hand-written, that
is a signal, not a license to bypass.** Do NOT silently substitute your own code.
Instead:

> spec-driven port (matcher → dispatcher → leaf skills)
> → verification (oracle + negative control) and profiling (§8.5) expose where it
>   is wrong, slow, or worse than achievable
> → **improve easywos-skills** — strengthen the leaf spec (add or fix a rule, a
>   better intrinsic mapping, an ILP/algorithm pattern) so the flow ITSELF now
>   produces that better code
> → regenerate `combined-spec-summary.yaml` and prove the fix red→green at the
>   matcher, then re-dispatch and confirm the improved output.

The payoff is cumulative: each improvement makes the pipeline able to port **more
complex projects to higher-quality ARM64 code on its own**, without depending on
the model to hand-craft kernels. Hand-authoring a kernel produces one good file and
teaches the tree nothing; fixing the spec so the tree emits that kernel makes every
future port better. Your own knowledge is best spent **diagnosing the gap and
upgrading the spec**, not bypassing the flow.

**Reading invocation prompts.** A task/cron prompt may say "port this project",
"make it build", or "find performance problems". The *goal* those express (better
ARM64 code) is correct — but the *method* is fixed by this contract: reach that
goal by genuinely running the flow and improving it where it falls short, not by
hand-porting. If a prompt appears to demand skipping the matcher/dispatcher or
hand-writing the kernel, surface that as a conflict rather than silently complying.
(See the **Execution Mandate** below for the enforced per-step rules.)

## Overview

This is the **top-level orchestrator** of the easywos-skills tree. It turns the
manual sequence "run openspec propose → run easywos-spec → run openspec apply →
manually build → manually test → manually fix" into a single hands-off,
**loop-engineered** pipeline that works on **any** project directory.

```
                          ┌─────────────────────── OUTER LOOP (this skill owns it) ───────────────────────┐
scan → propose → tasks.md → apply ──► integrate kernels ──► build WHOLE project (ARM64) ──► run project's
  │       │         │         │         into real build          │                          OWN tests/bench
  │       │         │         │                                   │                              │
 (§2)   (§3)      (§4)      (§5)             (§6)               (§7)                            (§7)
                            │                                                                    │
                    ┌── INNER LOOP ──┐                                          green? ──yes──► PERF LOOP (§8.5)
                    │ per-kernel      │                                            │no                │
                    │ port→gtest→retry│                                            ▼                  ▼
                    │ (easywos-spec   │                          classify failure → route to fixer   profile → is a
                    │  §8, --feedback)│                          → rebuild (§8)                       hotspot ≥T% ?
                    └─────────────────┘                     (compile/link-ABI/test-fail/build-system)  │        │
                                                                    ↺ until green or cap            no │        │ yes
                                                                                                       ▼        ▼
                                                                                          archive (§9) ◄──  optimize 1 hotspot
                                                                                                          → VERIFY correct+faster
                                                                                                          → capture lesson to leaf
                                                                                                          → re-profile  ↺ until
                                                                                                          no hotspot / stall / cap
```

Three loops, each with a **terminal exit** (no loop may hang):

- **INNER loop — per-kernel correctness.** Already implemented by
  `easywos-spec §8` + `dispatcher --feedback`: each ported kernel is verified in
  isolation (its own gtest fixture) and re-dispatched with feedback until green
  or the retry budget K is spent. This orchestrator does **not** reimplement it —
  it just runs `openspec apply` which executes that loop.
- **OUTER loop — whole-project integration (this skill owns it).** After the
  kernels are individually correct, they must compile, link, and pass **inside
  the real project** and against the **project's own test/bench suite**. Any
  failure there (a build-system gap, a link/ABI mismatch, a project-level test
  regression) is classified and routed to the right fixer, then the project is
  rebuilt — until the integrated project is green or the iteration cap is hit.
- **PERF loop — post-port optimization (NEW; this skill owns it, §8.5).** A port
  can be *correct but slow* — most often an x64 SIMD path ported to a scalar
  fallback. Correctness tests never catch this; only a profiler does. After the
  project is green, this loop profiles the ARM64 build with the `profiling`
  skills, and while a hotspot sits above a threshold it optimizes one hotspot,
  **independently verifies both correctness (negative control) and a real
  speedup**, **captures the verified technique back into a leaf skill**, and
  re-profiles — until no significant hotspot remains, a stall, or the cap. It is
  optional and additive, and never weakens a correctness gate to gain speed.

The orchestrator is **generic**: nothing below is x265-specific. All project
facts (path, build system, test command) are discovered at run time (§1, §7.1)
or passed as arguments.

### Loop-engineering decision model (how authority is delegated)

This skill follows the "push decisions down to the right layer" model. Three
kinds of decision, each handled by the right actor — never all by one agent:

1. **① Orchestration decision** — *what to do, in what order, whether to retry
   or stop.* This is **deterministic code**, never free LLM judgement: the outer
   loop lives in [assets/outer-loop-driver.js](assets/outer-loop-driver.js) (run
   via the Workflow tool), where the loop, fan-out, retry counters, and
   convergence/stall criteria are hardcoded. The skeleton is code; agents only
   fill it in. (§7.2, §8)
2. **② Task decision** — *how to do one specific thing.* Delegated to a fixer
   agent inside a **bounded box**: one owning file, a clear method, and an
   objective acceptance test (the rebuild). (§8 step 2)
3. **③ Judgement decision** — *is the work actually correct.* Handled by
   **independent** verification, never by the agent that did the work: objective
   gates (compile/link/test) plus an adversarial verifier agent that must refute
   the fix or watch the test go red under a negative control before it is
   trusted. (§8 step 3)

Backed by three principles enforced throughout: **narrow boundaries** (each agent
decides in a small space), **decision ≠ verification** (the maker never grades
itself — a green isn't real until seen red on a counterexample), and **state
externalized** (all cross-round decisions land in files — the state file, tasks.md
checkboxes, `feedback/*.yaml`, and `OUTER-PROGRESS.md` — so the loop is
resumable, reproducible, and debuggable).

---

## Execution Mandate: the port MUST be produced by the leaf skills, not by you (READ FIRST — NON-NEGOTIABLE)

**The goal is the best possible ARM64 code — but it must be reached by RUNNING the
pipeline, so the pipeline itself gets better (see the Purpose & Operating Contract
above).** The value chain this flow exists to run is:

> port **using spec knowledge** (via `dispatcher-skill` → leaf skills) → the spec
> has a gap → the spec-driven code is wrong, slow, or worse than achievable →
> verification + profiling (§8.5) find it → **improve easywos-skills** so the flow
> itself now emits the better code (then prove it red→green at the matcher).

Every link depends on the first one. If *you* (the orchestrating model) hand-write
the NEON port from your own intrinsic knowledge instead of driving the leaf skills,
the chain is **broken at the root**: the pipeline was never exercised, so any gap
you later "find" is an artifact of *your* code, not of the flow, and there is
nothing real to fix back into the tree (and it can be circular — you write the
naive version a spec would have avoided, then "discover" it). This actually
happened and wasted a run; do not repeat it. Hand-authoring yields one good file
and teaches the tree nothing; improving the spec makes every future port better.

**Therefore, MANDATORY on every run — no shortcuts, even when you are confident you
could write the kernel yourself:**

1. **Run the real matcher.** `port_spec_ids` in the matched YAML MUST come from
   `easywos-spec/scripts/spec_matcher.js`, never hand-filled. Hand-guessed IDs are
   routinely wrong (observed: guessed `[106]`, matcher actually returns 97/146/151/152).
2. **Dispatch to the leaf skills.** Each `tasks.md` item's port MUST be produced by
   actually invoking `/dispatcher-skill <id> --specs <ids> --source <matched-yaml>`
   (which routes to the `sse-avx-to-neon` / `intrinsics-x64-to-arm64` / `asm-*` leaf
   skills), so the code reflects **what the spec knowledge yields** — including its
   blind spots. Spawn a subagent as the leaf skill if needed, but the port is the
   leaf skill's output, following the matched specs, **not** your from-memory version.
3. **You orchestrate and verify; you do not author.** Your role is: run the matcher,
   dispatch, then apply the objective gates (scalar oracle + negative control + §8.5
   profile). Decision ≠ verification — the thing that *makes* the code must not be
   the thing that grades it, and here the maker must be the leaf skill.
4. **A clean spec-driven port is a valid, valuable outcome; a worse-than-achievable
   one is a spec-improvement task, not a bypass.** If the leaf skills produce good
   code, record CONVERGED — positive confirmation the spec is good. Do NOT
   manufacture a slow version to "find a problem"; a real problem only counts if the
   spec-driven output exhibits it. If the spec-driven output IS worse than what you
   know is achievable, the correct response is to **upgrade the leaf spec so the
   flow emits the better code** (then §5-re-dispatch and confirm), never to quietly
   swap in your hand-written kernel.
5. **Closing the loop requires red→green at the matcher.** A spec fix is not
   promoted until `combine-specs.js` regenerates `combined-spec-summary.yaml` AND
   the matcher then surfaces the new/edited spec on the report (it did not before).
   A leaf-yaml edit without regeneration is a **dormant fix**.

If for any reason a port is produced by hand rather than by the leaf skills, that
is a **skipped step** — say so plainly in the report (faithfulness over completion);
never present a hand-written port as a spec-driven result.

---

## Verification & Measurement Discipline (READ FIRST — applies to EVERY port)

These are cross-cutting **process** rules — not tied to any one intrinsic — that
govern every §5 correctness check and every §8.5 measurement. They were learned
across many real ARM64 porting runs; skipping one produces a false green or a
false speedup. Apply them on every run; the full rationale + the failure each was
learned from is in
[references/verification-measurement-discipline.md](references/verification-measurement-discipline.md).

1. **Negative control must EXCEED the tolerance.** A perturbation smaller than the
   pass tolerance still passes — the control is silently useless. Flip a mantissa
   bit / scale an input ±50%, not ±1 ULP. Prove red, revert, prove green.
2. **Oracle must match the ported SEMANTICS/LAYOUT.** Verify against the exact
   arithmetic of the kernel you ported (not the library's textbook scalar), and
   against its own SIMD layout (round-trip `unpack(pack(x))==x`, not a naïve linear
   layout). Mind rounding (`vcvtnq` round-to-nearest ≠ truncating `vcvtq` ≠ scalar
   `lrintf`).
3. **Near-zero references need ABS-OR-RELATIVE tolerance.** Pass if `abs_err<abs_tol`
   OR `rel_err<rel_tol`; a pure-relative metric flags correct near-zero results.
4. **Defeat benchmarking traps.** Loop-hoisting/dead-store elimination and
   first-touch page faults make you measure nothing or the OS. Make every result
   live (serial-dependent inputs + consume all outputs + `volatile` global sink),
   use large iteration counts, subtract a warmup pass (~6s+ steady state).
5. **Decide A-vs-B by PAIRED back-to-back measurement.** Do not compare CPU-ms from
   two ETLs collected minutes apart (load drifts). Run A,B,A,B… alternating and
   compare paired wall-clock; use the profiler for *attribution* (genuine kernel
   work vs fallback), not cross-collection magnitude.
6. **Faithfulness over completion.** A green never seen red is *unverified*; a
   speedup not re-measured is *unverified*; a synthetic-workload win stays a
   *candidate* until a second real-workload datapoint corroborates it.
7. **Profile the ported kernel against the REAL fallback — "correct but slower" is
   a defect class no correctness check can catch.** A port can pass every KAT,
   oracle and asm-equivalence test and still be slower than the portable C it
   replaced (measured case: a ChaCha20 port that narrowed 4-block-parallel asm to
   one block per iteration was 1.22x SLOWER than wolfSSL's C; widening it back to
   4-wide made it 1.96x FASTER, same tests). Therefore:
   - Compare against the **actual fallback the OFF build runs**, not a baseline
     you wrote yourself — a hand-written baseline flatters the port. If the real
     fallback is `static`, EXTRACT it verbatim and validate the extraction against
     a KAT before trusting it (a silently-empty macro in an extraction once made
     the "baseline" run 6x too fast).
   - Gate every benchmark on a **checksum both sides must match**; unequal work
     makes the timing meaningless, and this is what catches a broken baseline.
   - Treat *slower than portable C* as a signal to **widen the parallelism**, not
     to revert the port.

---

## 0. Invocation & Arguments

```
/arm64-port-orchestrator <project-path> [options]
```

| Argument | Required | Default | Meaning |
|----------|----------|---------|---------|
| `<project-path>` | Yes | — | Root of the project to port (absolute or repo-relative). |
| `--change-name <slug>` | No | `<project>-arm64-porting` | OpenSpec change id to create. |
| `--build-cmd "<cmd>"` | No | auto-detected (§7.1) | Command that builds the WHOLE project for ARM64. |
| `--test-cmd "<cmd>"` | No | auto-detected (§7.1) | Command that runs the project's own test/bench suite. |
| `--target arm64-windows \| arm64-linux` | No | `arm64-windows` | Toolchain family for build/test. |
| `--max-outer-iters N` | No | `12` | Cap on the outer build→fix loop (§8). |
| `--inner-retry-K N` | No | `3` | Per-kernel retry budget handed to easywos-spec §8 / dispatcher. |
| `--profile` / `--no-profile` | No | `--profile` | Run (or skip) the post-port performance loop (§8.5). Skipped automatically if no runnable workload is resolvable or the host is not elevated. |
| `--run-workload "<args>"` | No | — | A terminating workload for the profiled target (§8.5). If absent, §8.5 tries the project's own bench target, else STALLs with that reason. |
| `--perf-hot-pct N` | No | `10` | Stop threshold for §8.5: a hot leaf below this %CPU self-time is not worth optimizing (the CONVERGED signal). |
| `--perf-max-iters N` | No | `6` | Cap on the §8.5 profile→optimize→verify loop. |
| `--capture-lessons` / `--no-capture-lessons` | No | `--capture-lessons` | Whether §8.5 feeds each verified optimization back into a leaf skill spec (real ports only). |
| `--synthetic-workload` | No | off | Mark the profiled target as a synthetic/test program. §8.5 still profiles and optimizes, but lessons are written to `PERF-PROGRESS.md` only — never merged into the shared skill tree (a test program is not general evidence). |
| `--autonomy hands-off \| checkpoint` | No | `checkpoint` | `hands-off` runs all phases without pausing; `checkpoint` pauses for confirmation at the phase gates in §1.3. |
| `--resume-from <phase>` | No | — | Skip to a phase (`propose`/`apply`/`integrate`/`build`/`perf`/`archive`) when re-running after an interruption; earlier phases are assumed complete and verified. |

**State file.** The orchestrator maintains `openspec/changes/<change-name>/.orchestrator-state.yaml`
recording the phase reached, the matched-YAML path, the build/test commands, and
the outer-loop history. It is the resume anchor for `--resume-from` and the
audit trail; update it at every phase boundary.

---

## 1. Preflight, Autonomy & Phase Gates

### 1.1 Dependency preflight (MUST run first)

Before anything else, confirm every skill this orchestrator composes is present.
Reuse the same install-then-stop policy as `easywos-spec §0`.

| Dependency | Path | Role |
|-----------|------|------|
| `easywos-spec` | `skills/easywos-spec/SKILL.md` | Spec match + tasks.md + inner verify/retry loop (§4, §5) |
| `dispatcher-skill` | `skills/dispatcher-skill/SKILL.md` | Per-item routing / re-entry point (§5) |
| `arm64-porting-report` | `skills/arm64-porting-report/SKILL.md` | Scan → EasyWoS porting-report YAML (§2) |
| `enable-windows-arm64` | `skills/enable-windows-arm64/SKILL.md` | Generic build-system detect/enable (§6, §7.1) |
| `arm64-baseline-porting` | `skills/arm64-baseline-porting/SKILL.md` | Freeform / fallback constraints |
| leaf skills | `skills/{asm-x64-to-arm64,sse-avx-to-neon,intrinsics-x64-to-arm64,arm64-inlineasm-to-intrinsics}/` | Migration execution |
| profiling skills | `skills/profiling/{etl-generator,perf-sampling-parser,perf-optimizer}/` | Post-port CPU profiling + root-cause (§8.5) |
| `leaf-skill-creator` | `skills/leaf-skill-creator/SKILL.md` | Capture a verified optimization back into a leaf spec (§8.5) |
| combined specs | `skills/combined-spec-summary.yaml` | Global spec table |
| OpenSpec | `openspec/` present in `<project-path>` (or its repo) with `config.yaml` | Change lifecycle |

If any are missing, follow `easywos-spec §0.3`: try `npx skills add https://github.com/qcom-WoSEcosystem/easywos-skills.git`, re-check, and if still missing STOP and list them. Do NOT proceed on a partial toolchain.

### 1.2 Toolchain preflight

Confirm the build/test host can actually build ARM64 for the chosen `--target`:
- `arm64-windows`: a native Windows-on-ARM64 host (no emulation) with MSVC ARM64 tools + ClangCL, `cmake` on PATH; `armasm64` if any output is armasm-dialect `.asm`. (See `easywos-spec §7.5`/§7.6.)
- `arm64-linux`: an aarch64 host or a working cross toolchain.

Prove the toolchain works with a trivial invocation (`cmake --version`, compiler `--version`) before trusting later "build failed" signals — a missing compiler must be reported as a toolchain gap, not auto-"fixed" as a code bug.

### 1.3 Autonomy & phase gates

In `--autonomy checkpoint` (default), pause and summarize for user confirmation
at these gates: **after §2 (scan report)**, **after §4 (tasks.md generated)**,
**before §8.5 (perf loop — since it captures lessons into the shared skill tree)**,
and **before §9 (archive)**. In `--autonomy hands-off`, do not pause — but still
honor every mandatory STOP (missing deps §1.1, toolchain gap §1.2, ambiguous
build/test command §7.1, outer-loop non-convergence §8.4, perf STALL §8.5.2).
Autonomy tunes *optional* pauses; it never disables a safety STOP.

---

## 2. Scan → EasyWoS Porting Report

Produce the EasyWoS input the rest of the pipeline consumes.

1. Invoke the **`arm64-porting-report`** skill against `<project-path>` to scan
   for x64-specific code (hand-written asm, SSE/AVX intrinsics, arch guards) and
   emit an EasyWoS YAML with `schema: x64-to-arm64-porting` and a `porting_items`
   array. Save as `<project-path>/<project>-arm64-porting-report.yaml`.
2. Validate the output: non-empty `porting_items`, each with `file_path` +
   `code_range` resolvable from the report's directory (mirrors `easywos-spec §1.2`).
3. **Checkpoint gate (§1.3):** report the item count and a one-line summary per
   item. If zero items, STOP — either the project has no x64-specific code to
   port, or the scan config is wrong; do not fabricate work.

> If the user already has a hand-authored porting-report YAML, accept it via a
> `--report <path>` override and skip the scan.

---

## 3. OpenSpec Propose

Create the change that will carry the port.

1. Run the OpenSpec propose flow (skill `openspec-propose` / `opsx:propose`) to
   create `openspec/changes/<change-name>/` with `proposal.md`, `design.md`, and
   a `tasks.md` placeholder. The proposal's scope is "port <project> to ARM64:
   migrate the N scanned porting_items, integrate into the real build, and pass
   the project's own test suite on ARM64."
2. Ensure `openspec/config.yaml` has the `rules.tasks` entry that mandates
   `easywos-spec` for porting_item changes (as in this repo's `config.yaml`). If
   absent, add it — that rule is what makes §4 fire automatically on task
   generation.
3. Record the change path in the state file.

---

## 4. Task Generation via easywos-spec (drives the INNER loop's plan)

Delegate tasks.md generation entirely to **`easywos-spec`** — do not hand-write
tasks, and do **not** hand-fill `port_spec_ids`: they MUST be produced by actually
running `easywos-spec/scripts/spec_matcher.js` against the report (hand-guessed IDs
are routinely wrong — see the Execution Mandate). Pass it the porting-report YAML
from §2. It will:

- run script screening + LLM refinement, emit `<report>-matched.yaml` with
  `port_spec_ids` + `match_confidence` (easywos-spec §2–4),
- generate `tasks.md` with one `/dispatcher-skill` invocation per item plus a
  **Verification** section that already encodes the inner verify→retry loop
  (easywos-spec §5, §7, §8),
- decompose any whole-file assembly items into per-kernel group children
  (easywos-spec §1.4).

**Checkpoint gate (§1.3):** surface the generated tasks.md — item count, any
`[NEEDS REVIEW]` low-confidence items, and the chosen verification flow
(assembly / intrinsics / both). This is the plan the inner loop executes.

---

## 5. OpenSpec Apply — Port + Inner Verify/Retry Loop

Run the OpenSpec apply flow (skill `openspec-apply-change` / `opsx:apply`) to
work through `tasks.md`. This executes, per item:

- `/dispatcher-skill <id> --specs … --source <matched-yaml>` → leaf skill emits
  ARM64 output,
- the **inner loop** (easywos-spec §8): build the item's gtest fixture, run it,
  and on failure write `feedback/<id>.attemptN.yaml` and re-dispatch with
  `--feedback` until the fixture is green **and was shown red at the V.0
  negative-control gate**, or the retry budget `--inner-retry-K` is spent
  (→ `[NEEDS REVIEW]`, batch continues).

> **HARD GATE (see the Execution Mandate above): the NEON port MUST be the leaf
> skill's output, never hand-written by the orchestrating model.** The dispatcher
> loads the matched specs and the leaf skill emits the ARM64 code *from that spec
> knowledge* — that is the only way §8.5 can later reveal a genuine *spec* gap
> rather than an artifact of your own coding. If you skip the dispatcher and write
> the kernel yourself, the entire "spec-driven → profile → fix-the-spec" loop is
> invalidated. Spawn a subagent to act as the leaf skill if the dispatcher cannot
> run directly, feed it ONLY the matched specs (not your own solution), and treat
> its output as the port. Never hand-fill `port_spec_ids` — they come from the
> matcher (§4). If a hand port is unavoidable, mark the item and report it as a
> skipped/unverified spec-driven step; do not pass it off as spec-driven.

The orchestrator's job here is to **launch and monitor**, not to re-implement:
- Pass `--inner-retry-K` through as easywos-spec's K.
- When apply finishes, read tasks.md checkboxes: collect items marked `[x]`
  (verified), `[NEEDS REVIEW]` (retry-exhausted), and any unchecked (skipped).
- **Do not enter the outer loop until every item is either `[x]` or explicitly
  `[NEEDS REVIEW]`.** A `[NEEDS REVIEW]` kernel is allowed to proceed (it may not
  be exercised by the project tests, or its defect may surface at §7 and get
  fixed there), but it MUST be reported, not silently treated as done.

> Trust rule (inherited from global working principles + easywos-spec §7.6):
> never count a fixture as passing unless it was observed failing under a
> deliberate perturbation. If apply reports greens that were never shown red,
> treat them as **unverified** and force the negative control before trusting.

---

## 6. Integrate Kernels Into the Project's REAL Build

This is the bridge between "kernels correct in isolation" (§5) and "whole project
builds" (§7) — the step most manual pipelines forget. It is **generic**: discover
how the project already wires its *existing* asm/arch-specific sources, then wire
the ARM64 outputs the same way.

1. **Detect the build system** with `enable-windows-arm64`'s detector
   (`scripts/detect_build_system.py`) and its ARM64-enable step so the project
   has an ARM64 build configuration/preset at all.
2. **Find the existing arch-specific integration point.** Locate how the project
   compiles its current SIMD/asm sources (e.g. an x86 source list, an assembler
   custom command, a `setupAssemblyPrimitives`-style dispatch table, `#ifdef`
   arch guards). This is the template.
3. **Register the ARM64 outputs by mirroring it:**
   - add the ported `.S`/`.asm`/`.c` files to the build under the ARM64 guard,
     mirroring how the existing arch sources are listed;
   - create/extend the dispatch table so the ARM64 kernels are actually *called*
     (a registration TU mirroring the existing one, guarded by the project's
     ARM64 macro), and matching headers with the exact C-ABI prototypes;
   - only register a symbol that actually exists in the emitted output — inspect
     the files; never invent symbols.
4. **Idempotent.** If integration already exists (re-run / `--resume-from`),
   detect it and change nothing. Record what was wired in the state file.

Ground every edit in the surrounding code's idiom and the project's own arch
macros. When the correct wiring is ambiguous, prefer registering fewer, certain
kernels — the outer loop (§7/§8) will surface anything missing as a link error
and route it back here.

---

## 7. Build the WHOLE Project & Run Its OWN Tests (outer-loop body)

### 7.1 Resolve build & test commands (once)

If `--build-cmd`/`--test-cmd` were not given, auto-detect and CONFIRM before use
(a wrong test command silently reports false green — a mandatory STOP if
ambiguous):

- **Build:** from the detected build system + target. E.g. CMake/Windows-ARM64:
  `cmake -S <src> -B <build> -A ARM64 -T ClangCL <arch/test flags> && cmake --build <build> --config Release`. Reuse the project's own ARM64 preset/toolchain file if present (e.g. a `arm64-windows-clangcl` toolchain, a `CMakePresets.json` ARM64 preset).
- **Test/bench:** discover the project's OWN suite — do not settle for the
  isolated verify-gtest from §5. Look for, in priority order: a CTest/`ctest`
  registration, a test/benchmark target or binary (e.g. a `*TestBench`,
  `*_test`, `check` target, `checkasm`), a `make check` / `ninja test`, or a
  documented test command in the project README/CI. Enabling tests may require a
  build flag (e.g. `-DENABLE_TESTS=ON`); fold it into the build command.
- Record both commands in the state file. See
  [references/build-test-detection.md](references/build-test-detection.md).

### 7.2 The outer loop is driven by a DETERMINISTIC script, not by prose

The loop control — iterate, fan out, count retries, decide "loop again vs.
stop", detect no-progress, exit — is **hardcoded** in
[assets/outer-loop-driver.js](assets/outer-loop-driver.js), run via the Workflow
tool. This is the orchestration-layer (①) decision, and per the loop-engineering
principle it is CODE, not an LLM judgement: a single bad agent turn cannot make
the loop run away, skip verification, or archive early, because those transitions
are not the agent's to make. Agents only FILL IN two delegated decisions:

- **② task-layer** — "how do I fix this one file" (the fixer agents), and
- **③ judgement-layer** — "is this fix actually correct" (the verifier agents).

**Invoke the driver** once build/test commands are resolved (§7.1), passing all
project facts as `args` (nothing is hardcoded in the script):

```
Workflow({ scriptPath: "<skills>/arm64-port-orchestrator/assets/outer-loop-driver.js",
           args: { projectPath, buildCmd, testCmd, matchedYaml,
                   stateDir: "openspec/changes/<change>/",
                   maxOuterIters: <--max-outer-iters>, innerRetryK: <--inner-retry-K> } })
```

Do **not** re-implement the loop by hand-running build/fix steps in the main
conversation — that reintroduces exactly the "LLM decides whether to continue"
failure mode the driver exists to remove. The driver returns
`{ status: CONVERGED | STALL, reason, iterations, finalTests, needsReview, history, progressLog }`.

---

## 8. Auto-Fix Loop Internals (what the driver does each iteration)

The driver embodies the three-layer decision model. Each iteration:

1. **Build stage — objective gate (not an agent opinion).** One agent runs
   `buildCmd` then `testCmd`, and returns a *structured* classification of every
   distinct root failure (category + owning `targetFile` + `kernelId`). Red/green
   is decided by the tools, not by an agent's say-so. Success = configure+build+
   link clean AND the project's own suite ran with zero failures.

2. **Fix stage — ② task-layer, one fixer per owning file (bounded box).**
   Failures are grouped by the file that owns them; one fixer agent per file,
   independent files fixed in parallel, **never two agents writing the same
   file**. Each fixer gets a tight box: *only* this file, minimal root-cause fix,
   with method by category:

   | Failure category | Owning fixer | Box / method |
   |---|---|---|
   | `build-system` | `enable-windows-arm64` + §6 integration | fix build files / ARM64 flag / source registration |
   | `compile-asm` / `compile-cpp` | leaf skill discipline via targeted edit | fix the owning `.S`/`.cpp`/header |
   | `link-abi` | §6 integration + leaf skill | fix the symbol's owner (export name / prototype / registration) |
   | `test-failure` | **re-enter the INNER loop** for that `kernelId` | write `feedback/<id>.attemptN.yaml` (dispatcher §2.7.1) and re-dispatch with `--feedback`; the project's own test is now the oracle |

3. **Verify stage — ③ judgement-layer, DECISION ≠ VERIFICATION.** The agent that
   made a fix does **not** bless it. A separate, independent verifier agent
   adversarially checks each applied fix (default verdict: *not verified*):
   - non-test fixes → try to **refute** (find a counterexample; re-run the build/
     link step to confirm the specific error is gone and nothing new broke);
   - `test-failure` fixes → **mandatory negative control**: perturb the test's
     reference side, watch it go `[FAILED]`, revert, watch it go green. A fix that
     can't be shown red is *unverified* — the test isn't wired to the kernel.
   Only **independently verified** fixes let the loop proceed to rebuild. Refuted
   fixes are recorded so the next round doesn't retry the dead approach.

**Retry budget (owned by the code).** Per-kernel `test-failure` retries are
counted by the driver against `innerRetryK`; on exhaustion the kernel is marked
`[NEEDS REVIEW]` and no longer re-fixed — one hard kernel never stalls the batch.

**State externalization.** Each iteration appends to
`openspec/changes/<change>/OUTER-PROGRESS.md`: the failures seen, fixes applied,
which were verified vs. **refuted (with counterexample)**, so a resumed or next
iteration never repeats a dead end. Per-kernel `feedback/*.yaml` carries the
inner-loop signal (as in §5).

### 8.4 Terminal exit (the driver ALWAYS returns one)

- **`CONVERGED`** — whole project builds + the project's own suite green + every
  trusted test fix was shown red under negative control → §9 (archive).
- **`STALL(reason)`** — iteration cap hit, zero fixes applied, failure signature
  unchanged across `staleStop` rounds, all fixes refuted, or only
  retry-exhausted kernels remain. Do **not** archive; report the surviving
  failures (category + owning file + message) and the single most likely next
  action; leave the change applied-but-not-archived for a human.

A run that neither converges nor stalls is a bug in the driver, not a valid
state — every code path returns one of the two.

---

## 8.5 Post-Port Performance Loop (profile → optimize → verify → capture)

Runs **after** §8 reaches CONVERGED (the whole project builds and passes its own
tests on ARM64) and **before** §9 archive. Skipped when `--no-profile` is given,
when no runnable terminating workload can be resolved, or when the host is not
elevated (kernel CPU sampling requires it) — in those cases record why and go to
§9.

**Why it exists.** A port can pass every correctness gate and still be *slow* —
the classic case is an x64 SIMD kernel that was ported to a **scalar fallback**
(per-element `fminf`/`sqrtf`/`expf`, a NEON block gated out by `#ifdef __GNUC__`,
a `portable::` path with no ARM64 specialization). The inner (§5) and outer (§8)
loops are correctness loops; they are green on slow-but-correct code. Only a
profiler catches it. This phase adds that missing signal and, uniquely, **feeds
what it learns back into the skill tree**.

### 8.5.1 The loop is a DETERMINISTIC driver (same model as §7.2/§8)

Loop control — profile, decide *whether a hotspot is worth optimizing*, whether
to *loop again*, and *when we are done* — is **hardcoded** in
[assets/perf-optimize-loop-driver.js](assets/perf-optimize-loop-driver.js), run
via the Workflow tool. It is the orchestration-layer (①) decision and is CODE,
read from the objective profile numbers, never an agent's opinion. Agents fill in
only ② "how do I optimize this one hotspot" and ③ "is it still correct AND
actually faster". Invoke once the ARM64 build is green and a workload is known:

```
Workflow({ scriptPath: "<skills>/arm64-port-orchestrator/assets/perf-optimize-loop-driver.js",
           args: { projectPath, runTarget, runArgs, buildCmd, matchedYaml,
                   skillsRoot: "<skills>", stateDir: "openspec/changes/<change>/",
                   sourceMap: "<module=src;...>",
                   hotThresholdPct: <--perf-hot-pct>, minSpeedupPct: 5,
                   maxIters: <--perf-max-iters>, captureLessons: <--capture-lessons>,
                   syntheticWorkload: <--synthetic-workload> } })
```

Each iteration:

1. **Profile stage — objective gate.** One agent runs the `profiling` skills
   (`etl-generator` → `perf-sampling-parser` → `perf-optimizer` analyze; **never**
   xperf/WPA) and returns the ranked hot leaves with `selfPct` and perf-optimizer's
   `suspect_caller_module`, mapping each to a `kernelId` via `matchedYaml` when it
   traces to a ported kernel. Hotness is measured by tools, not asserted.
2. **Optimize stage — ② task-layer, one hotspot in a bounded box.** The driver
   picks the single most expensive **actionable** hotspot and hands it to an
   optimizer agent restricted to that hotspot's owning source, told to apply the
   right leaf-skill technique (e.g. scalar libm → NEON `vminq`/`vsqrtq` +
   vectorized polynomial; fix a NEON-blocking `#ifdef` guard to include
   `_M_ARM64`). A SIMD specialization **must** keep the scalar `#else` fallback,
   guard with `_M_ARM64 || _M_ARM64EC || __ARM_NEON`, handle the tail, and keep a
   scalar-vs-optimized correctness check.
3. **Verify stage — ③ judgement, DECISION ≠ VERIFICATION.** An independent agent
   must confirm **both**: (a) **correctness** via a mandatory **negative control**
   (perturb the optimized path, watch the check go red, revert, watch it go
   green), and (b) a **real speedup** it measured itself by re-profiling/timing
   (≥ `minSpeedupPct`). A speedup from shrinking the workload or loosening
   tolerance is rejected. Only a fix that is *both* correct and measurably faster
   is **accepted**.
4. **Capture stage — feedback into the skill tree.** For each accepted, and if
   the technique is **generalizable**, the driver routes it into the best leaf
   skill (extend an existing `references/specs/*.md`+`.yaml`, or use
   `leaf-skill-creator --add-yaml`), adds one spec pattern whose **Validation
   block records the profiler signature** (e.g. *"hot leaf was `module!expf`"*)
   and whose match rules fire on **both** the x86 source construct and the
   NEON-output self-check, then regenerates `combined-spec-summary.yaml`. One-off,
   project-specific wins are recorded only in `PERF-PROGRESS.md`, not the tree.

   > **A lesson is NOT promoted until the matcher can surface it (verify red→green).**
   > Editing a leaf `references/specs/*.yaml` is not enough: the spec-matcher reads
   > the aggregated `combined-spec-summary.yaml`, so you MUST run
   > `dispatcher-skill/scripts/combine-specs.js` to regenerate it, then re-run
   > `easywos-spec/scripts/spec_matcher.js` on the porting report and confirm the new
   > spec now appears for the target item (it did NOT before). A leaf-yaml edit
   > without regeneration is a **dormant fix** — invisible to the very tool that
   > would apply it. Also add a match rule for the actual construct that appears
   > (e.g. a FLOAT accumulator kernel needs `_mm_add_ps`/`float32x4_t sum` rules —
   > integer-only rules never fire on it). Do not hand-fill `port_spec_ids` in a
   > matched YAML; run the matcher — hand-guessed IDs are often wrong.

   **Route the lesson by its KIND — two homes (standing rule).** Every time a
   run yields a durable lesson — during *any* phase, not just this one — capture
   it in the correct place:
   - **Technical / intrinsic-specific** ("this x86 op maps to that NEON op / this
     pattern is faster") → a **leaf spec** (`references/specs/*.md`+`.yaml`),
     matched by the spec-matcher on the relevant construct. (e.g.
     `neon-performance-patterns` §9 popcount→`vcntq`, §13 reciprocal/rsqrt pivot;
     `intrinsic-mapping` shuffle bit7-zeroing.)
   - **Cross-cutting / process / verification / measurement** ("how to verify or
     measure correctly, regardless of kernel") → the global
     [Verification & Measurement Discipline](#verification--measurement-discipline-read-first--applies-to-every-port)
     section of this SKILL.md + its
     [reference file](references/verification-measurement-discipline.md), so it is
     loaded on **every** run. Do not bury a process rule in a leaf spec (it would
     only fire when one intrinsic matches); do not put an intrinsic mapping in the
     global section (it would bloat every run). Same promotion bar applies: merge
     into the shared tree only when confirmed on a **real** workload; a
     synthetic/single-datapoint lesson stays a candidate in `PERF-PROGRESS.md` +
     memory until corroborated.

   **Keep the spec GENERAL — write the transferable rule, not the incident report
   (standing rule).** A spec must guide *a whole class* of future ports, not
   document one project's outcome. When capturing a lesson:
   - **State the rule and the mechanism** (the x86 construct → the NEON
     construct, and *why*: which hardware capability or latency/throughput fact
     drives it). That is what transfers. Cite the specific project/measurement as
     *supporting evidence in one clause*, not as the rule itself. ("Prefer
     `vcntq_u8` for a per-byte popcount because ARM has hardware popcount" is
     general; "sse-popcount is 12% faster" is an incident.)
   - **Match rules fire on the CONSTRUCT, not the codebase** — regex the x86 source
     pattern (`_mm_mul_epu32`, `_mm_add_ps`, `_mm_cmpestrm`) and the NEON-output
     self-check, so the spec surfaces on *any* project using that construct, never
     just the one you tested.
   - **Scope conditions belong in the rule, generalized.** If the win is
     regime-dependent, state the regime as a decision rule others can evaluate
     ("estimate+NR wins *when the reciprocal is the loop bottleneck*"), not a bare
     verdict ("use vrsqrte"). One-off, project-specific facts with no transferable
     shape stay in `PERF-PROGRESS.md`, not the tree.
   - **Do not overfit the magnitude.** A measured speedup is evidence a hand-run
     can inflate (it may be measured against a strawman baseline — see the
     Verification & Measurement Discipline); report it as an honest range/direction
     with the regime that governs it, and prefer the mechanism over the number.
     If unsure whether a lesson is general, widen it or leave it a candidate — an
     over-narrow spec that only matches your one test case is nearly worthless to
     the next port.

See [references/perf-optimize-loop.md](references/perf-optimize-loop.md) for the
full rationale, prerequisites, and an illustrative capture example. Note that a
lesson is only merged into the shared skill tree when it is confirmed on a
**real** port; a win measured on a synthetic/test workload is recorded in
`PERF-PROGRESS.md` only.

### 8.5.2 Terminal exit (the driver ALWAYS returns one)

- **`CONVERGED`** — **no hot leaf remains at or above `hotThresholdPct` self-CPU**
  (default 10%). This is the real stop condition: the top of the profile is now
  the optimized kernel doing genuine irreducible work, not a scalar-fallback
  artifact → proceed to §9.
- **`STALL(reason)`** — profiling could not run (e.g. not elevated), the cap was
  hit with an actionable hotspot still present, no optimization could be applied,
  or the **same hotspot survives `staleStop`+1 rounds with no accepted speedup**.
  Do **not** treat perf as done; report the surviving hotspot and the most likely
  next action. A STALL here does **not** block archive (§9) — correctness already
  passed §8 — but it is surfaced prominently in the final report.

The driver returns `{ status, reason, iterations, acceptedOptimizations,
lessonsCaptured, finalTotalCpuMs, history, progressLog }`; cross-round state is in
`openspec/changes/<change>/PERF-PROGRESS.md`.

---

## 9. OpenSpec Archive (only on verified green)

Only when §8 converged **and** the negative-control evidence exists:

1. **Checkpoint gate (§1.3):** present the final tally — whole-project build
   status, the project's own test/bench pass count, list of `[NEEDS REVIEW]`
   kernels (if any), the negative-control record, and (if §8.5 ran) the
   performance result: accepted optimizations with measured speedups, any
   lessons captured into leaf skills, and any perf STALL.
2. Run the OpenSpec archive flow (skill `openspec-archive-change` /
   `opsx:archive`) to finalize the change.
3. Write the final state file entry.

Never archive a change with a red or unverified suite, an unresolved
`[NEEDS REVIEW]` kernel that the project tests actually exercise, or a build that
does not fully link. Report and stop instead.

---

## 10. Final Report

Synthesize the driver's return value (`status`, `iterations`, `finalTests`,
`needsReview`, `history`) plus `OUTER-PROGRESS.md` into a markdown report: phases
run; scan item count; inner-loop results (verified / needs-review / skipped per
kernel); integration wiring performed; outer-loop history per iteration (what
failed, what was fixed, and crucially **which fixes an independent verifier
confirmed vs. refuted**, with negative-control status); final whole-project build
+ project-test tally; and — if `STALL` — the exact blocker and single most likely
next action. If §8.5 ran, add a **performance** section from the perf driver's
return (`acceptedOptimizations`, `lessonsCaptured`, `finalTotalCpuMs`) plus
`PERF-PROGRESS.md`: each accepted optimization with its **independently measured**
speedup and negative-control status, each lesson captured back into a leaf skill
(skill/spec id), and any perf STALL with the surviving hotspot. This report is the
artifact the user reads; be faithful (state skipped steps, unverified greens,
refuted approaches, unverified/rejected optimizations, and failures plainly — a
green never seen red is reported as unverified, not passing; a speedup the
verifier did not re-measure is reported as unverified, not achieved).

---

## Relationship to the other skills (do not duplicate them)

| Concern | Owned by | This skill's role |
|---|---|---|
| Scan → porting report | `arm64-porting-report` | invoke it (§2) |
| Spec match + tasks.md + inner verify/retry loop | `easywos-spec` (§2–8) | invoke it (§4, §5); pass K |
| Per-item routing / feedback re-entry | `dispatcher-skill` | invoked by easywos-spec and by §8 test-failure routing |
| Actual migration | leaf skills | invoked by the dispatcher |
| Build-system detect/enable | `enable-windows-arm64` | invoke it (§6, §7.1) |
| Post-port CPU profiling + root-cause | `profiling` skills | invoke them inside the §8.5 driver |
| Capture a verified optimization into a spec | `leaf-skill-creator` + the leaf skills | invoked by the §8.5 Capture stage |
| **Whole-project integrate → build → project-test → auto-fix → archive** | **this skill** | **owns the OUTER loop** |
| **Post-port profile → optimize → verify → capture** | **this skill** | **owns the PERF loop (§8.5)** |

The orchestrator adds two things the tree lacked: the **outer integration loop**
that carries individually-correct kernels all the way to "the whole open source
project builds and passes its own tests on ARM64," and the **post-port
performance loop** (§8.5) that catches correct-but-slow ports, optimizes them
under independent correctness+speedup verification, and **feeds each verified
technique back into the leaf skills** — plus the end-to-end sequencing of
propose→apply→(perf)→archive around them.

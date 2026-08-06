# Post-Port Performance Optimization Loop

This is the reference for **§8.5** of the orchestrator — the phase that runs
**after** a project builds and passes its own tests on ARM64 (§7/§8 CONVERGED),
to catch the class of defect functional tests cannot: a port that is **correct
but slow**.

A migration can pass every correctness gate and still leave a large performance
regression — most commonly an x64 SIMD path that was ported to a **scalar
fallback** (per-element `fminf`/`sqrtf`/`expf`, a NEON block gated out by an
`#ifdef __GNUC__` guard, a `portable::`/`generic::` path with no ARM64
specialization). The inner and outer loops never see it: the gtest is green, the
project test suite is green. Only a **profiler** surfaces it. This loop closes
that gap and — crucially — **feeds what it learns back into the skill tree** so
the next port does not repeat the mistake.

---

## Why this is a loop, not a one-shot pass

The same three-layer decision model as the outer loop (SKILL.md §"loop
engineering"):

- **① Orchestration decision** — *profile, is this hotspot worth fixing, loop
  again, or stop?* — is **deterministic code** in
  [assets/perf-optimize-loop-driver.js](../assets/perf-optimize-loop-driver.js),
  run via the Workflow tool. The **stop condition is owned by this code**, read
  from the objective profile numbers, never left to an agent's opinion.
- **② Task decision** — *how do I optimize this one hotspot* — is delegated to a
  bounded optimizer agent (one hotspot, its owning source only, a leaf-skill
  technique).
- **③ Judgement decision** — *is it still correct AND actually faster* — is an
  **independent** verifier: a negative-control correctness check **and** a
  self-measured speedup. Decision ≠ verification; a speedup claimed by the
  optimizer is not trusted until the verifier re-measures it.

One profile→optimize→verify pass is not enough because fixing the top hotspot
**reveals the next one** (Amdahl): once the scalar `expf` is vectorized, the loop
re-profiles and may find a second hotspot (a memcpy, a lock) now dominating. The
loop repeats until the stop condition holds.

---

## The stop condition (owned by the driver, from the numbers)

The driver terminates with exactly one of two outcomes — it never hangs and
never leaves "are we done?" to an agent:

- **CONVERGED** — **no hot leaf remains at or above `hotThresholdPct` self-CPU
  (default 10%).** This is the real "no significant performance problem left"
  signal. The residual top-of-profile is then the optimized kernel itself doing
  genuine, irreducible work (e.g. `process_frames` after vectorization), not a
  scalar-fallback artifact.
- **STALL(reason)** — profiling could not run (e.g. not elevated), the iteration
  cap (`maxIters`, default 6) was hit with an actionable hotspot still present,
  no optimization could be applied to the top hotspot, or the **same hotspot
  survives `staleStop`+1 rounds with no accepted speedup** (the no-progress
  guard). A STALL is reported, not archived; the surviving hotspot and the most
  likely next action are handed to a human.

An optimization is only **accepted** when the independent verifier confirms
**both**:
1. **correctness** — the scalar-vs-optimized check passes *and was watched going
   red under a deliberate perturbation* (negative control), and
2. **speedup** — a re-profile/timing the verifier ran itself shows the hotspot's
   self-CPU dropped by at least `minSpeedupPct` (default 5%).

A speedup obtained by shrinking the workload, loosening the tolerance, or
deleting work is explicitly rejected.

---

## Lesson capture (the feedback into the skill tree)

This is what makes the loop part of *easywos-skills* rather than a standalone
profiler. On each **accepted** optimization the driver runs a **Capture** phase:

1. Decide if the technique is **generalizable** (a pattern other ports will hit)
   or a **one-off** (project-specific). One-offs are recorded only in
   `PERF-PROGRESS.md`; they do **not** touch the skill tree.
2. For a generalizable technique, add **one new pattern** to the best-fitting
   leaf skill — prefer extending an existing spec pair
   (`references/specs/<topic>.md` + `.yaml`) over creating a new one; use
   `leaf-skill-creator --add-yaml` for a genuinely new dimension. The new spec
   entry follows the exact structure of its neighbors and — the part unique to a
   profile-derived lesson — its **Validation** block records the **profiler
   signature** that identifies the anti-pattern (e.g. *"hot leaf was
   `module!expf` at ~15% self-CPU"*), so future screening and review can point
   to it.
3. Regenerate the combined index:
   `node skills/dispatcher-skill/scripts/combine-specs.js`.

The match rules of the captured spec are written to fire on **both** the x86
source construct (so `easywos-spec` screening surfaces the pattern *before* the
same mistake is made) and the NEON-output self-check (so review catches it
*after*). That is the loop closing: a perf defect found once becomes a spec that
prevents or flags it next time.

> **Illustrative example of a capture.** Suppose profiling a ported kernel shows
> ~50% of CPU in scalar `fmaxf`/`fminf`/`expf` (an x64 SIMD path that came across
> as a per-element scalar fallback). The optimizer vectorizes it to
> `vminq`/`vmaxq`/`vsqrtq` + a NEON polynomial `exp`; the verifier confirms
> correctness (negative control) and a real speedup. The Capture stage would then
> add a `neon-performance-patterns`-style spec to `sse-avx-to-neon` whose match
> rules fire on the x86 packed-float / scalar-libm construct **and** the
> NEON-output self-check, and whose Validation block records the profiler
> signature (*"hot leaf was `module!expf` at ~15% self-CPU"*) — so the next port
> is screened for it. This is only captured when the win is confirmed on a **real**
> port; a lesson derived from a synthetic/test workload is recorded in
> `PERF-PROGRESS.md`, not merged into the shared skill tree.

---

## Invocation

The orchestrator invokes the driver once the ARM64 build is green (§8 CONVERGED)
and a runnable, terminating workload is known:

```
Workflow({ scriptPath: "<skills>/arm64-port-orchestrator/assets/perf-optimize-loop-driver.js",
           args: { projectPath, runTarget, runArgs, buildCmd, matchedYaml,
                   skillsRoot: "<skills>",
                   stateDir: "openspec/changes/<change>/",
                   sourceMap: "<module=src;...>",
                   hotThresholdPct: 10, minSpeedupPct: 5, maxIters: 6,
                   captureLessons: true } })
```

The driver returns
`{ status: CONVERGED | STALL, reason, iterations, acceptedOptimizations, lessonsCaptured, finalTotalCpuMs, history, progressLog }`.

### Prerequisites and honest limits

- **Trace capture needs an elevated shell** (kernel CPU sampling). If the host is
  not elevated, the Profile stage reports failure and the driver STALLs with that
  reason — it does not silently skip profiling and claim success.
- **Symbols matter.** If `unresolvedPct > 5`, module/function rankings are less
  trustworthy (weak PDB coverage); the driver surfaces the number so a human can
  judge. Provide `sourceMap` so `perf-optimizer` can locate hot functions in
  source and classify x64-SIMD-vs-NEON gaps.
- **The workload must terminate.** PerfView `run` stops sampling when the target
  exits; a server workload needs a terminating benchmark, or the collection times
  out. Pick a workload representative of the ported kernels' hot path.
- This loop is **optional and additive**: it runs after correctness is already
  established and never weakens a correctness gate to gain speed.

# Verification & Measurement Discipline (cross-cutting, all ports)

These are **process** rules learned across many real ARM64 porting runs. They are
not about a specific intrinsic — they apply to *every* §5 correctness check and
every §8.5 measurement, regardless of the kernel. A port that skips them can
report a false green or a false speedup. Keep them loaded for the whole flow.

Each rule below states the trap, the rule, and the concrete failure it was
learned from.

---

## 1. A negative control must be sized to EXCEED the tolerance

**Trap.** You add a negative control (deliberately corrupt the computed side and
confirm the check goes red). But if the perturbation is *smaller* than the check's
own tolerance, the corrupted result still passes — the negative control reports
green, and you wrongly conclude "the check can catch errors" when it cannot.

**Rule.** Size the perturbation so the induced error is clearly **larger** than
the pass tolerance. Prefer a perturbation whose magnitude you can reason about
(flip a mantissa bit ≈ ×√2 relative error; scale an input ±50%), not a 1-ULP /
±1-bit nudge. Then confirm red, revert, confirm green.

**Learned from.** fmath run (exp_ps, tol 1e-5): a `+1`-bit corruption was smaller
than the tolerance, so the negative control *passed* — it was silently useless.
Changed to flip a mantissa bit (`veorq 0x00400000`) → reliably red.

---

## 2. The oracle must match the SEMANTICS/LAYOUT of the thing you ported

**Trap.** You compare the NEON port against a "reference" that computes the same
*conceptual* result by a different route — a different recurrence, a different
memory layout, a different rounding rule. The check fails (or passes) for reasons
that have nothing to do with the port's correctness.

**Rule.** The oracle must mirror exactly what the ported kernel computes:
- Port an **AVX/SSE kernel** → the oracle is that kernel's exact arithmetic, not
  the library's textbook scalar version (they can differ, including dead code
  that changes the result).
- Port a **SIMD-laid-out** kernel → verify against its own layout (round-trip:
  `unpack(pack(x)) == x`), not against a naïve linear scalar layout.
- Watch rounding: `vcvtnq_s32_f32` (round-to-nearest) ≠ truncating `vcvtq`, and ≠
  scalar `lrintf` tie-breaking — a mismatch here is an oracle bug, not a port bug.

**Learned from.** (a) SIMDxorshift: the AVX kernel's `s1 = part2 ^ (part2<<23)`
differs from the lib's scalar xorshift128+ (the `s1=part1` line is dead code) —
first verify failed against the wrong oracle. (b) SIMDComp pack5: the SIMD packer
is SoA-transposed, so packed bytes ≠ the linear scalar layout; round-trip identity
is the valid oracle.

---

## 3. Near-zero references need an ABS-OR-RELATIVE tolerance

**Trap.** A pure **relative** error metric blows up when the reference value is
near zero (tiny absolute differences become huge relative ones), flagging correct
results as failures. A pure **absolute** metric misses real errors on large
values.

**Rule.** Pass if **either** `abs_err < abs_tol` **or** `rel_err < rel_tol`. Pick
`abs_tol` from the domain's noise floor and `rel_tol` from the algorithm's design
accuracy.

**Learned from.** fastapprox vfastlog2: near `log2(x) ≈ 0`, a pure-relative
tolerance flagged 41/1.2M correct results. Abs-or-relative fixed it; the port was
correct all along.

---

## 4. Defeat benchmarking traps: loop-hoisting & first-touch

**Trap.** (a) **Loop-hoisting / dead-store elimination** — the optimizer sees the
loop's output is unused (or invariant) and hoists or deletes the work, so you time
nothing. Symptom: a "2M-iteration" run finishes faster than a "1M" one, or timing
is implausibly low. (b) **First-touch page faults** — the first pass pays
page-zeroing/cache-fill cost that dominates a short run, so you measure the OS,
not the kernel.

**Rule.**
- Make **every** result live: serial-dependent inputs (each iteration consumes the
  previous output), consume *all* outputs, and write the running total to a
  `volatile` global sink.
- Use **large** iteration counts and **subtract a warmup** pass so you measure
  steady state (~6s+ of real work).

**Learned from.** Nearly every profiling workload in these runs (nbody, sx, sbp,
popcount, …) initially hoisted; fixed with serial dependency + volatile sink +
hundreds of millions of iters.

---

## 5. Decide A-vs-B by PAIRED back-to-back measurement, not single-ETL magnitude

**Trap.** You collect one ETL for variant A and, minutes later, one for variant B,
then compare their absolute CPU-ms. System load drifts between the two collections
(background work, thermal, frequency scaling), so the magnitudes are not
comparable — the "winner" can be an artifact of *when* each was collected.

**Rule.** To decide which of two implementations is faster, run them **back-to-back
and alternating** (A,B,A,B,…) several rounds and compare paired wall-clock times.
Use the **profiler for attribution** (is the hot leaf genuine kernel work, or a
fallback/emulation?), **not** for cross-collection magnitude comparison.

**Learned from.** nbody rsqrt A-vs-B: the two ETLs' CPU-ms (5162 vs 3446) were
non-comparable (collected minutes apart); paired back-to-back wall-clock
(A=3.18s vs B=3.57s, 5 alternating rounds) gave the reliable verdict.

---

## 6. Faithfulness over completion (reporting)

State skipped/unverified steps plainly. A green never seen red is **unverified**,
not passing. A speedup the verifier did not re-measure is **unverified**, not
achieved. A win measured on a synthetic/test workload stays a **candidate**
(PERF-PROGRESS.md + memory) and is merged into the shared skill tree only after a
**second** corroborating measurement on a real workload — a single counterintuitive
datapoint can be loop-specific and flip in another regime.

**Learned from.** fastapprox `vdivq`-vs-`vrecpe` stayed a candidate after one run;
it took the opposite-regime nbody datapoint to promote the bottleneck-dependent
rule (neon-performance-patterns §13).

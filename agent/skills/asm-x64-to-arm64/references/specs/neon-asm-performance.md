# NEON Hand-Written Assembly Performance Patterns

A correct translation is **not** a finished port. The other specs in this skill
make the arm64 asm *produce the right numbers*; this one makes it *fast*. The
dominant failure mode of a mechanical x86→arm64 asm port is a kernel that passes
every correctness test yet runs at roughly **half** the speed of a hand-tuned
arm64 kernel — not because of a missing instruction, but because the x86 *shape*
(scalarized horizontal reductions, per-operation constant materialization,
full-matrix inner products) was transliterated instead of re-derived for the
NEON pipeline.

These are **baseline `armv8-a` NEON** patterns — no DotProd/i8mm/SVE required
(for those, see [[neon-isa-extensions-dispatch]]). They apply to any compute
kernel with a hot inner loop: transforms (DCT/DST/FFT/wavelet), FIR/IIR filters,
convolution, matrix multiply, correlation/similarity metrics, colour-space
conversion, and similar image/video/audio/DSP code. For the streaming/checksum
family (64B unroll, deferred multiply, multiple accumulators, alignment
preamble) see the intrinsics-side `neon-performance-patterns` spec in
`sse-avx-to-neon`; the patterns here are the ones that bite hand-written *asm*
compute kernels.

---

## 1. Horizontal reduction: `addv`-per-output is an anti-pattern

**Symptom in the x86-shaped port.** A matrix/transform/dot-product kernel
computes one output by doing a full-length inner product across a vector, then
collapses the vector to a scalar with `addv` and stores that single element.
Repeat per output. A size-N kernel with two passes then executes on the order of
N² such reductions (e.g. N=32 → ~2048 `addv` + 2048 single-element stores).

```gas
// ANTI-PATTERN: one full-width horizontal reduce + one scalar store per output
smull   v28.4s, v0.4h, v1.4h        // partial products for ONE output element
smlal2  v28.4s, v0.8h, v1.8h
...                                  // accumulate the length-N inner product
addv    s28, v28.4s                 // full-width horizontal reduce → 1 scalar
fmov    w9, s28
strh    w9, [x1], #2                // store ONE element, then repeat per output
```

`addv` is a **full-width horizontal reduction**: on out-of-order cores it is a
long-latency, serializing operation, and each one yields exactly one output
element (plus a single-element store). Doing it per output is the single worst
throughput mistake in this class of kernel.

**The fix — keep the reduction vertical, produce N outputs at once.** Arrange the
computation so that lane `k` of an accumulator holds output `k` (not a partial of
output 0). Then no horizontal reduction is needed at all; a batch of outputs is
narrowed and stored together. When a horizontal combine is genuinely required,
use pairwise `addp` trees that produce **4 outputs per reduction**, not `addv`
that produces one:

```gas
// GOOD: pairwise tree reduces four independent lane-sums into four outputs,
// then one rounding-narrow + one 64-bit store emits all four at once.
addp    v0.4s, v0.4s, v1.4s         // {Σa, Σb, Σc, Σd} pairwise, no full-width reduce
addp    v0.4s, v0.4s, v0.4s
sqrshrn v0.4h, v0.4s, #SHIFT        // round+narrow 4 lanes together
str     d0, [x1], #8                // store 4 outputs in one instruction
```

**Even better — restructure so outputs land in lanes naturally** (see §4 for the
transform case) and the reduction disappears entirely.

**Validation**
- No `addv` inside a per-output loop of a reduction/matrix/transform kernel. An
  `addv` whose result feeds a single-element store, repeated per output, is the
  fingerprint of the anti-pattern.
- Horizontal combines, when unavoidable, use `addp`/pairwise trees that emit ≥4
  outputs per reduction and a single wide store.

---

## 2. Constant coefficients: materialize once, use by-element lanes

**Symptom in the x86-shaped port.** Each multiply-accumulate re-loads its constant
coefficient into a register via `mov`+`dup` immediately before the `mul`/`mla`.

```gas
// ANTI-PATTERN: materialize each constant right before every multiply
mov     w15, #64
dup     v25.4s, w15                 // materialize constant EVERY multiply
mul     v20.4s, v16.4s, v25.4s
mov     w15, #83
dup     v26.4s, w15
mla     v20.4s, v17.4s, v26.4s
...
```

The `mov`+`dup` pair is pure overhead repeated on the critical path, wastes a GP
register and a SIMD port per coefficient, and bloats the loop. This bites any
fixed-coefficient kernel: FIR taps, transform matrices, colour-conversion
constants, fixed-point scale factors.

**The fix — load the coefficient table once, use by-element multiply.** `armv8-a`
supports the by-element form `smull/smlal/mul/mla vD.4s, vN.4h, vM.h[lane]` (and
`.8h`/`.4s` variants). Pack the (few) constants into one or two vector registers
outside the loop and index them by lane:

```gas
// GOOD: coefficients live in v7 for the whole kernel; MAC reads a lane directly
ld1     {v7.8h}, [x_coef]           // constants loaded ONCE, before the loop
...
smull   v20.4s, v16.4h, v7.h[0]     // × coeff 0, no mov/dup
smlal   v20.4s, v17.4h, v7.h[1]     // × coeff 1
smlal2  v20.4s, v16.8h, v7.h[0]     // high half, same lane
```

This removes the per-MAC `mov`+`dup`, frees the GP register, and shortens the
dependency chain.

**Pitfalls**
- By-element lane index must be a compile-time constant, and for the `.h[]`
  element form some assemblers require the source register in the low 16
  (`v0`–`v15`) — keep the coefficient vector in a low register.
- A `.8h`/`.4s` constant vector holds 8/4 coefficients; if a kernel needs more,
  use a second register rather than falling back to `mov`+`dup`.

**Validation**
- No `mov wN,#imm; dup vN, wN` pair on the multiply critical path. Constants are
  loaded once (via `ld1`/literal pool) before the loop.
- Multiplies by a constant use the by-element form `…vN.4h, vM.h[lane]`.

---

## 3. Accumulator width: stay narrow while the magnitude bound allows

**Symptom in the x86-shaped port.** A kernel accumulating 8-bit terms
(sum-of-absolute-differences, sum-of-squared partials, Hadamard/transform partials
over byte data) promotes every partial straight to 32-bit "to be safe", one
`uaddl`/`saddl` per term. A `.8h` (16-bit) datapath processes **twice** the lanes
per instruction as `.4s`, so widening earlier than the running sum actually needs
throws away half the throughput.

The safe window is set by the accumulator's worst case,
`max_addend × addends_per_lane`:
- An unsigned-8-bit sum in a `.8h` lane holds up to `65535 / 255 ≈ 257` byte
  addends before it can overflow. A block metric summing far fewer than that per
  lane (an 8×8 or 16×16 block) is provably safe in 16-bit.
- Keep the inner loop in `.8h` (`uabd`+`uadalp`, or `add`/`abs` on `.8h`) and
  widen to `.4s` (`uaddlp`/`uadalp`) only at the **cross-block reduction**, where
  the addend count would otherwise push a lane past the 16-bit bound.

```gas
// GOOD: inner accumulation stays 16-bit (2× lane throughput), widen once at the end
uabd    v4.8h, v0.8h, v1.8h          // per-row abs-diff, 8 lanes
uadalp  v16.4s, v4.8h                // (only at block boundary) widen+accumulate
```

This is the throughput counterpart of the correctness rule in [[simd-sse-to-neon]]
("pre-combined sums must fit the lane width"): that rule is a *floor* (too narrow
→ wrong numbers), this is the *ceiling* (too wide → half speed). Decide the width
from the magnitude bound in **both** directions — widen when the product can
exceed the type, stay narrow when it provably cannot.

**Validation**
- 8-bit metric/reduction kernels keep the inner accumulation in `.8h`, widening to
  `.4s` only at the block/reduction boundary — not a `uaddl` per partial.
- The chosen accumulator width is justified by `max_addend × addends_per_lane`
  against the type's range.

---

## 4. Separable transforms: butterfly beats full-matrix multiply

**Symptom in the x86-shaped port.** A separable transform (DCT/DST/FFT/Hadamard
and similar row-then-column kernels) multiplies the input by the full N×N
coefficient matrix — N inner products of length N per row — instead of using the
transform's **butterfly** decomposition (for a DCT: the E/O, EE/EO, EEE/EEO
even/odd folds; for an FFT: radix butterflies).

Full-matrix cost is ~N² multiplies per row; the butterfly is a fraction of that,
and it also *structures the data so outputs land in lanes* — which is what lets
§1's `addv` disappear. It is faster **and** more robust:

- **Speed:** far fewer multiplies; no per-output horizontal reduction.
- **Robustness — it structurally avoids the intermediate-overflow trap.** The
  butterfly widens as it folds: a sum like `E = a + b` is taken with
  `saddl`/`saddl2` to `.4s` from the start, so intermediates that exceed the
  narrow type never wrap. A full-matrix port, by contrast, is where the
  "pre-combined sums must fit the lane width" correctness bug (see
  [[simd-sse-to-neon]]) keeps recurring, because widening is bolted on as an
  afterthought.

```gas
// SHAPE of a butterfly (per 1-D pass): fold first, widen while folding, then the
// folded groups multiply into lanes — outputs end up in lanes, so the store is a
// batched narrow, not an addv-per-output.
saddl   v_e.4s, v_a.4h, v_b.4h      // E = a + b, widened to 32-bit immediately
ssubl   v_o.4s, v_a.4h, v_b.4h      // O = a - b
// ... further EE/EO folds, then by-element multiply of E/O by the half-matrix ...
```

**Use an existing correct kernel as the template, not the x86 asm.** If the
codebase already has *some* correct arm64 transforms (e.g. one direction or one
size done right — column-parallel butterflies with `trn1/trn2` transposes and no
`addv`), copy that structure for the ones still on full-matrix + `addv`. Do not
re-translate the x86 matrix multiply.

**Transpose the register way, not by strided gather.** Full-matrix ports tend to
build the second-pass columns with per-lane strided loads (`ld1 {v0.h}[i], [x],
stride` ×N) or per-lane scatter stores — both slow and a notorious source of the
transpose-order bug ([[simd-sse-to-neon]] "separable transforms must mirror the
reference's pass/transpose order"). Use in-register
`zip1/zip2/uzp1/uzp2/trn1/trn2` transposes instead; they are faster and eliminate
that whole bug class.

**Correctness guard rail (do not skip).** When restructuring a transform for
speed, the rounding/shift semantics must still match the reference bit-exact if
that is the contract: keep the reference's rounding form (e.g. **floor** via
`add #round; sshr`) rather than switching to `srshr`/`sqrshrn` (round-half-away)
just because it is one instruction — negative half-integers differ by 1 and fail
a bit-exact check. Prove the failure path first: feed a known-wrong shift and
confirm the numeric harness (with all-min / all-max / alternating-±max boundary
vectors) reports failure *before* trusting the green run.

**Validation**
- A separable transform uses its butterfly decomposition (widening folds like
  `saddl`/`ssubl`), not an N-length full-matrix inner product per output.
- Second-pass columns come from in-register `zip/uzp/trn` transposes, not
  per-lane strided `ld1 {vN.h}[i]` gathers or per-lane scatter stores.
- Rounding/shift form matches the reference (floor vs round-half-away) and is
  verified on boundary inputs with a failure-path (negative-control) check.

---

## 5. When to stop: benchmark against the reference kernel

A hand-written asm kernel is not done at "numerically correct." If a prior or
reference implementation exists (the C fallback, an upstream arm64 kernel, or a
previous version), build both and compare throughput on a realistic workload. A
materially slower result almost always traces to one of §1–§4:

- per-output `addv` where a batched pairwise reduce (or butterfly) belongs (§1),
- `mov`+`dup` constant materialization on the MAC critical path (§2),
- widening the accumulator earlier than the magnitude bound requires (§3),
- full-matrix multiply where a butterfly belongs (§4).

Fix the shape, then re-measure. Apply the same "prove the check can fail before
trusting a pass" discipline to the *performance* check that the correctness specs
demand for numeric checks: confirm the benchmark actually distinguishes a
known-slow build from the tuned one before quoting a speedup.

> The concrete figures in §1–§2 (e.g. ~2048 `addv` in a 32-point two-pass
> transform, hundreds of `mov`+`dup` per pass, ~2× overall) come from a measured
> real-world video-codec transform port; the patterns themselves are general to
> any reduction/coefficient/transform kernel.

## See Also

- [[simd-sse-to-neon]] — SIMD mnemonic mappings and the **correctness** pitfalls
  (stale lanes, pre-combined-sum overflow, saturate-vs-wrap, transpose/pass
  order) that these performance restructurings must preserve.
- [[neon-isa-extensions-dispatch]] — the next tier: DotProd/i8mm extension
  kernels + runtime dispatch, when the target CPU has those features.
- `sse-avx-to-neon` → `neon-performance-patterns` — the intrinsics-side,
  streaming/checksum performance patterns (64B unroll, deferred multiply, ≥4
  accumulators, alignment preamble, copy/non-copy split).

# ARM NEON Performance Patterns

---

## General Patterns

### 1. Loop Unrolling: 64B/iter Instead of 16B/iter

A single 16B/iter loop leaves most of the hardware idle. ARM cores typically have 2–4 SIMD execution units and a dual-issue load pipeline, so a loop body with only one `vld1q` + a few arithmetic instructions cannot saturate them. Processing 64 bytes per iteration (four 16-byte vectors) amortizes loop overhead across 4× more work, gives the out-of-order engine enough independent instructions to fill all execution slots, and lets the hardware prefetcher recognise a coarser, more predictable access pattern.

For **non-copy** paths, use `_x4` struct loads — the compiler and hardware get full visibility of the 64-byte stride in a single operation:

```c
uint8x16x4_t d0_d3 = vld1q_u8_x4(buf);
buf += 64;
```

For **copy** paths, use four **separate** loads instead — `_x4` blocks ILP when stores are interleaved:

```c
uint8x16_t d0 = vld1q_u8(buf);
uint8x16_t d1 = vld1q_u8(buf + 16);
uint8x16_t d2 = vld1q_u8(buf + 32);
uint8x16_t d3 = vld1q_u8(buf + 48);
vst1q_u8(dst,      d0);
vst1q_u8(dst + 16, d1);
vst1q_u8(dst + 32, d2);
vst1q_u8(dst + 48, d3);
buf += 64; dst += 64;
```

### 2. Deferred Multiply for Weighted Sums

**Scope condition — read this before applying.** This pattern is valid only when
the multiplier is a **loop-invariant weight** (a constant, a coefficient table, a
per-lane scale): then Σ w[i]·b[i] can be regrouped as Σ over distinct weights of
w·(Σ b), so the multiply leaves the loop. It is **invalid for a data×data
product** — a dot product Σ a[i]·b[i] where both operands change every iteration
cannot defer its multiply at all, because there is nothing to factor out.
Deferring one there produces a *wrong kernel*, not a slow one. So an
`_mm_madd_epi16` / `_mm_maddubs_epi16` match is a *candidate*, not a verdict:
check what the two operands are first. For a genuine data×data product, use
`vmull_s16`+`vpadalq`/`vmlal_s16` (or SDOT/UDOT where the values fit in 8 bits)
with several independent accumulators (pattern 3) instead.

When computing a weighted sum (Σ weight[i]×b[i]) with loop-invariant weights,
**never multiply inside the loop**. Accumulate raw byte sums into `uint16x8_t`
lanes with cheap widening adds, then apply weights once after the loop with
`vmlal_u16`.

```c
// BAD: multiply every iteration
uint16x8_t wsum = vmull_u8(vget_low_u8(vbuf), weights_lo);
wsum = vmlal_u8(wsum, vget_high_u8(vbuf), weights_hi);
acc = vaddq_u32(acc, vpaddlq_u16(wsum));  // in the loop

// GOOD: cheap widening adds in loop, one multiply pass at end
// -- inside loop --
s2_lo = vaddw_u8(s2_lo, vget_low_u8(d0));   // uint8 → uint16, no multiply
s2_hi = vaddw_high_u8(s2_hi, d0);

// -- after loop --
acc = vmlal_u16(acc, vget_low_u16(weights), vget_low_u16(s2_lo));
acc = vmlal_high_u16(acc, weights, s2_lo);
```

Before applying: verify uint16 won't overflow. Bound = iterations × max_byte_value × lanes_per_accumulator < 65535.

### 3. Multiple Independent Accumulators for ILP

A single accumulator serializes execution. Split into 4 independent accumulators and reduce once at the end:

```c
// BAD: serial chain — each iteration waits for the previous
acc = vaddq_u32(acc, weighted_sum);

// GOOD: 4 independent accumulators — CPU can issue all 4 multiply-adds in parallel
uint32x4_t acc0 = vdupq_n_u32(0);
uint32x4_t acc1 = vdupq_n_u32(0);
uint32x4_t acc2 = vdupq_n_u32(0);
uint32x4_t acc3 = vdupq_n_u32(0);
// ... fill each with a different vmlal_u16 subset ...

// Reduce once at the end
uint32x4_t acc = vaddq_u32(vaddq_u32(acc0, acc1), vaddq_u32(acc2, acc3));
```

**This applies to FLOAT accumulators too — and a faithful SSE→NEON port silently
inherits the stall.** Many SSE kernels (dot products, FIR filters, norms) keep a
single `__m128 sum` chained across the loop because on x86 it was "good enough".
Transliterating that 1:1 to a single `float32x4_t sum` with `vaddq_f32`/`vmlaq_f32`
makes every iteration wait on the previous FADD/FMLA (**latency ~3-4 cyc**), even
though the core has 2+ FP pipes idle — the loop is **latency-bound, not
throughput-bound**. Use ≥4 independent `float32x4_t` accumulators with `vfmaq_f32`
(fused multiply-add, one rounding) and a single `vaddvq_f32` reduce at the end
(§6):

```c
// FAST: independent FP accumulator chains, fused MAC, reduce once
float32x4_t s0=vdupq_n_f32(0), s1=vdupq_n_f32(0), s2=vdupq_n_f32(0), s3=vdupq_n_f32(0);
for (i = 0; i + 16 <= len; i += 16) {
    s0 = vfmaq_f32(s0, vld1q_f32(a+i),    vld1q_f32(b+i));
    s1 = vfmaq_f32(s1, vld1q_f32(a+i+4),  vld1q_f32(b+i+4));
    s2 = vfmaq_f32(s2, vld1q_f32(a+i+8),  vld1q_f32(b+i+8));
    s3 = vfmaq_f32(s3, vld1q_f32(a+i+12), vld1q_f32(b+i+12));
}
float r = vaddvq_f32(vaddq_f32(vaddq_f32(s0,s1), vaddq_f32(s2,s3)));  // reduce once (§6)
```

**Measured (speexdsp `inner_product_single` FIR resampler kernel, Windows ARM64
clang-cl, 128 taps, 550M calls): faithful single `float32x4_t` accumulator
4.69 s CPU vs 4-accumulator+`vfmaq` 2.35 s CPU — ~1.65-2× faster**, both verified
against a scalar dot-product oracle (identical result) and both 99.4% self-time in
the inlined kernel (no fallback).

**Profiler signature (how §8.5 surfaces this):** the kernel is a top self-time leaf
doing genuine FP work (no fallback, no libm), but per-iteration throughput is far
below the core's FP-pipe width — the tell is that adding independent accumulators
(A/B, paired back-to-back per the measurement-discipline rule) yields a large
speedup with byte-identical output.

### 4. Alignment Preamble Before the SIMD Loop

Align `src` to a natural SIMD boundary (16 or 32 bytes) before entering the vectorized loop to avoid cacheline-crossing penalties:

```c
// Process unaligned head with scalar code
size_t head = (-(uintptr_t)src) & 15;  // bytes to next 16-byte boundary
head = head < len ? head : len;
for (size_t i = 0; i < head; i++)
    scalar_process(src[i]);
src += head;
len -= head;
// src is now 16-byte aligned — safe to use aligned loads
```

### 5. Separate Hot-Path Functions for Copy vs Non-Copy

An `if (copy)` branch inside the SIMD loop adds branch prediction pressure and prevents the compiler from optimising each path independently. Provide two separate inner functions and branch outside:

```c
static void process_neon(uint32_t *s, const uint8_t *buf, size_t blocks);
static void process_neon_copy(uint32_t *s, uint8_t *dst, const uint8_t *buf, size_t blocks);

// Branch is outside the hot loop
if (copy)
    process_neon_copy(state, dst, src, n >> 4);
else
    process_neon(state, src, n >> 4);
```

---

## Compute-Kernel Patterns (DSP / transforms / filters)

Patterns §1–§5 target **streaming/bandwidth-bound** loops (checksums, compare,
hash, copy — one uniform op over a large array). A second family of hot kernels
is **compute-bound**: transforms (DCT/DST/FFT), FIR/IIR filters, convolution,
matrix multiply, correlation/similarity metrics — many multiply-accumulates over
small fixed-size blocks. These have their own two anti-patterns when an
`_mm_*`/`_mm256_*` kernel is transcribed to NEON intrinsics. (The hand-written
**asm** form of these lives in `asm-x64-to-arm64` →
`neon-asm-performance`; this is the intrinsics form.)

### 6. Horizontal Reduction: Reduce 4 Outputs at Once, Not 1

An inner-product/reduction kernel computes each output by multiplying across a
vector, then summing the vector to a scalar. The x86 shape reaches for a
horizontal add (`_mm_hadd_epi32`, or the SSE "shuffle + add" reduction idiom) per
output. Transcribed literally, each output triggers a **full-width horizontal
reduction** (`vaddvq_s32`) plus a single-element store — a long-latency,
serializing op repeated N times.

```c
// BAD: full-width horizontal reduce per output element
int32x4_t prod = vmull_...            // partial products for ONE output
int32_t   out  = vaddvq_s32(prod);    // full-width reduce -> 1 scalar
dst[k] = out;                         // one store, repeat per output
```

```c
// GOOD: keep the reduction vertical — lane k accumulates output k, so a whole
// vector of outputs is produced without any horizontal reduction:
acc = vmlal_lane_s16(acc, in, coeffs, 0);   // 4 outputs accumulate in 4 lanes
// ...
vst1q_s16(dst, vqrshrn_high_...(narrow(acc))); // narrow+store 4+ outputs at once

// If a horizontal combine is truly unavoidable, use PAIRWISE adds that yield 4
// outputs per reduction, not vaddvq per output:
int32x4_t r = vpaddq_s32(vpaddq_s32(t0, t1), vpaddq_s32(t2, t3)); // {Σt0..Σt3}
```

`vaddvq_*` (and the `vadd` + `vget_lane` reduction chain) is the intrinsics twin
of asm `addv`; one-per-output is the single worst throughput mistake in this
kernel class. Arrange lanes so output `k` lives in lane `k`, or reduce with
`vpaddq`/`vpadd` trees that emit ≥4 results per reduction.

**Validation**
- No `vaddvq_*` (or `vadd`+`vget_lane` reduction) inside a per-output loop of a
  reduction/transform kernel.
- Outputs are produced a vector at a time (lane k = output k), or horizontal
  combines use `vpaddq`/`vpadd` trees emitting ≥4 outputs per reduction.

### 7. Fixed Coefficients: Load Once, Multiply by Lane

A fixed-coefficient kernel (FIR taps, transform matrix, colour-conversion
constants, fixed-point scales) that transcribes each x86 broadcast-then-multiply
(`_mm_set1_epi16(c)` + `_mm_mullo_epi16`) into a per-multiply `vdupq_n_*` rebuilds
the constant vector on the critical path every MAC.

```c
// BAD: rebuild the constant vector before every multiply
acc = vmlaq_s32(acc, in, vdupq_n_s32(COEFF[k]));   // dup per multiply

// GOOD: load the coefficient vector once, index it by lane
int16x8_t c = vld1q_s16(COEFF);        // once, outside the loop
acc = vmlal_lane_s16(acc, in, vget_low_s16(c), 0); // × c[0], no dup
acc = vmlal_lane_s16(acc, in, vget_low_s16(c), 1); // × c[1]
```

The lane-indexed multiply family (`vmul*_lane*` / `vmla*_lane*` / `vmull_lane*`)
takes the multiplier straight from a lane of a preloaded vector — no `vdupq_n`,
no extra register, shorter dependency chain. This is the intrinsics twin of the
asm by-element `mul vD, vN, vM.h[lane]`.

**Pitfalls**
- The lane index must be a compile-time constant; `vmul*_laneq_*` indexes a
  128-bit vector (8 `int16` lanes), `vmul*_lane_*` a 64-bit half (4 lanes).
- If the kernel needs more coefficients than one vector holds, use a second
  vector rather than reverting to per-multiply `vdupq_n`.

**Validation**
- No `vdupq_n_*` of a constant on the multiply critical path; the coefficient
  vector is loaded once before the loop.
- Constant multiplies use the `_lane`/`_laneq` indexed form.

### 8. Separable Transforms: Butterfly, Not Full-Matrix Multiply

A separable transform (DCT/DST/FFT/Hadamard) coded as a full N×N matrix multiply
does ~N² multiplies per row and forces the §6 per-output reduction. Its butterfly
decomposition (even/odd `E/O` folds for a DCT; radix butterflies for an FFT) does
a fraction of the multiplies, lands outputs in lanes (so §6's reduction
disappears), and — critically for correctness — **widens as it folds**
(`vaddl_s16`/`vsubl_s16` to `int32x4_t`), structurally avoiding the
pre-combined-sum overflow trap that a bolt-on-widening full-matrix port keeps
hitting.

```c
int32x4_t e = vaddl_s16(a, b);   // E = a + b, widened to 32-bit immediately
int32x4_t o = vsubl_s16(a, b);   // O = a - b
// ... EE/EO folds, then vmlal_lane the folded groups by the half-matrix ...
```

Transpose the second pass with `vzipq`/`vuzpq`/`vtrnq` (or `vld4`/`vst4`
de/interleave), not a per-lane strided gather. And when the contract is
bit-exact, keep the reference's rounding form (floor vs `vrshrn` round-half-away)
— see the correctness note in `asm-x64-to-arm64` → `simd-sse-to-neon`
("separable transforms must mirror the reference's pass/transpose order").

**Validation**
- A separable transform uses its butterfly folds (`vaddl`/`vsubl` widening), not
  a full-matrix inner product per output.
- Second-pass transpose uses `vzip`/`vuzp`/`vtrn`/`vld4`, not per-lane gather.

### 9. Don't Reach NEON Through a Generic `_mm_shuffle_epi8` Shim — Use the Native Op

When an x86 SIMD kernel is ported by routing each `_mm_*` intrinsic through a
**generic SSE→NEON translation shim** (a header that maps `_mm_shuffle_epi8` to
`vqtbl1q_u8` + low-nibble mask + `vbic` to emulate PSHUFB's zeroing, `_mm_add_epi32`
to `vaddq_u32`, `_mm_hadd_epi32` to `vpaddq`, etc.), the result is **correct but
slow**. The shim is written to reproduce *arbitrary* x86 semantics, so it emits
extra masking/table-lookup instructions the specific operation never needed. A
profiler shows the kernel hot even though "it's already using NEON."

The fix is to recognise the *operation* and emit the **dedicated NEON instruction**,
not the general shuffle. The canonical case is a one's-complement / checksum /
byteswap-accumulate loop:

```c
// SLOW (correct): x86 path reached via a generic shim
//   _mm_shuffle_epi8(block, swap16_mask)  ->  vqtbl1q_u8 + mask + vbic   (per 16B)
//   widen + _mm_add_epi32                 ->  vaddq_u32
//   _mm_hadd_epi32 x2                     ->  vpaddq_u32 reductions in the loop

// FAST: native NEON, recognise "byteswap each 16-bit word, then widen-accumulate"
uint32x4_t acc0 = ..., acc1 = ...;                 // 2 independent accumulators (§3)
for (; i + 64 <= len; i += 64) {                   // 64B/iter
    acc0 = vpadalq_u16(acc0, vreinterpretq_u16_u8(vrev16q_u8(vld1q_u8(p))));      // p+0
    acc1 = vpadalq_u16(acc1, vreinterpretq_u16_u8(vrev16q_u8(vld1q_u8(p+16))));   // p+16
    acc0 = vpadalq_u16(acc0, vreinterpretq_u16_u8(vrev16q_u8(vld1q_u8(p+32))));   // p+32
    acc1 = vpadalq_u16(acc1, vreinterpretq_u16_u8(vrev16q_u8(vld1q_u8(p+48))));   // p+48
    p += 64;
}
// masked n%16 tail via vcltq_u8(lane_idx, vdupq_n_u8(rem)); then:
uint32_t sum = vaddvq_u32(acc0) + vaddvq_u32(acc1);                              // reduce once (§6)
```

| generic-shim path | native NEON | why the native op wins |
|---|---|---|
| `_mm_shuffle_epi8` byteswap mask → `vqtbl1q_u8` + mask + `vbic` | `vrev16q_u8` | one instruction reverses bytes within every 16-bit word; no table, no zeroing mask |
| shuffle→widen→`vaddq_u32` (3 ops) | `vpadalq_u16` | pairwise-adds 16-bit lanes into 32-bit *and* accumulates, in one instruction |
| `_mm_hadd_epi32` per block | `vaddvq_u32` once after loop | horizontal reduce belongs outside the loop (§6), not per iteration |
| `_mm_shuffle_epi8` nibble-LUT popcount (2 shuffles + mask + shift per vec) → `vqtbl1q_u8`×2 | `vcntq_u8` | ARM has a HARDWARE per-byte popcount; the x86 shuffle-LUT exists only because pre-AVX512 x86 lacks one — prefer the native op. **Measured on a spec-driven A/B (WojciechMula/sse-popcount `popcnt_SSE_lookup`, Windows ARM64 clang-cl, 1 MiB, warm paired back-to-back, identical work): native `vcntq_u8` ~0.42 s vs faithful vqtbl1q-LUT ~0.48 s — ~12% faster**, both count-identical to scalar. (An earlier hand-written micro-bench reported ~2.4×; the fair spec-driven, identical-workload A/B shows ~12% — the LUT path is also efficient and the 1 MiB loop is partly memory-bound. Direction holds: use `vcntq_u8`.) |
| 64-bit multiply-high built from four `_mm_mul_epu32` (32×32→64) + shuffles + carry → four `vmull_u32` + carry | `__umulh` per lane (ARM64 `UMULH`) | ARM64 has a HARDWARE 64×64→high-64 multiply (`UMULH`); SSE2 has none, so x86 *must* synthesize mulhi from four 32-bit partials — transliterating those four `vmull_u32` reproduces work one `UMULH` does. Extract lanes, `__umulh` each, recombine. **Measured (ridiculousfish/libdivide `libdivide_mullhi_u64_vec128`, Windows ARM64 clang-cl, 560M divides: faithful 4×`vmull_u32` emulation 6.05 s / CPU 5819 ms vs per-lane `__umulh` 4.07 s / CPU 3901 ms — ~1.5× faster**, both verified 800K/0 vs libdivide's scalar oracle and doing identical work. NB: this is a 2-lane u64 kernel, so scalar-per-lane wins; for wider elementwise u32 mulhi `vmull_u32` on gathered lanes is still the right vector op. |

Measured on a real port (intel/soft-crc TCP/IP one's-complement checksum, Windows
ARM64 clang): the native path cut the kernel from **0.17 → 0.07 cycles/byte, ~56%**,
bit-exact with the scalar reference across sizes 1..300.

**Profiler signature (how §8.5 surfaces this):** the kernel is a top self-time leaf
even though the module already contains NEON; the hot frames trace to the generic
shim's `vqtbl1q`/`vbic`/`vpaddq` rather than to a dedicated `vrev*`/`vpadal*`.

**Validation**
- A byteswap-then-accumulate / checksum kernel uses `vrev16q_u8`/`vrev32q_u8` +
  `vpadalq_u16`/`vpadalq_u8`, not `vqtbl1q_u8`-based shuffle emulation.
- No `_mm_hadd_*`-equivalent reduction inside the hot loop; a single `vaddvq_*`
  after the loop (see §6).
- The generic SSE→NEON shim remains only as the correctness fallback / for
  intrinsics without a dedicated NEON op — hot kernels get a native path.

---

## Generalizing Project-Wrapper Idioms to Portable NEON

Real codebases often wrap NEON in project-local macros (alignment-hint loads,
capability-dispatch macros, weight tables). Those macro *names* are not portable —
using them outside their project is an undefined-symbol build error. But each is
an instance of a **general, portable pattern**. When porting, translate to the
portable form below; keep the project's own macro only inside that project. The
zlib-ng spellings (`_ex`, `ALIGN_DIFF`, `OPTIMAL_CMP`, `tap_table`) are cited as
concrete examples, not as APIs to reuse.

### 10. Aligned Wide Load/Store After an Alignment Preamble

A hot streaming loop should use wide struct loads/stores (`vld1q_*_x4` /
`vst1q_*_x4`, 64 B/iter — §1) *after* the pointer has been aligned (§4). Some
projects express the "the pointer is aligned to N" fact with an alignment-hint
wrapper (e.g. zlib-ng's `vld1q_u8_x4_ex(buf, 256)`, hint in **bits**, so
256 = 32 B). The portable equivalent is the plain struct intrinsic — the hint
only helps on cores that honour it and only after §4 has *made* the pointer
aligned:

```c
// Portable: standard wide struct load (use after the §4 alignment preamble)
uint8x16x4_t d0_d3 = vld1q_u8_x4(buf);
vst1q_u8_x4(dst, d0_d3);

// Project-local ALTERNATIVE (zlib-ng): an alignment-hint wrapper — same effect,
// non-portable name. Only valid when buf is actually 32-byte aligned:
//   uint8x16x4_t d0_d3 = vld1q_u8_x4_ex(buf, 256);
```

**Validation**
- Hot loop uses `vld1q_*_x4` / `vst1q_*_x4` (or a project wrapper over them), and
  a §4 preamble has aligned the pointer before any aligned/hinted access.
- No `*_ex`-style alignment-hint wrapper appears outside the project that defines
  it; ports use the plain `vld1q_*_x4` form (or explicit alignment).

### 11. Alignment Preamble + Capability-Dispatched Copy/No-Copy

Two portable techniques often hide behind project macros:

1. **Alignment preamble** — compute the bytes to the next N-byte boundary with
   plain pointer math and scalar-process them first (this is §4). Projects may
   wrap the count in a macro (e.g. zlib-ng `ALIGN_DIFF(src, 32)`); the portable
   form is explicit:

   ```c
   size_t align_diff = (size_t)((-(uintptr_t)src) & (32 - 1));   // portable
   if (align_diff > len) align_diff = len;
   if (align_diff) { scalar_process(src, align_diff); src += align_diff; len -= align_diff; }
   ```

2. **Capability dispatch** — pick a code path by a runtime/compile-time hardware
   capability. Projects may gate on an internal macro (e.g. zlib-ng
   `#if OPTIMAL_CMP >= 32`); the portable form is a documented feature check
   (`IsProcessorFeaturePresent` on Windows, `getauxval`/`__ARM_FEATURE_*` on
   Linux), with **both** branches preserved:

   ```c
   if (have_wide_path) return impl_copy(state, dst, src, len);   // copy variant
   else { uint32_t r = impl_no_copy(state, src, len); memcpy(dst, src, len); return r; }
   ```

**Validation**
- Alignment preamble uses `(-(uintptr_t)src) & (align-1)` (or a project macro
  over exactly that), and `len` is clamped before the SIMD loop.
- Capability dispatch keeps both the wide and fallback branches; the gate is a
  documented feature check, not an undefined project macro, in a portable port.

### 12. Deferred Multiply with a Preloaded Coefficient/Weight Table

The deferred-multiply pattern (§2) generalizes to *any* fixed weight/coefficient
table: load the table **once** outside the loop, accumulate raw sums in-loop with
cheap widening adds, then apply the weights after the loop with `vmlal_u16` /
`vmlal_high_u16`. Projects may name the table (e.g. zlib-ng adler32's
`tap_table`); the pattern and the intrinsics are portable — only the table's
*contents* are workload-specific:

```c
uint16x8x4_t taps = vld1q_u16_x4(weight_table);            // load once (portable)
// ... in loop: widening adds into s2_* accumulators (§2) ...
acc   = vmlal_high_u16(acc,   taps.val[0], s2_0);          // apply weights after loop
acc_0 = vmlal_u16     (acc_0, vget_low_u16(taps.val[0]), vget_low_u16(s2_0));
```

**Validation**
- The weight/coefficient table is loaded once before the loop (`vld1q_*` /
  `vld1q_*_x4`), not rebuilt per iteration.
- Weights are applied with a single post-loop `vmlal`/`vmlal_high` pass (§2); the
  table's layout is treated as workload-specific data, not a portable API.

### 13. Reciprocal / Reciprocal-Sqrt: Estimate+NR vs Full-Precision — Decide by Bottleneck

`_mm_rcp_ps` / `_mm_rsqrt_ps` (12-bit estimates) have NEON estimate ops
(`vrecpeq_f32` / `vrsqrteq_f32`) with fused NR helpers (`vrecpsq_f32` /
`vrsqrtsq_f32`, each computing the NR multiplier in one op). The instinct to
*always* reach for the estimate+Newton-Raphson path on NEON is **wrong**; whether
it wins depends on whether the reciprocal/rsqrt is the loop's bottleneck. NEON
also has full-precision `vdivq_f32` and `vsqrtq_f32` — these are single
instructions but high-latency and poorly pipelined.

**The rule (two measured datapoints, opposite regimes):**

| Regime | Faster choice | Why |
|---|---|---|
| Reciprocal/rsqrt is **NOT** the bottleneck (surrounded by other FP work that hides its latency) | **Full-precision** `vdivq_f32` / `vsqrtq_f32`+`vdivq_f32` | One high-latency op overlaps with neighboring work; the 4-op estimate+NR chain just adds µops. Also full precision, no accuracy loss. |
| Reciprocal/rsqrt **IS** the bottleneck (dominates the loop; back-to-back, little else to overlap) | **Estimate+NR** `vrsqrteq_f32`+`vrsqrtsq_f32` / `vrecpeq_f32`+`vrecpsq_f32` | The estimate+NR ops (~3-4 cyc, well pipelined) out-*throughput* one non-pipelined `vsqrtq`/`vdivq` (~10+ cyc) when this op is what the loop is waiting on. |

**Measured evidence (Windows ARM64, clang-cl, native):**
- *Divide NOT the bottleneck* — romeric/fastapprox `vfastlog2` (one divide amid
  bit-twiddling): faithful `vdivq_f32` **~1.3× FASTER** than `vrecpeq_f32`+2 NR,
  and full precision.
- *Rsqrt IS the bottleneck* — CUDA-Handbook N-body force kernel (one
  reciprocal-sqrt per interaction, back-to-back over N² pairs): `vrsqrteq_f32`+1 NR
  **~11% FASTER** than `vdivq_f32(1, vsqrtq_f32(x))` (3.18 s vs 3.57 s,
  back-to-back alternating wall-clock; both profiled at 99.5-99.7% self-time in
  the inlined kernel, no libm `sqrtf`, no dispatch fallback).

**Profiler signature (how §8.5 surfaces this):** the reciprocal/rsqrt kernel is a
top self-time leaf doing genuine vector FP work (no libm `sqrtf`/`__divsf3` call,
no scalar fallback). To *decide the strategy*, compare the two builds
back-to-back and alternating (system load drifts between separately-collected ETLs
— do not compare CPU-ms from ETLs minutes apart; use paired wall-clock, use the
profiler only to confirm the leaf is genuine kernel work).

**Validation**
- The chosen path matches the regime: estimate+NR only where the reciprocal/rsqrt
  is the measured bottleneck; full-precision `vdivq`/`vsqrtq` otherwise.
- NR step count matches the source's precision target (SSE `rcp_sqrt_nr_ps` = 1 NR
  ≈ 24-bit; do not silently drop or add NR steps).
- The A-vs-B decision is backed by a paired back-to-back measurement, not a single
  ETL magnitude.

### 14. Delete x86 Workarounds for Instructions ARM64 Actually Has

A surprising amount of SSE/AVX code is not *algorithm*, it is **compensation for a
missing x86 primitive**. Ported literally, that compensation survives into the
ARM64 kernel as pure overhead — and it drags its correctness hazards (bias terms,
padding accounting, extra accumulators) along with it. Recognise the workaround
and delete it, keeping only what the algorithm actually needs.

Recurring cases, and what ARM64 offers instead:

| x86 has no… | so SSE/AVX code does this | ARM64 instead |
|---|---|---|
| signed 8-bit multiply (no `_mm_mullo_epi8`) | bias operands into unsigned (`x ^ 0x08`), widen to 16-bit, `madd`, then subtract correction sums (`Σ(a) `, `Σ(b)`) and add a `k·n` term back | `vmull_s8` / `vmlal_s8` directly on sign-extended bytes; the whole bias + correction + `k·n` epilogue disappears |
| 8-bit shift (`psrlb` does not exist) | 16-bit shift plus an `& 0x0F` mask fixup | `vshrq_n_u8` / `vshlq_n_s8` |
| per-lane variable shift pre-AVX2 | multiply by a power-of-two table | `vshlq_s32`/`vshlq_u8` with a vector shift count (native) |
| horizontal reduction | log₂-step `shuffle`+`add` ladder | `vaddvq_*` / `vaddlvq_*` (one op) |
| population count | `pshufb` nibble-LUT (see pattern 9) | `vcntq_u8` |
| unsigned compare on some widths | XOR with a sign-flip constant first | `vcgtq_u8`/`vcgeq_u32` (native unsigned compares) |

**Correctness rule that makes deletion safe.** Only delete a compensation step
when both forms are *exact* evaluations of the same integer/real expression — then
the results are bit-identical by construction, and the tail/padding accounting the
workaround required (e.g. inflating `n` so a `+k·n` term cancels zero padding)
also becomes unnecessary. Verified on ashvardanian/SimSIMD's int4 dot product,
whose entire `(a-8)(b-8)` expansion — nibble bias, four `_mm_sad_epu8` correction
sums, and the `-8(Σc+Σd)+64n` epilogue — exists solely because SSE lacks a signed
8-bit multiply; the NEON port sign-extends nibbles with `vshlq_n_s8`/`vshrq_n_s8`
and multiplies with `vmull_s8`, dropping all of it, and is exact against the scalar
definition over 4812 cases including the n=0, odd-n and all-`-8` extremes.

**Do not** delete a step you have merely *decided* is redundant: if the two forms
differ in rounding, saturation, or overflow behaviour (float reassociation,
saturating narrows, `mulhrs`-style rounding multiplies), the "workaround" is part
of the specified result and must be kept.

### 15. SoA Byte-Transpose / De-interleave: Use `vldN`/`vstN`, Not the x86 Unpack Tree

x86 has no de-interleaving load. So every SSE/AVX kernel that splits an
array-of-structures into planes — byte-plane shuffle filters (compressors),
RGB→R/G/B planar splits, complex→re/im, any `dest[p*n + e] = src[e*P + p]` — builds
the transpose out of an **unpack/shuffle tree**: `_mm_unpacklo_epi8` /
`_mm256_unpacklo_epi8/16/32/64` + `_mm256_shuffle_epi32`, typically ending in a
cross-lane repair permute (see `arm64-limitations` → Cross-128-bit-Lane Operations).

ARM64 has the instruction the tree was emulating. `vldNq`/`vstNq` de-interleave and
re-interleave N-way in one operation:

```c
// AoS -> SoA, stride 4 (32 elements = 128 bytes per iteration)
uint8x16x4_t p = vld4q_u8(src);        // p.val[k][n] == src[4*n + k]  — IS the transpose
vst1q_u8(dest + 0*n, p.val[0]);
vst1q_u8(dest + 1*n, p.val[1]);
vst1q_u8(dest + 2*n, p.val[2]);
vst1q_u8(dest + 3*n, p.val[3]);
// SoA -> AoS is the mirror: vst4q_u8(dest, plane_struct)
```

Stride 2/3/4 all exist (`vld2q`/`vld3q`/`vld4q`, and the `_u16`/`_u32` forms for
wider elements), so match N to the element size in bytes.

**Why it matters.** A literal application of "no 256-bit registers → split into two
128-bit ops" plus "`_mm256_loadu_si256` → two `vld1q_u8`" reproduces the x86 unpack
tree faithfully — i.e. it faithfully preserves a **workaround for an instruction
ARM64 has** (this is pattern 14's shape applied to data movement). Measured on
c-blosc2's `shuffle4_avx2` (Windows ARM64, byte-identical output on both sides,
paired alternating rounds with cooldowns): the `vld4q_u8` form ran **~1.3–1.8x
faster on a memory-resident 4 MiB buffer and ~2.0–2.5x faster cache-resident
(32 KiB)**, winning every paired round on both MSVC `cl` and `clang-cl`. Report the
range, not one number: the two compilers disagreed on the streaming magnitude
(1.78x vs 1.30x) because the `vld4q` form is already near the machine's streaming
bandwidth limit. Disassembly of the real objects showed the mechanism: ~60
instructions per 16 elements for the tree (16 `zip1`, 8 `ext`, 4 `uzp1`, 4 `uzp2`,
4 `zip2`; clang even lowered part of it to 8 `tbl` + 8 `dup`) versus ~40 per 32
elements for `vld4` — roughly 3x the instructions per element.

**Correctness note that comes free.** Because `vldN` never creates x86's in-lane
mis-ordering, the AVX2 kernel's trailing `_mm256_permutevar8x32_epi32` has nothing
to repair and **must be dropped, not emulated** — emulating it re-scrambles correct
data (silent format corruption, not a crash). Gate the port on a byte-exact
comparison against the x86/scalar reference, plus a negative control that swaps two
planes so you have seen the check reject a wrong layout.

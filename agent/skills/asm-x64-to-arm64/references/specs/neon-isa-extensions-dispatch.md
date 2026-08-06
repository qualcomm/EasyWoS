# NEON ISA Extensions (DotProd / i8mm) + Runtime CPU Dispatch

The baseline patterns in [[neon-asm-performance]] tune a **single** `armv8-a`
kernel. This spec is the next tier: when the target CPU has the **DotProd**
(`armv8.2-a+dotprod`, `udot`/`sdot`) or **i8mm** (`armv8.6-a`, `usmmla`/`usdot`)
extensions, a *separate* kernel using those instructions can be roughly **twice**
as fast on MAC-heavy work — anything dominated by sum-of-products or
sum-of-absolute-differences over 8-bit data (block-matching / similarity metrics,
sum-of-squared-differences, FIR/convolution, integer GEMM, dot products).
Reaching that speedup is not a single-kernel edit — it requires **three pieces
together**: (1) the extension kernel, (2) CPU feature detection, (3) a runtime
dispatch that installs the best available implementation. Missing any one means
the extension code is either never built, never selected, or crashes on CPUs
that lack the feature.

> **Scope / cost warning.** This goes *beyond the `armv8-a` baseline*. If the
> project's contract is "baseline NEON only", DO NOT introduce these — an
> `udot` on a non-DotProd core is an illegal instruction (SIGILL), so the
> extension path is only safe behind runtime detection. Adopt this tier only
> when (a) the baseline kernels are already correct and wired, and (b) the
> deployment target population includes DotProd/i8mm CPUs (e.g. Windows-on-ARM
> Snapdragon, Apple M-series, AWS Graviton3+, recent Android).

---

## 1. The three required pieces

### Piece A — the extension kernel (isolated translation unit)
The `udot`/`usmmla` kernels must be compiled with the extension enabled
(`-march=armv8.2-a+dotprod` / `+i8mm`) in a **separate** object from the baseline
code, so the baseline object stays legal on non-DotProd cores. Never sprinkle
`udot` into a file compiled at plain `armv8-a`.

### Piece B — CPU feature detection (per-OS)
Detection is an OS query (no user-space CPUID on arm64). The three real paths —
these APIs are generic, independent of any project:

```c
// Windows — IsProcessorFeaturePresent
#if defined(PF_ARM_V82_DP_INSTRUCTIONS_AVAILABLE)   // SDK 20348+ (Win11/Server2022)
    if (IsProcessorFeaturePresent(PF_ARM_V82_DP_INSTRUCTIONS_AVAILABLE))
        have_dotprod = 1;
#endif
#if defined(PF_ARM_SVE_I8MM_INSTRUCTIONS_AVAILABLE) // SDK 26100+
    // No dedicated Neon-I8MM PF_* flag exists; SVE_I8MM implies Neon I8MM.
    if (IsProcessorFeaturePresent(PF_ARM_SVE_I8MM_INSTRUCTIONS_AVAILABLE))
        have_i8mm = 1;
#endif

// Linux/Android — getauxval(AT_HWCAP / AT_HWCAP2)
if (getauxval(AT_HWCAP)  & HWCAP_ASIMDDP) have_dotprod = 1;
if (getauxval(AT_HWCAP2) & HWCAP2_I8MM)   have_i8mm    = 1;

// Apple — sysctlbyname
// "hw.optional.arm.FEAT_DotProd", "hw.optional.arm.FEAT_I8MM"
```

Gate each `#if` on both the SDK-macro guard **and** a compile-time
`HAVE_DOTPROD`/`HAVE_I8MM` (or equivalent) so old SDKs still build. Cache the
result in a capability mask; do not query per call.

### Piece C — runtime dispatch (tiered, later tier overrides earlier)
Install the baseline implementation first, then let each available extension
**overwrite** the entries it improves. The generic shape — a capability mask
selecting which implementation fills a function-pointer table (or vtable /
primitive struct):

```c
void setup_kernels(kernel_table *t, uint32_t caps)
{
    if (caps & CAP_NEON)          setup_neon(t);        // baseline: fills all slots
    if (caps & CAP_NEON_DOTPROD)  setup_dotprod(t);     // overrides the MAC/SAD slots
    if (caps & CAP_NEON_I8MM)     setup_i8mm(t);         // overrides the filter slots
    // ... further tiers (SVE/SVE2) if present ...
}
```

The order matters: each higher tier reassigns only the slots it beats, leaving
the rest at baseline. A setup routine that **ignores** the capability mask (e.g.
`(void)caps;`) can never select any extension tier — that is the single biggest
structural blocker in a baseline-only port. (This dispatch mirrors how x86 ports
already select SSE4/AVX2/AVX-512 at runtime — same pattern, arm64 capability
bits.)

**Feature dependency collapsing:** i8mm implies DotProd; SVE implies both; SVE2
implies SVE. Detection should set the implied bits too, so a `caps &
CAP_NEON_DOTPROD` test still passes on an i8mm core.

---

## 2. The extension kernels — instruction recipes

### Sum-of-absolute-differences via `udot` (DotProd)
`|a−b|` then dot with an all-ones vector sums 16 bytes into 4×u32 in **two**
instructions, landing directly in a u32 accumulator (no u16→u32 widening chain):

```gas
    movi    v1.16b, #1                  // ones, set up once outside the loop
    ...
    uabd    v4.16b, v2.16b, v3.16b      // |a-b|
    udot    v0.4s,  v4.16b, v1.16b      // Σ over 16 lanes → 4×u32, one insn
    ...
    addv    s0, v0.4s                   // final reduce (once, after the loop)
```
Baseline needs 3 insns/16B (`uabd`+`uaddlp`+`uadalp`) plus a u16→u32 fold; the
DotProd form is 2 insns straight to u32.

### Sum-of-squared-differences via `udot(x,x)` (DotProd)
Dotting the abs-diff with **itself** squares and accumulates in one instruction:

```gas
    uabd    v1.16b, v16.16b, v17.16b
    udot    v0.4s,  v1.16b, v1.16b      // Σ v1[i]² → 4×u32, one insn
```
Baseline needs 5 insns (`uabd`+`umull`+`umull2`+`uadalp`+`uadalp`). Often the
biggest single-kernel win in an 8-bit metric family.

### FIR / convolution via `udot`/`usmmla`
- **DotProd:** rearrange the sliding window (via a `tbl` permute table) into
  dot-product layout, then 2× `udot`/`sdot` (or `vdotq_lane`) cover an 8-tap
  half-MAC. For signed 8-bit coefficients, bias u8 samples by −128 and compensate
  with a constant `coeff_sum*128` term.
- **i8mm:** one `usmmla` does an 8×2 · 2×8 matrix multiply = a full 8-tap MAC.
  Pack taps into an 8×2 matrix; for a coefficient containing −1, add that tap
  separately (`usubw`) to avoid int8 overflow. More abstract than `udot`,
  higher verification cost — do DotProd first, i8mm as an optional later tier.

### Intrinsics side
If the extension kernel is written in C intrinsics rather than hand asm, the
equivalents are `vdotq_u32`/`vdotq_lane_s32` (DotProd) and `vusmmlaq_s32`/
`vusdotq_lane_s32` (i8mm), from `<arm_neon.h>` under
`__ARM_FEATURE_DOTPROD`/`__ARM_FEATURE_MATMUL_INT8`. See the intrinsics-side
`sse-avx-to-neon` skill for the x86 VNNI (`_mm*_dpbusd_epi32`) → `vdot` mapping.

---

## 3. Correctness & safety guard rails

- **SIGILL is the failure mode, not wrong numbers.** An extension instruction on
  a CPU without the feature is undefined/illegal. The *only* thing that makes it
  safe is Piece B+C actually gating it. Test on a non-DotProd core (or an
  emulator with the feature masked) that the baseline path still runs.
- **The extension kernel must be numerically identical to the baseline**, not
  just "close". Validate it against the same reference/oracle with the same
  boundary vectors (all-min/all-max) the baseline used, and run a negative
  control (feed a known-wrong result, confirm the harness reports failure) before
  trusting a pass.
- **Don't let detection over-claim.** If the OS lacks a specific `PF_*` macro
  (old SDK), the `#if defined(...)` must compile it out, leaving the capability
  bit unset — a missing feature must fail *closed* (baseline), never assumed
  present.

---

## 4. Adoption decision

| Precondition | Required before adopting this tier |
|---|---|
| Baseline NEON kernels correct + wired | Yes — extensions override baseline slots; baseline must exist first |
| Dispatch honours the capability mask | Yes — a `(void)caps;` stub can never select an extension tier |
| Target population has DotProd/i8mm CPUs | Yes — otherwise the added complexity buys nothing |
| Per-OS detection wired (Win/Linux/Apple) | Yes — without it the path is either dead or unsafe |

If all four hold, the payoff is large (SAD/SSD ~2×, FIR ~2×). If the project is
locked to baseline `armv8-a`, record this as "future work: DotProd is the first
high-value tier once the ISA baseline is raised" and stop — do not smuggle
`udot` into a baseline object.

## See Also

- [[neon-asm-performance]] — the baseline (`armv8-a`) performance patterns that
  must be correct and wired *before* this extension tier is worth adding.
- [[simd-sse-to-neon]] — SIMD mnemonic mappings and correctness pitfalls.
- `sse-avx-to-neon` skill — intrinsics-side DotProd/i8mm and x86 VNNI→vdot mapping.

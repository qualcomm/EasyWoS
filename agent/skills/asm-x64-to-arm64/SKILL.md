---
name: asm-x64-to-arm64
description: Convert x64 assembly to AArch64 arm64 — both inline asm (asm volatile / __asm__) and standalone MASM .asm files (PROC/ENDP, equ, macro/endm) translated to GAS .S form. Use when porting x64-specific asm to arm64, adding arm64 support alongside an existing x64 path, translating an entire MASM hot-loop file, or auditing code for missing arm64 coverage.
author: Hao Zeng
---

## Two scenarios this skill covers

1. **Inline asm in C/C++** — `asm volatile (...)` / `__asm__ (...)` blocks gated
   by `#ifdef __x86_64__`. Constraints, clobbers, and operand templates change;
   the surrounding C does not.
2. **Standalone .asm files (MASM x64 → GAS arm64 .S)** — entire files of
   `OPTION PROLOGUE:NONE` / `MY_PROC name, n` / `mov rax, [rsi]` style code,
   plus their macro headers. The dialect changes wholesale; translate the
   directive layer first, then the body.

The instruction-level mappings (registers, ABI, EFLAGS↔NZCV, atomics, SIMD,
memory model) apply to **both** scenarios identically — only the *syntactic
container* differs.

## Critical pre-translation check

Before applying any rules below, identify:

1. **Source x64 ABI variant** — System V AMD64 (Linux/macOS) or Windows x64.
   They differ in argument register order, callee-saved set, and shadow space.
   See [[register-and-abi]].
2. **Target toolchain** — clang integrated assembler (recommended; same `.S`
   works on Linux/macOS/Windows-on-ARM64) or Microsoft `armasm64.exe` (which
   does *not* consume GAS syntax). See [[standalone-asm-dialect]].
3. **Concurrency requirements** — any plain `mov` to/from memory that survived
   under x64 TSO must be reviewed for required ordering on arm64.
   See [[memory-model-and-atomics]].

## Spec dimensions

Detailed translation rules are organized by topic in `references/specs/`. Each
`.md` is paired with a structured `.yaml` for tooling.

| Dimension | Covers |
|---|---|
| [[inline-asm-constraints]] | GCC `asm volatile` operand constraints, `%w`/`%x` modifiers, clobber list, `m` operand restrictions, condition-code outputs |
| [[standalone-asm-dialect]] | MASM .asm → GAS .S directives (PROC/ENDP, equ, macro/endm, ptr keyword, includes), Apple `_name` symbol prefix, p2_ macro idiom, toolchain selection |
| [[register-and-abi]] | x64 ABI variant identification, AAPCS64 argument/callee-saved/scratch sets, special-purpose registers (XR, IP0/IP1, FP, LR, x18), TLS access, stack alignment, red zone, return-address handling |
| [[flags-and-conditions]] | S-suffix discipline, EFLAGS bits with no NZCV equivalent (AF/DF/PF), inverted carry polarity after cmp, conditional branch mnemonic mapping, CMOV→CSEL/CSET, CSDB speculation barrier |
| [[memory-addressing]] | Plain/offset/index/scaled/combined forms, RIP-relative addressing, arm64-only pre/post-indexed and load-pair forms, PUSH/POP→STP/LDP |
| [[memory-model-and-atomics]] | TSO→weak ordering, ldar/stlr single-access acquire/release, mfence/lfence/sfence→dmb, lock cmpxchg→casal/LL-SC, lock and→ldclral with complemented mask |
| [[bit-bulk-special-ops]] | bsr/bsf/popcnt/lzcnt/tzcnt, bit-test→tbz/tbnz, shrd/shld→extr, bswap→rev, REP/string→memcpy or unrolled loop, cache management, prefetch, rdtsc→cntvct_el0, pause→yield, cpuid→OS API |
| [[simd-sse-to-neon]] | XMM/YMM/ZMM→V registers, lane suffixes (.16b/.8h/.4s/.2d), SIMD load/store, integer arithmetic, bitwise (PANDN operand swap), shifts, compares, shuffles (palignr→ext), no-direct-equivalent ops (PMOVMSKB, AES-NI), inline-asm "=w" constraint, **plus the computational-correctness pitfalls** (stale lanes, butterfly overflow, saturate-vs-wrap, separable-transform pass/transpose order) |
| [[neon-asm-performance]] | **Performance** (not correctness) of hand-written NEON asm compute kernels — the four anti-patterns that make a *correct* port run ~2× too slow: per-output `addv` horizontal reduction, per-multiply `mov`+`dup` constant materialization, over-widening the accumulator (8-bit kernels not staying `.8h` through the inner loop), full-matrix multiply where a partial butterfly belongs. Baseline armv8-a; benchmark-against-reference discipline |
| [[neon-isa-extensions-dispatch]] | **Beyond baseline**: DotProd (`udot`/`sdot`) and i8mm (`usmmla`) extension kernels (SAD/SSD/FIR ~2× faster) + the runtime CPU-detection & tiered dispatch that make them *safe* (an extension insn on a CPU without the feature is SIGILL). Per-OS detection (Win `IsProcessorFeaturePresent` / Linux `getauxval` / Apple `sysctl`); a capability-mask-honoring dispatch that installs baseline then overrides slots per tier. Adopt only after baseline is correct+wired AND the target population has these CPUs |

## Worked example reference

- [[lzma-dec-port]] — 7-zip's `Asm/x86/LzmaDecOpt.asm` (1500-line MASM x64
  hot loop) ported to `Asm/arm64/LzmaDecOpt.S` GAS arm64. Demonstrates the
  macro-shim idiom end-to-end, register-pressure annotations, PSHIFT-style
  data-width abstraction, calling-convention contract with the surrounding C,
  and Windows-on-ARM64 toolchain selection.

## Preprocessor guards

Wrap architecture-specific blocks with standard guards. Split Apple vs. Linux
arm64 only when the instruction actually differs (e.g. `tpidrro_el0` vs
`tpidr_el0`):

```c
#if defined(__x86_64__) || defined(__i386__)
    /* x64 path */
#elif defined(__aarch64__) && defined(__APPLE__)
    /* Apple arm64 */
#elif defined(__aarch64__)
    /* Linux / other arm64 */
#else
    /* fallback */
#endif
```

## Task

First identify which scenario applies.

**Scenario A — inline asm:** the target is `asm volatile` / `__asm__` blocks
inside C/C++.

1. Read the target code.
2. Identify every block that is x64-specific (x64 instructions, named register
   constraints, or `__x86_64__`/`__i386__` guards).
3. For each block, determine the **intent** first (timing? CPU ID? atomic? SIMD?),
   then apply the correct mapping from the relevant spec — do not mechanically
   swap mnemonics.
4. Rewrite operand constraints and clobbers per [[inline-asm-constraints]].
5. Wrap both variants in appropriate preprocessor guards.
6. Add a one-line comment only when arm64 semantics differ non-obviously from
   x64 (e.g. added `dmb`, changed zero-input behavior, implicit vs explicit
   register).
7. Do not change non-asm logic. Do not introduce unnecessary abstractions.
8. Show the converted code and explain non-obvious translation decisions in
   1–2 sentences.

**Scenario B — standalone .asm file:** the target is a full MASM x64 file (and
typically a paired macro header).

1. Translate the **macro header** first per [[standalone-asm-dialect]]. It
   defines the vocabulary the body uses; without it the body translation is
   meaningless.
2. Replace dialect directives (`.code` → `.text`, `PROC`/`ENDP` → `.global` +
   label, `equ` → `.equ`, `macro`/`endm` → `.macro`/`.endm`).
3. Translate the procedure prologue/epilogue once and reuse: AAPCS64 typically
   needs `stp x29, x30, [sp, #-16]!` on entry and `ldp` + `ret` on exit. See
   [[register-and-abi]].
4. If the file is a long hot loop, consider the macro-shim idiom (see
   [[lzma-dec-port]]) before line-by-line translation.
5. Translate the body. For each x86 instruction: choose 2-op or 3-op form,
   decide whether the S-suffix flag-setting variant is needed
   ([[flags-and-conditions]]), rewrite memory addressing
   ([[memory-addressing]]), translate `jcc` to `b.<cond>` watching the
   inverted carry semantics.
6. Add `#ifdef __APPLE__` switches around every `.globl` for Mach-O underscore
   prefix.
7. Verify the symbol still satisfies any link-time version contract with
   surrounding C (function name suffix `_3` etc.) and any shared struct layout
   (`offsetof()` `.equ` constants must match what the C compiler produces).
8. Wire into the build system: pick `clang -c --target=...` (cross-platform
   GAS) or `armasm64.exe` (Windows-only ARMASM dialect — last resort).
9. Test: build, link, run a functional test (e.g. compress/decompress
   round-trip), then a benchmark to confirm the asm path is actually faster
   than the C fallback. If it isn't, the port likely has redundant flag-setting
   or missed a pre/post-indexed addressing opportunity.
10. **Compute kernel (transform / filter / metric / DSP inner loop)? Re-tune the
    shape, don't transliterate — see [[neon-asm-performance]].** A numerically
    correct port that mirrored the x86 shape typically runs ~2× too slow. Before
    declaring done, check for the four anti-patterns: per-output `addv`
    horizontal reduction, `mov`+`dup` constant materialization on the MAC
    critical path, over-widening the accumulator (8-bit kernels that leave `.8h`
    too early), and full-matrix multiply where a partial butterfly belongs.
    If a prior/upstream arm64 kernel exists, confirm throughput is ≥ it.
11. **Baseline already tuned and the target CPUs have DotProd/i8mm? Consider the
    extension tier — see [[neon-isa-extensions-dispatch]].** `udot`/`sdot`
    (SAD/SSD ~2×) and `usmmla` (FIR) need three pieces together: an isolated
    `+dotprod`/`+i8mm` translation unit, per-OS feature detection, and a
    capability-mask-honoring dispatch. An extension instruction on a CPU without the
    feature is SIGILL, so it is only safe behind runtime detection — never
    smuggle `udot` into a baseline `armv8-a` object.

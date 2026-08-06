# inline-asm-neon

Porting reference for GCC/Clang-style ARM64 NEON **inline assembly**
(`__asm__ __volatile__(...)`) into MSVC-compatible NEON C intrinsics. This is a
*toolchain* port, not an x86→ARM64 port: the AArch64 instructions already exist,
but MSVC has **no ARM64 inline-asm facility** and cannot consume GCC extended asm,
so the kernel must be re-expressed with intrinsics behind a compiler guard and
proven byte-equivalent with the bundled `assets/Verification/` gtest project.

See the skill's `SKILL.md` for the full verification-first workflow. The two
sections below are the spec recipes the dispatcher extracts by name.

## arm64-neon-inline-asm-block

**What it is.** A GCC/Clang *extended* inline-asm block has four parts:

```c
__asm__ __volatile__ (
    "instr ...\n\t"          // (1) template: quoted AArch64 instruction strings
    : [name] "+r" (var)      // (2) output operands  (constraint + tied C lvalue)
    : [name] "r"  (var)      // (3) input operands
    : "memory", "cc", "v0"   // (4) clobbers: memory, condition flags, vec regs
);
```

**Why MSVC can't build it.** MSVC ARM64 rejects `__asm__`/`asm` entirely — there
is no ARM64 inline-asm keyword. The `.S` standalone form is GNU/GAS syntax, which
`armasm64.exe` also cannot consume. Both upstream forms are dead ends for `cl.exe`.

**Landing shape.** Replace the asm region with conditional compilation, keeping
the original asm intact for non-MSVC toolchains:

```c
#if defined(_MSC_VER) && (defined(_M_ARM64) || defined(_M_ARM64EC))
    /* intrinsics translation (identical to the verified kernel_intrinsics) */
#else
    __asm__ __volatile__ ( ...original... );
#endif
```

**Workflow.** Read the asm region with surrounding context → instantiate/​update
the `Verification/` project from `assets/Verification/` → put the *original asm*
in `kernel_reference.cpp` (compiled with clang-cl) and the intrinsics in
`kernel_intrinsics.cpp` → build + run the gtest (asm vs intrinsics, randomized
inputs, edge cases) → only after it passes, land the intrinsics into the main
source. Never drop operand post-increments, loop counts, or clobbers when lifting
the asm into the wrapper.

## arm64-neon-asm-mnemonic-stream

The quoted instruction stream maps mnemonic-by-semantic to NEON intrinsics.
Common crypto/GHASH mnemonics:

| AArch64 asm | NEON intrinsic | notes |
|---|---|---|
| `ld1 {v.2d}, [p]` | `vld1q_u8(p)` | 128-bit load |
| `st1 {v.2d}, [p]` | `vst1q_u8(p, v)` | 128-bit store |
| `movi v,#0x87` + `ushr v,#56` | `vreinterpretq_p64_u64(vdupq_n_u64(0x87))` | GF(2^128) reduction constant |
| `rbit v.16b, v.16b` | `vrbitq_u8(v)` | GHASH bit-order reversal |
| `eor v,a,b` | `veorq_u8(a, b)` | XOR |
| `ext v,a,b,#8` | `vextq_u8(a, b, 8)` | 64-bit lane rotate/select |
| `pmull v.1q,a.1d,b.1d` | `vmull_p64(...)` | **low** 64×64→128 carryless mul |
| `pmull2 v.1q,a.2d,b.2d` | `vmull_high_p64(a, b)` | **high** 64×64→128 carryless mul |
| `mov v.d[1], v.d[0]` | `vsetq_lane_u64(vgetq_lane_u64(...),...,1)` | lane insert |

**Critical cross-compiler pitfall — `vmull_p64` low form.** The low
64×64→128 polynomial multiply diverges by compiler:

```c
static inline uint8x16_t gf_pmull_low(poly64x2_t a, poly64x2_t b) {
#if defined(_MSC_VER) && !defined(__clang__)
    /* real MSVC arm64_neon.h: vmull_p64 takes __n64 (== poly64x1_t) */
    return vreinterpretq_u8_p128(vmull_p64(vget_low_p64(a), vget_low_p64(b)));
#else
    /* clang / clang-cl arm_neon.h: vmull_p64 takes scalar poly64_t */
    return vreinterpretq_u8_p128(vmull_p64((poly64_t)vgetq_lane_p64(a, 0),
                                           (poly64_t)vgetq_lane_p64(b, 0)));
#endif
}
```

**Guard on the HEADER, not the compiler driver.** clang-cl (the compiler used to
build the Verification project) **defines `_MSC_VER`** for MSVC compatibility but
ships **clang's `arm_neon.h`**, whose `vmull_p64` takes a scalar `poly64_t`. A bare
`#if defined(_MSC_VER)` therefore selects the `__n64` form under clang-cl and fails
to compile (`no matching function for call to 'vmull_p64'`: `poly64x1_t` → `poly64_t`).
Use `#if defined(_MSC_VER) && !defined(__clang__)` so only **real** MSVC `cl.exe`
takes the `vget_low_p64`/`__n64` branch; clang and clang-cl share the scalar form.

**PMULL target feature.** Under clang/clang-cl, `vmull_p64`/`vmull_high_p64` are
`always_inline` and require a crypto target feature, or you get
`always_inline function 'vmull_p64' requires target feature 'aes'`. Compile the
kernel TU with `-march=armv8-a+crypto` (or `+aes`). Real MSVC `cl.exe` enables NEON
crypto unconditionally on ARM64, so no flag is needed there.

- The **high** form `vmull_high_p64(poly64x2_t, poly64x2_t)` and
  `vreinterpretq_u8_p128` are common to both compilers — no split needed.
- **`poly128_t` has no name on MSVC.** Never declare a `poly128_t` variable; wrap
  every `vmull_p64`/`vmull_high_p64` result *immediately* in `vreinterpretq_u8_p128`.
- On MSVC, `<arm_neon.h>` forwards to `<arm64_neon.h>` under `_M_ARM64`; the ARM32
  `arm_neon.h` path lacks these poly intrinsics, so guard on `_M_ARM64`/`_M_ARM64EC`.

**Operand/clobber lifting.** Turn each `"+r"/"=r"/"r"` operand into an explicit
function parameter, and treat `"memory"` + post-index addressing as a signal to
preserve pointer advancement in the intrinsics.

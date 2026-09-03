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

## arm64-msvc-aes-round-codegen-traps

**What it is.** Three MSVC ARM64 intrinsics codegen behaviors that leave a
byte-correct AES/GHASH translation silently ~2x slower than the armasm64
assembly it replaces. None is visible from reading the intrinsics source —
only from disassembly (`dumpbin -disasm:nobytes`) — and all three showed up
while matching wolfSSL's hand-written ARM64 crypto assembly under MSVC.

1. **A runtime round count blocks unrolling.** `for (i = 0; i < nr - 1; i++)`
   with `nr` a function parameter (10/12/14 AES rounds) compiles to a REAL
   loop: MSVC emits ~3 scalar bookkeeping ops (`sub`/`add`/`cbnz`) for every 2
   `aese`/`aesmc` instructions, because the trip count is not known at compile
   time. AES has exactly 3 valid round counts — dispatch on them:

   ```c
   // SLOW: nr is a runtime parameter, loop cannot be unrolled
   for (i = 0; i < nr - 1; i++) { s = vaeseq_u8(s, rk[i]); s = vaesmcq_u8(s); }

   // FAST: switch to compile-time-constant round counts, each body unrolled
   switch (nr) {
     case 10: AES_ENC_BODY_10(s); break;
     case 12: AES_ENC_BODY_12(s); break;
     case 14: AES_ENC_BODY_14(s); break;
   }
   ```

   **Measured** (fixed 1-block width, isolating this change alone):
   2732 → 5913 MB/s (**2.16x**).

2. **Wide state passed as an array stays in memory.** `f(uint8x16_t s[8])`
   is a pointer parameter; MSVC keeps the 8 blocks in memory rather than
   registers even though the whole point of the 8-wide path is to keep them
   live in vector registers. Disassembly showed 42 load/stores for 63 AES
   instructions, and the "wide" path ran no faster than the 1-wide path. Fix:
   **named locals**, not an array — token-pasting macros that declare
   `s0..s7` as separate `uint8x16_t` locals:

   ```c
   #define AES_X8_DECL(s)  uint8x16_t s##0, s##1, s##2, s##3, s##4, s##5, s##6, s##7
   #define AES_ENC_R8(s, r) do { \
       s##0 = vaeseq_u8(s##0, AES_RK(r)); s##0 = vaesmcq_u8(s##0); \
       /* ... s1..s7 identically ... */ \
   } while (0)
   ```

   **Measured** (depth sweep at fixed instruction mix, 1/2/4/8 blocks):
   2503 / 3540 / 4310 / 8024 MB/s — the 8-wide path only pays off once state is
   in named locals; disassembly then showed 8 distinct `aese` destination
   registers (state really lives in registers, not memory).

3. **`WC_INLINE`/`inline` is a hint MSVC can decline.** Once a helper held
   three unrolled round bodies (10/12/14), MSVC stopped inlining it and
   emitted `bl <helper>` per block, adding a call per block to a hot loop.
   Fix: `static __forceinline` on any helper meant to disappear into the
   caller. Verify by disassembling the caller and grepping for a stray `bl`
   to the helper — do not assume a project's inline macro was honored.

**End-to-end result**, all three fixes applied and measured against wolfSSL's
own hand-written armasm64 assembly (interleaved, checksum-matched, cooled-down
per the orchestrator's thermal-throttling rule): AES-ECB went from **1.97x
slower** than the assembly to **1.012x** — effectively parity, from three
compiler-codegen fixes with zero algorithmic change.

**Verification habit that catches these.** Disassemble the candidate
(`dumpbin -disasm:nobytes` on MSVC, or the equivalent for the target
toolchain) and count the kernel's core op (`aese`/`aesmc`, or equivalent)
against `ldr`/`str`, and check how many distinct vector-register destinations
appear for that op — if it's fewer than the intended width, state is not
actually staying in registers, regardless of what the C source implies.

# SIMD Translation (SSE/AVX → NEON)

ARM64 baseline NEON is 128-bit; YMM (256-bit) and ZMM (512-bit) have no
direct equivalent. NEON registers are `v0`–`v31`, accessed with type/lane
suffixes: `v0.16b` (16 bytes), `v0.8h` (8 halfwords), `v0.4s` (4 single-words),
`v0.2d` (2 doublewords). Inline-asm operand constraint for NEON is `"=w"`,
not `"=r"`.

## SIMD Register Aliases and Width

**x64**: `xmm0`–`xmm15` (128-bit); `ymm0`–`ymm15` (256-bit); `zmm0`–`zmm31` (512-bit).
Sub-register access via `xmmN` referring to the lower 128 of `ymmN`.

**ARM64**: `v0`–`v31` (128-bit). Lane-typed views: `v0.16b`/`v0.8h`/`v0.4s`/`v0.2d`.
Scalar views: `q0` (full 128), `d0` (low 64), `s0` (low 32), `h0` (low 16),
`b0` (low 8). Q/D/S/H/B are aliases of the same physical register but used
with scalar (non-vector) instructions.

**Workaround**:
| x64 | arm64 | Width |
|---|---|---|
| `xmm0` | `v0` (`q0`) | 128-bit |
| `ymm0` | (none — split) | 256-bit |
| `zmm0` | (none — split) | 512-bit |

256-bit operations split into two 128-bit ops on `vN` and `vN+1`. 512-bit
operations split into four. SVE (when available) gives variable-width — but
SVE is not the baseline target.

**Pitfalls**:
- XMM6–XMM15 are callee-saved on Windows x64; their ARM64 counterparts V8–V15
  are also callee-saved on AAPCS64, but the obligation covers only the lower
  64 bits (D8–D15). If the function uses the full 128 bits of V8–V15, save
  and restore the full Q register.
- AVX `_mm256_zeroupper()` has no equivalent — remove entirely. There is no
  upper-half contamination issue on arm64.

**Validation**:
- All `xmm` references become `v` (or `q`) in arm64 output.
- Every `ymm` operation is split into two 128-bit `v` operations.
- V8–V15 saves use full Q-register form when upper 64 bits are written.

## SIMD Load / Store

**x64**: `movdqa` (aligned), `movdqu` (unaligned), `movaps`/`movups` (FP),
`movntdq` (non-temporal).

**ARM64**: `ldr q0, [x1]` is always alignment-safe — no separate aligned form.
`stnp q0, q1, [x1]` is the non-temporal pair store.

**Workaround**:
| x64 | arm64 | Notes |
|---|---|---|
| `movdqa xmm0, [rcx]` | `ldr q0, [x1]` | aligned 128-bit load |
| `movdqu xmm0, [rcx]` | `ldr q0, [x1]` | unaligned — same instruction |
| `movdqa [rcx], xmm0` | `str q0, [x1]` | store |
| `movaps xmm0, [rcx]` | `ldr q0, [x1]` | FP load — same |
| `movntdq [rcx], xmm0` | `stnp q0, q1, [x1]` | non-temporal *pair* store |
| `vmovdqu ymm0, [rcx]` | `ldr q0, [x1]; ldr q1, [x1, #16]` | 256-bit split |
| `movq xmm0, [rcx]` | `ldr d0, [x1]` | 64-bit load into low half |
| `movd xmm0, eax` | `fmov s0, w0` | 32-bit GP→SIMD |
| `movd eax, xmm0` | `fmov w0, s0` | 32-bit SIMD→GP |
| `movq rax, xmm0` | `fmov x0, d0` | 64-bit SIMD→GP |

**Pitfalls**:
- arm64 `ldr q0, [x1]` is unaligned-tolerant by default. The `movdqa` /
  `movdqu` distinction in the x64 source is informational only — both map
  to the same arm64 instruction.
- `stnp` requires a *pair* of registers; single non-temporal stores use
  `str q0, [...]` with no non-temporal hint (or rely on `dc cvap` / cache
  hints separately).
- **`ld1`/`st1` immediate post-index must equal the access size.** With the
  structured load/store form, the immediate post-index on a single-register
  access is fixed to the bytes transferred — `16` for one `{Vn.16b}` /
  `{Vn.8h}` / `{Vn.4s}` (a full Q reg), `8` for a `D`-form. To advance the
  pointer by an arbitrary stride (row pitch, element gap ≠ load width), use the
  **register** post-index form, not an arbitrary immediate:
  ```
  ld1  {v0.8h}, [x1], #16      ; OK    — load 16 bytes, pointer += 16
  ld1  {v0.8h}, [x1], #32      ; ERROR — immediate must equal access size (16)
  mov  x9, #32
  ld1  {v0.8h}, [x1], x9       ; OK    — load 16 bytes, pointer += 32 (skip a row)
  ```
  `ldr q` / `ldp` accept arbitrary signed immediate offsets, but the immediate
  *write-back* on `ld1`/`st1` does not. This trips up ports of row-strided
  loops (image / matrix / DSP) where the stride differs from the load width.

**Validation**:
- All SSE/AVX 128-bit loads/stores become `ldr q` / `str q`.
- 256-bit loads/stores explicitly produce two 128-bit instructions.
- GP↔SIMD scalar transfers use `fmov`, not the inline-asm `mov` mnemonic.
- Any `ld1`/`st1` with an immediate post-index uses an immediate equal to the
  access size; arbitrary strides use a register post-index (`[xN], xM`).

## SIMD Integer Arithmetic

**x64**: `paddb/w/d/q xmm0, xmm1` etc.

**ARM64**: `add v0.<lane>, v0.<lane>, v1.<lane>` where `<lane>` is `16b` /
`8h` / `4s` / `2d`.

**Workaround**:
| x64 | arm64 |
|---|---|
| `paddb xmm0, xmm1` | `add v0.16b, v0.16b, v1.16b` (16 bytes) |
| `paddw xmm0, xmm1` | `add v0.8h, v0.8h, v1.8h` (8 halfwords) |
| `paddd xmm0, xmm1` | `add v0.4s, v0.4s, v1.4s` (4 words) |
| `paddq xmm0, xmm1` | `add v0.2d, v0.2d, v1.2d` (2 doublewords) |
| `psubb` ... | `sub v0.16b, v0.16b, v1.16b` |
| `pmullw xmm0, xmm1` | `mul v0.8h, v0.8h, v1.8h` (low half) |
| `pmulld xmm0, xmm1` | `mul v0.4s, v0.4s, v1.4s` |
| `pmaddwd xmm0, xmm1` | `smull v2.4s, v0.4h, v1.4h; smlal2 v2.4s, v0.8h, v1.8h` (multiply-add chain) |
| `pabsb/w/d` | `abs v0.16b/8h/4s, v1.<>` |
| `pminsb/w/d` | `smin v0.<>, v0.<>, v1.<>` |
| `pmaxsb/w/d` | `smax v0.<>, v0.<>, v1.<>` |
| `pminub/uw/ud` | `umin v0.<>, v0.<>, v1.<>` |
| `pmaxub/uw/ud` | `umax v0.<>, v0.<>, v1.<>` |

**Pitfalls**:
- Lane suffix must match the operation width: `paddb` → `.16b`, `paddw` → `.8h`, etc. Forgetting the suffix or mismatching it changes the operation entirely.
- `pmaddwd` (multiply-and-horizontal-add) has no single-instruction NEON form; it requires `smull` + `smlal2` (or NEON pairwise `addp`) to reproduce.
- **By-element multiply restricts the element register to the LOW bank.** When
  a constant/coefficient is supplied via the by-element form `mul`/`mla`/`smull`/
  `smlal`/`sqdmulh ... , Vm.<T>[idx]`, the element source `Vm` is architecturally
  limited by element width: for `.h[]` (16-bit lanes) `Vm` **must be v0–v15**;
  for `.s[]` (32-bit lanes) `Vm` **must be v0–v31** (no restriction). Putting a
  16-bit-lane coefficient table in v16–v31 assembles to `error: invalid operand
  for instruction`. Fix: load such coefficient/basis vectors into the low bank
  (v0–v15) — and since v8–v15 are callee-saved (low 64 bits), save `d8`–`d15`
  with `stp`/`ldp` if you use them. This bites coefficient-driven kernels (DCT/
  DST basis, FIR taps, fixed-point multipliers) ported from x86, where the source
  freely used any xmm for the constant table.

**Validation**:
- All `padd*`/`psub*`/`pmul*` translate with correct lane suffix.
- `pmaddwd`-class operations use multi-instruction sequences.
- Any by-element `*.h[idx]` multiply/multiply-accumulate sources its element
  register from v0–v15 (and saves d8–d15 if v8–v15 are used).

## SIMD Bitwise

**x64**: `pand`/`por`/`pxor`/`pandn`.

**ARM64**: `and`/`orr`/`eor`/`bic` on `v0.16b` form (always 16-byte lane).
**Operand order for `pandn` reverses** in `bic`.

**Workaround**:
| x64 | arm64 |
|---|---|
| `pand xmm0, xmm1` | `and v0.16b, v0.16b, v1.16b` |
| `por xmm0, xmm1` | `orr v0.16b, v0.16b, v1.16b` |
| `pxor xmm0, xmm1` | `eor v0.16b, v0.16b, v1.16b` |
| `pandn xmm0, xmm1` | `bic v0.16b, v1.16b, v0.16b` (note operand swap: result = v1 AND NOT v0) |

**Pitfalls**:
- `pandn` semantics: `dst = (NOT dst) AND src`. arm64 `bic` semantics: `dst = src1 AND NOT src2`. The operand order swap is exact.

**Validation**:
- All `pand*`/`por*`/`pxor*` use `.16b` lane.
- `pandn` translation has operands swapped from naive 1:1 mapping.

## SIMD Shift

**x64**: `pslld/q/w xmm0, imm` (left shift), `psrld/q/w` (logical right),
`psrad/w` (arithmetic right).

**ARM64**: `shl v0.<lane>, v0.<lane>, #imm` for left; `ushr` (unsigned) /
`sshr` (signed) for right.

**Workaround**:
| x64 | arm64 |
|---|---|
| `psllw xmm0, imm` | `shl v0.8h, v0.8h, #imm` |
| `pslld xmm0, imm` | `shl v0.4s, v0.4s, #imm` |
| `psllq xmm0, imm` | `shl v0.2d, v0.2d, #imm` |
| `psrlw xmm0, imm` | `ushr v0.8h, v0.8h, #imm` |
| `psrld xmm0, imm` | `ushr v0.4s, v0.4s, #imm` |
| `psrlq xmm0, imm` | `ushr v0.2d, v0.2d, #imm` |
| `psraw xmm0, imm` | `sshr v0.8h, v0.8h, #imm` |
| `psrad xmm0, imm` | `sshr v0.4s, v0.4s, #imm` |
| `pslld xmm0, xmm1` (variable) | `ushl v0.4s, v0.4s, v1.4s` (signed shift count, negative = right) |

**Pitfalls**:
- Variable-shift `pslld xmm0, xmm1` has different semantics in NEON: arm64
  `ushl`/`sshl` interpret a negative count as a right shift, not a wrap-around.
- arm64 has no `psra` for 64-bit lanes (`psraq`); workaround is `cmp v.2d,
  #0` + `eor` chain or `sshr` on a sign-broadcast.

**Validation**:
- All immediate-count shifts have correct lane suffix and direction (`shl`/`ushr`/`sshr`).
- Variable shifts handle signed-count semantics correctly.

## SIMD Compare

**x64**: `pcmpeqb/w/d`, `pcmpgtb/w/d`. Sets each lane to 0xFF...F or 0x00...0.

**ARM64**: `cmeq` (equal), `cmgt` (signed greater-than), `cmhi` (unsigned hi).
Lane width via `.<lane>` suffix.

**Workaround**:
| x64 | arm64 |
|---|---|
| `pcmpeqb xmm0, xmm1` | `cmeq v0.16b, v0.16b, v1.16b` |
| `pcmpeqw xmm0, xmm1` | `cmeq v0.8h, v0.8h, v1.8h` |
| `pcmpeqd xmm0, xmm1` | `cmeq v0.4s, v0.4s, v1.4s` |
| `pcmpgtb xmm0, xmm1` | `cmgt v0.16b, v0.16b, v1.16b` (signed) |
| (unsigned compare) | `cmhi v0.<>, v0.<>, v1.<>` |

**Pitfalls**:
- x64 `pcmpgt*` is signed; for unsigned use NEON `cmhi` (no x64 equivalent
  exists in same single instruction — x64 typically used `pmaxub` + `pcmpeq`).

**Validation**:
- All `pcmpeq*` translate to `cmeq` with correct lane suffix.
- `pcmpgt*` translate to `cmgt` (signed); separately translated unsigned compares use `cmhi`.

## SIMD Shuffle / Permute

**x64**: `pshufb`, `pshufd`, `punpcklbw`/`hbw` etc., `palignr`.

**ARM64**: `tbl` (table lookup, byte-granular), `zip1`/`zip2`/`uzp1`/`uzp2`/
`trn1`/`trn2` (interleaving), `ext` (byte-aligned extract).

**Workaround**:
| x64 | arm64 |
|---|---|
| `pshufb xmm0, xmm1` (byte shuffle by index) | `tbl v0.16b, {v0.16b}, v1.16b` |
| `pshufd xmm0, xmm0, 0` (broadcast lane 0) | `dup v0.4s, v0.s[0]` |
| `pshufd xmm0, xmm1, imm` (general) | Expand imm into a lane-index byte vector, then `tbl` |
| `punpcklbw xmm0, xmm1` | `zip1 v0.16b, v0.16b, v1.16b` |
| `punpckhbw xmm0, xmm1` | `zip2 v0.16b, v0.16b, v1.16b` |
| `punpcklwd xmm0, xmm1` | `zip1 v0.8h, v0.8h, v1.8h` |
| `palignr xmm0, xmm1, imm` | `ext v0.16b, v1.16b, v0.16b, #imm` |
| `vpbroadcastb ymm0, [mem]` | `ld1r {v0.16b}, [x0]` |
| `vpbroadcastd ymm0, [mem]` | `ld1r {v0.4s}, [x0]` |

**Pitfalls**:
- `pshufd imm` to general patterns has no single-instruction NEON form;
  expand the immediate into a byte-index vector and use `tbl`. The
  immediate-to-vector translation is not mechanical — read the imm as a
  4-element 2-bit lane-permutation, then expand each 32-bit lane into 4
  bytes for the byte-granular `tbl` index.
- `palignr` operand order on arm64 `ext` reverses: x64 `palignr xmm0, xmm1,
  imm` extracts from `xmm1:xmm0` — arm64 `ext v0.16b, v1.16b, v0.16b, #imm`
  has the source pair in the opposite order.

**Validation**:
- `pshufb` translates to `tbl`.
- `punpcklXY`/`punpckhXY` translate to `zip1`/`zip2` with correct lane suffix.
- `palignr` translates to `ext` with operand order reversed.

## No-Direct-Equivalent SIMD Operations

| x64 | Arm64 workaround | Notes |
|---|---|---|
| `pmovmskb xmm0, xmm1` (byte mask to GP) | `umaxv b0, v1.16b` for "any nonzero" test; `addv` + masking for general | NEON has no movemask analog |
| `vmovmskps`/`vmovmskpd` | Restructure logic — usually replaceable with `cmlt` + `addp` reductions | |
| 256-bit (`ymm`) anything | Two 128-bit Q-register operations | |
| 512-bit (`zmm`) anything | Four or more 128-bit Q-register operations | |
| `_mm256_zeroupper()` | Remove entirely | No upper-half contamination |
| `vpermd` (cross-lane permute) | `tbl` with manually constructed index | |
| AES-NI (`aesenc` etc.) | NEON crypto (`aese` + `aesmc`) — different round structure | Verify `__ARM_FEATURE_CRYPTO` |
| CLMUL (`pclmulqdq`) | NEON crypto `pmull`/`pmull2` | |

**Pitfalls**:
- `pmovmskb` is the most common compatibility pain point. Many x64 SIMD
  algorithms branch on `movemask == 0xFFFF` or specific bit patterns. arm64
  needs algorithmic rework — typically replacing the bitmask test with a
  reduction (`addv` of compare result) or per-lane processing.
- AES round structure differs: x64 `aesenc` does ShiftRows + SubBytes +
  MixColumns + AddRoundKey in one; arm64 `aese` is ShiftRows + SubBytes +
  AddRoundKey, with `aesmc` (MixColumns) as a separate instruction. Round
  scheduling must be rewritten.

**Validation**:
- No `pmovmskb`/`vmovmskps` in arm64 output.
- AES sequences use paired `aese` + `aesmc` with correct round structure.

## NEON Computational Correctness Pitfalls

These are not mnemonic mappings — they are semantic traps that compile and run
but produce wrong numbers. Each recurs across image/DSP kernel ports and is only
caught by diffing numeric output against the reference (see the verification
checklist).

### Partial loads leave stale upper lanes

A narrow load (`ld1 {v0.s}[0]`, `ld1 {v0.h}[0]`, `ldr s0`/`ldr b0`) writes only
the addressed lanes; the rest of the V register keeps **stale prior contents**.
A later full-width op (`.8b`/`.16b`/`.8h`) reads those stale lanes and folds
garbage into the result. Pre-zero the register (`movi v0.8b, #0`) before the
partial load, or use a load form that zeroes the remainder.

```gas
// WRONG — bytes 4..7 of v0/v1 are stale, then squared into the sum
ld1     {v0.s}[0], [x0]          // load 4 valid bytes
ld1     {v1.s}[0], [x2]
uabd    v2.8b, v0.8b, v1.8b      // reads 8 bytes — 4..7 are garbage
umull   v3.8h, v2.8b, v2.8b

// CORRECT — zero first
movi    v0.8b, #0
movi    v1.8b, #0
ld1     {v0.s}[0], [x0]
ld1     {v1.s}[0], [x2]
```

A comment asserting "the upper lanes are 0" is not a guarantee — verify something
actually zeroed them.

### Self-`ext` on a partial-width window wraps cyclically

`ext vD, vS, vS, #N` (single-register form) is **cyclic within that register** —
byte `lane+N` past the end wraps to the register's low bytes, not the next
memory element. A "narrow" partial-width filter that builds its tap-slices by
self-`ext` on a single loaded register is only correct while
`out_cols + taps − 1 <= reg_lanes`. Once the rightmost tap of the last output
column exceeds the loaded window it silently reads wrapped data. This is
width-dependent: narrow widths whose last column stays in range are fine, so the
bug first appears at the width that just exceeds the load (e.g. width-6 with a
4-tap filter on an 8-byte load needs `src[0..8]` — byte 8 wraps to byte 0).

Fix: load the full window (e.g. 16 bytes) and `ext` *across two registers*
(`ext vD, vLo, vHi, #N`), which pulls real neighbours instead of wrapping. Audit
every self-`ext` narrow path against its widest column's tap reach.

### Pre-combined butterfly sums must fit the lane width

Any operation that **pre-combines inputs before narrowing** (butterfly
`E=a+b`/`O=a−b`, `EE`/`EO` folds, sum-of-products) must hold the intermediate in
a lane width that fits the worst-case magnitude. A 16-bit (`.8h`) lane overflows
the moment a pass consumes another pass's already-up-scaled values: e.g. an input
near int16 max (~32767) combined via `E=a+b` reaches ~2× that, **outside int16**,
and the `.8h` add wraps — corrupting only the extreme-input cases (often <1%), so
random small inputs pass and only a boundary test catches it. Widen to 32-bit
(`saddl`/`saddl2`/`ssubl`/`ssubl2` → two `.4s` halves, `sxtl` the other operand,
`mul`/`mla` on `.4s`) when the reference holds the intermediate in 32-bit int.

### But don't widen *earlier* than the magnitude requires — it halves throughput

The rule above is a *correctness floor*, not a "always widen to 32-bit" order.
Widening early is the opposite mistake: a `.8h` (16-bit) datapath processes twice
the lanes per instruction as `.4s`, so promoting to 32-bit before the running sum
can actually exceed 16-bit throws away half the throughput for nothing. The safe
window is bounded by the accumulator's worst case: an unsigned 8-bit source summed
in `.8h` lanes holds up to `65535 / 255 ≈ 257` byte-addends per lane before it can
overflow, so a kernel that accumulates a bounded number of 8-bit terms per lane
(e.g. an 8×8 block of absolute differences or Hadamard partials) is provably safe
in 16-bit and only needs to widen to `.4s` at the **cross-block reduction**, not
inside the inner loop.

Concretely, for an 8-bit metric (SAD/SATD/SSD-of-bytes and similar): keep the
inner per-block accumulation in `.8h` (`uabd`+`uadalp`, or `add`/`abs` on `.8h`),
and only `uaddlp`/`uadalp` up to `.4s` when combining blocks whose count would push
a lane past the 16-bit bound. A port that reflexively `uaddl`s every partial to
32-bit "to be safe" is correct but runs at roughly half speed.

Decide the accumulator width by the **magnitude bound**, computed from
`max_addend × addends_per_lane`, in both directions:
- If that product can exceed the narrow type → widen (the correctness rule above).
- If it provably cannot → stay narrow through the inner loop, widen only at the
  reduction boundary.

This is a performance/correctness balance; the throughput rationale and its
counterpart patterns live in [[neon-asm-performance]] (baseline) — this note is
here only because it shares the exact overflow-bound reasoning above.

> **Worked example (HEVC `dct4`, a real port).** Pass 1 of the separable 4x4 DCT
> butterflies 8-bit residuals (≤255), so `E=r0+r3` fits `.4h` and the kernel used
> `add v.4h` + by-element `smull`. Pass 2 re-runs the *same* butterfly on pass-1
> **coefficients** — for a flat max-residual block those reach `64·(255+255)+round
> ≈ 32640`, so `E=c0+c3 ≈ 65280` overflows the `.4h` lane and wraps to a negative
> value. Random mid-range inputs passed; only the all-max / alternating-sign
> boundary tests went red. The fix was to compute the *whole* butterfly in 32-bit
> from the start — `saddl/ssubl` into `.4s`, then `mul`/`mla v.4s` against a
> 32-bit basis — for **both** passes, because the per-pass cost of always-32-bit
> is negligible versus diagnosing the wrap. Lesson: when a kernel is multi-pass
> and a later pass consumes an earlier pass's up-scaled output, size the butterfly
> lane for the *latest* pass's magnitude, not the input's.

### Narrowing: wrap (truncate) vs saturate must match the reference

NEON narrowing instructions differ in overflow behaviour and this is **not**
interchangeable with the C reference:
- `sqxtn`/`sqxtun`/`uqxtn` **saturate** (clamp to the type's min/max).
- `xtn` plus a manual mask, or a plain `mov`/store of the low half, **truncates
  (wraps)** — matching a C `(int16_t)x` cast.

If the reference casts with `(int16_t)`/`(uint8_t)` (wrap) but the port uses
`sqxtn` (saturate), results diverge exactly when an intermediate exceeds the
narrow type — again only on extreme inputs. Choose the narrowing form by what the
reference does on overflow, not by which instruction is most convenient. Likewise
match the **rounding** form: `sqrshrn`/`srshr` round half-away/half-up, while
`add #round; sshr` floors — pick the one the reference's `>>` semantics imply.

### Lane-width / rounding bugs hide on random inputs

The common thread above: overflow, stale-lane, and wrap-vs-saturate bugs are
invisible on typical mid-range random data and only fire on boundary/extreme
inputs (all-min, all-max, alternating ±max). A numeric harness MUST include
boundary vectors, not just uniform random ones, or it produces a false green.

**Validation**:
- Every partial/narrow load into a register a later full-width op reads is
  preceded by a zeroing of the unloaded lanes (or uses a zero-extending load).
- No self-`ext` (single-register) builds a tap window whose widest column reads
  past the loaded lanes; wide-window cases `ext` across two registers.
- Pre-combined butterfly/fold intermediates are held in a lane width that fits
  `input_max × combine_factor`; widened to 32-bit where the reference uses int32 —
  but **not** widened earlier than that bound requires (8-bit metrics stay in
  `.8h` through the inner loop, widening to `.4s` only at the cross-block
  reduction).
- The narrowing instruction's overflow behaviour (saturate vs wrap) and rounding
  direction match the reference implementation, verified on extreme inputs.

### Separable transforms must mirror the reference's pass/transpose order

A multi-pass separable transform (DCT/IDCT/DST and similar row-then-column
kernels) that **rounds between passes** is not free to pick any
mathematically-valid axis order. Because each pass quantizes its intermediate
(`(x + round) >> shift`), doing columns-first vs rows-first — or omitting/adding a
transpose — changes which values get rounded when, producing results that differ
by ±1 from the reference on some outputs. When the contract is **bit-exact**
(the reference output must be reproduced exactly, not merely within a tolerance),
that ±1 is a failure even though the transform is mathematically "correct".

Match the reference exactly: which axis each pass transforms, every inter-pass
and final transpose, and each pass's shift/round amount (these are often
data-width-dependent, e.g. a `shift = base + bitWidth − N` formula). A common net
identity is that the reference's *two transposed writes* cancel to natural order
— so the asm needs a leading transpose and a mid transpose but **no** final one.
Verify by brute-forcing the `{start, mid, end}` transpose placements against the
reference if unsure; only one combination is bit-exact.

```
// symptom signatures (diagnostic):
//   first/DC output correct, most others wrong, large maxdiff -> output is the TRANSPOSE of correct
//   small fraction of outputs off-by-1, symmetric             -> inter-pass rounding-order/axis mismatch
//   every output over/under-shifted by a power of two         -> wrong pass shift (often a stale x86 comment)
```

Do not trust the port's own comment for the shift amount — copy it from the
reference for the target data width.

## Inline-Asm NEON Constraint

**x64**: `"=x"`, `"=Yz"` for SSE; `"=v"` for AVX.

**ARM64**: `"=w"` for any NEON/FP register output; `"+w"` for read-write.
Operand template uses `%0`/`%1` (no `%w` / `%x` width modifier — the lane
suffix in the instruction template determines the view).

**Workaround**:
```c
// arm64 NEON inline asm
uint8x16_t v;
uint8x16_t a, b;
asm ("add %0.16b, %1.16b, %2.16b" : "=w"(v) : "w"(a), "w"(b));
```

**Pitfalls**:
- Forgetting `"=w"` and using `"=r"` allocates a GP register; the NEON
  instruction will fail to assemble. See [[inline-asm-constraints]].

**Validation**:
- All inline-asm NEON outputs use `"=w"` constraint.

## See Also

- [[inline-asm-constraints]] for the `"=w"` constraint rule and width modifiers.
- [[register-and-abi]] for V8–V15 callee-saved obligations.
- [[memory-addressing]] for `ldr q` addressing-mode constraints.

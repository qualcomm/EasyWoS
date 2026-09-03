# ARM64 NEON Limitations and Workarounds

Operations that have no direct NEON equivalent to common SSE/AVX patterns,
with concrete workarounds derived from the Microsoft STL implementation.

## Table of Contents
1. [No 256-bit Registers](#no-256-bit-registers)
2. [No Horizontal 64-bit Integer Min/Max](#no-horizontal-64-bit-integer-minmax)
3. [No `_mm_movemask_epi8` Equivalent](#no-_mm_movemask_epi8-equivalent)
4. [No AVX2 Masked Loads/Stores](#no-avx2-masked-loadsstores)
5. [No `_Zeroupper` Equivalent](#no-_zeroupper-equivalent)
6. [No `__isa_enabled` Mechanism](#no-__isa_enabled-mechanism)
7. [No Gather/Scatter Instructions (Baseline)](#no-gatherscatter-instructions-baseline)
8. [No String-Compare Instructions (`PCMPxSTRx` family)](#no-string-compare-instructions-pcmpxstrx-family--substitute-the-algorithm-dont-emulate-the-instruction)
9. [Variable-Count Shifts](#variable-count-shifts)
10. [Cross-128-bit-Lane Operations](#cross-128-bit-lane-operations)
11. [The 4-byte Tail UB Trap](#the-4-byte-tail-ub-trap)

---

## No 256-bit Registers

**x64**: `__m256i` processes 32 bytes in a single register.

**ARM64**: Maximum native width is 128-bit (`uint8x16_t`). There is no 256-bit NEON
register (SVE has variable-width vectors, but that requires a runtime check and
different programming model).

**Workaround**: Use 4 × 128-bit registers per loop iteration to process 64 bytes,
matching or exceeding AVX2 throughput on modern ARM64 microarchitectures:

```cpp
// Instead of one __m256i load (32 bytes), use four uint8x16_t loads (64 bytes):
uint8x16_t _V0 = vld1q_u8(ptr +  0);
uint8x16_t _V1 = vld1q_u8(ptr + 16);
uint8x16_t _V2 = vld1q_u8(ptr + 32);
uint8x16_t _V3 = vld1q_u8(ptr + 48);
// Process all four, then advance by 64
```

This is exactly what the STL does in `__std_swap_ranges_trivially_swappable_noalias`
and `_Rotating::_Swap_3_ranges`.

---

## No Horizontal 64-bit Integer Min/Max

**x64**: `_mm_min_epi64` / `_mm_max_epi64` (SSE4.1) reduce 64-bit integer lanes.

**ARM64**: NEON has `vminvq_u8/u16/u32` and `vmaxvq_u8/u16/u32` for horizontal
reduction, but **there is no `vminvq_u64` or `vmaxvq_u64`**.

**Impact in the STL**: `min_element` / `max_element` for `int64_t` / `uint64_t` is
**not vectorized** on ARM64/ARM64EC. The scalar path is used instead.

```cpp
// In xutility — this guard prevents the 64-bit int path from being compiled:
#if defined(_M_ARM64) || defined(_M_ARM64EC)
template <class _Ty>
_INLINE_VAR constexpr bool _Is_64bit_int_on_arm64_arm64ec =
    sizeof(_Ty) == 8 && !is_floating_point_v<_Ty>;
#else
template <class _Ty>
_INLINE_VAR constexpr bool _Is_64bit_int_on_arm64_arm64ec = false;
#endif
```

**Workaround options**:
1. **Skip vectorization** (STL approach) — scalar is competitive for 64-bit int min/max
2. **Manual two-step reduction**: compare lanes with `vcgtq_u64`, use `vbslq_u64` to
   select, then extract both lanes and compare scalarly:
   ```cpp
   uint64x2_t _Cmp = vcgtq_u64(a, b);
   uint64x2_t _Min = vbslq_u64(_Cmp, b, a);  // elementwise min
   // Horizontal: extract both lanes and compare
   uint64_t _Lo = vgetq_lane_u64(_Min, 0);
   uint64_t _Hi = vgetq_lane_u64(_Min, 1);
   uint64_t _Result = _Lo < _Hi ? _Lo : _Hi;
   ```
3. **Use SVE** if `_Use_FEAT_SVE()` — SVE has `svminv` for all widths including 64-bit.

---

## No `_mm_movemask_epi8` Equivalent

**x64**: `_mm_movemask_epi8(v)` extracts the MSB of each of the 16 bytes into a
16-bit integer. This is used extensively for "find first match" patterns.

**ARM64**: No single instruction equivalent. Two approaches:

### Approach 1: `vmaxvq_u8` — sufficient for "any match?" test

```cpp
// x64:
if (_mm_movemask_epi8(cmp) != 0) { /* found */ }

// ARM64:
if (vmaxvq_u8(cmp) != 0) { /* found */ }
```

This is the approach used in the STL's `__std_find_trivial_*` implementations.

### Approach 2: `vshrn_n_u16` — for exact position finding

```cpp
// Compress 16 bytes of 0xFF/0x00 into a 64-bit bitmask (4 bits per byte):
uint8x8_t _Narrowed = vshrn_n_u16(vreinterpretq_u16_u8(cmp), 4);
uint64_t _Mask64 = vget_lane_u64(vreinterpret_u64_u8(_Narrowed), 0);
// Each matching byte contributes 0xF to its nibble
// First match position = __builtin_ctzll(_Mask64) / 4
if (_Mask64 != 0) {
    size_t _Pos = __builtin_ctzll(_Mask64) / 4;
    return _First + _Pos;
}
```

---

## No AVX2 Masked Loads/Stores

**x64**: `_mm256_maskload_epi32` / `_mm256_maskstore_epi32` allow partial vector
loads/stores controlled by a mask. Used in `_Avx2_tail_mask_32` for tail handling.

**ARM64**: No equivalent masked load/store in baseline NEON.

**Workaround**: The STL's **descending-granularity tail pattern** — instead of one
masked load, use a cascade of progressively smaller unconditional loads:

```cpp
// x64 tail (masked):
__m256i _Mask = _Avx2_tail_mask_32(remaining_bytes);
__m256i _Data = _mm256_maskload_epi32(ptr, _Mask);

// ARM64 tail (descending granularity — no masks needed):
if (remaining >= 16) { /* vld1q_u8 */ remaining -= 16; ptr += 16; }
if (remaining >= 8)  { /* vld1_u8  */ remaining -= 8;  ptr += 8;  }
if (remaining >= 4)  { /* vld1_lane_u32 */ remaining -= 4; ptr += 4; }
while (remaining > 0) { /* scalar */ --remaining; ++ptr; }
```

SVE's predicated loads (`svld1`) can replace masked loads if `_Use_FEAT_SVE()`.

---

## No `_Zeroupper` Equivalent

**x64**: After using YMM (256-bit AVX) registers, `_mm256_zeroupper()` must be called
to avoid performance penalties when transitioning back to SSE (XMM) code. The STL
uses a `_Zeroupper_on_exit` RAII guard for this.

**ARM64**: NEON registers have no "upper half" contamination issue. There is no
equivalent concept and no equivalent instruction.

**Action**: Simply **remove** `_Zeroupper_on_exit` and any `_mm256_zeroupper()` calls.
Do not add any replacement.

```cpp
// x64 — REMOVE both of these:
struct _Zeroupper_on_exit {
    ~_Zeroupper_on_exit() { _mm256_zeroupper(); }
};
// and:
_mm256_zeroupper(); // TRANSITION, DevCom-10331414
```

---

## No `__isa_enabled` Mechanism

**x64**: `extern "C" long __isa_enabled` is a vcruntime-internal bitmask that tracks
which ISA extensions are available. It can be patched in tests to simulate missing
features (useful for testing SSE4.2 fallback paths on AVX2 hardware).

**ARM64**: No equivalent mechanism exists in vcruntime as of PRs #6067/#6084.
`IsProcessorFeaturePresent` is used instead, but it cannot be patched for testing.

**Future**: A "Vulcan nerve pinch" test-only function may be added to the import lib
to simulate feature disablement on ARM64 (analogous to the old ConcRT mechanism).

**Impact on testing**: ARM64 vectorized code currently cannot be tested with features
artificially disabled. Tests must run on hardware that actually lacks the feature,
or use compile-time `#if` to select paths.

---

## No Gather/Scatter Instructions (Baseline)

**x64**: AVX2 has `_mm256_i32gather_epi32` and similar gather instructions for
non-contiguous memory access.

**ARM64**: Baseline NEON has no gather/scatter. SVE2 adds gather/scatter support.

**Workaround**: Use scalar loads into vector lanes:
```cpp
uint32x4_t _V;
_V = vsetq_lane_u32(ptr[idx[0]], _V, 0);
_V = vsetq_lane_u32(ptr[idx[1]], _V, 1);
_V = vsetq_lane_u32(ptr[idx[2]], _V, 2);
_V = vsetq_lane_u32(ptr[idx[3]], _V, 3);
```
Or use SVE gather loads if `_Use_FEAT_SVE2()`.

---

## No String-Compare Instructions (`PCMPxSTRx` family) — Substitute the ALGORITHM, don't emulate the instruction

**x64**: SSE4.2 has the string-compare instructions `_mm_cmpestrm` / `_mm_cmpestri`
/ `_mm_cmpistrm` / `_mm_cmpistri` (`PCMPESTRM`/`PCMPESTRI`/`PCMPISTRM`/`PCMPISTRI`).
In `_SIDD_CMP_EQUAL_ORDERED` mode, a **single** instruction performs an ordered
substring compare of a needle against a 16-byte data window and returns a bitmask
of candidate start offsets — the core of an SSE4.2 `strstr`.

**ARM64**: NEON has **no** string-compare instruction at all — not baseline, not
SVE2. There is nothing to map the intrinsic to.

**The trap — faithful per-window emulation is slow.** You *can* emulate
`cmpestrm` EQUAL_ORDERED by comparing the window against each needle byte at the
matching shift and AND-reducing a movemask:
```cpp
uint32_t mask = 0xFFFF;
for (size_t t = 0; t < k; t++) {                 // k = needle length
    uint8x16_t Dt = vld1q_u8(data + t);          // window shifted by t
    uint8x16_t eq = vceqq_u8(Dt, vdupq_n_u8(needle[t]));
    mask &= neon_movemask_u8(eq);                // movemask emulation (see above)
    if (!mask) break;
}
```
This is correct, but it costs **O(k) NEON ops per 16-byte window** (one `vld`+`vdup`+
`vceqq`+movemask-gather per needle byte) to replace **one** x86 instruction.

**The fix — use the SIMD substring ALGORITHM, not the instruction.** The standard
(Mula) first-and-last-byte filter is O(1) vector ops per window: broadcast
`needle[0]` and `needle[k-1]`, compare against `D[i..]` and `D[i+k-1..]`, AND the
two masks to get candidate offsets, and run a full `memcmp` only on the (rare)
survivors:
```cpp
uint8x16_t first = vdupq_n_u8(needle[0]);
uint8x16_t last  = vdupq_n_u8(needle[k-1]);
for (size_t i = 0; i + 16 + k <= n + 1; i += 16) {
    uint32_t mask = neon_movemask_u8(vandq_u8(
        vceqq_u8(vld1q_u8(s+i),       first),
        vceqq_u8(vld1q_u8(s+i+k-1),   last)));
    while (mask) { unsigned b = __builtin_ctz(mask);
        if (memcmp(s+i+b, needle, k) == 0) return i+b;
        mask &= mask - 1; }
}
// + scalar tail
```

**Measured — two framings, be honest about which one applies:**
- A *naive* O(k)-per-window `cmpestrm` emulation (k shifted `vceqq_u8` + movemask
  AND-reduce, one iteration per needle byte) vs the first/last-byte algorithm:
  the emulation is **~2× slower** (k=16, 700K searches over 8 KiB — 1.98 s vs
  1.00 s, both 50K/0 vs oracle, identical 186114 matches).
- BUT a *competent* spec-driven port rarely writes the naive O(k) version: because
  the candidate positions get a trailing `memcmp` confirm anyway, a good port
  filters on just the **first byte** (`vceqq_u8` + movemask, O(1)/window) — which
  is already close to the first/last-byte algorithm. A fair spec-driven A/B
  (first-byte-filter BEFORE vs first-and-last-byte AFTER, needle mostly absent,
  identical work) measured only **~3% apart** (≈3.49 s vs ≈3.36 s).

**Rule.** When an x86 intrinsic has *no* NEON equivalent AND the surrounding
routine solves a well-known problem (substring search, set membership, etc.),
port the **problem** with a SIMD-friendly algorithm, not a faithful per-window
transliteration of the instruction. The big win (~2×) is specifically over a
*naive* O(k) emulation; against an already-reasonable first-byte filter the
first-and-last-byte refinement is a smaller (~single-digit-%) gain that grows with
needle length and alphabet skew. Contrast a genuinely irreducible limit (large-
table gather, above) where the scalar/emulated path *is* the floor.

---

## Variable-Count Shifts

**x64**: `_mm_sll_epi32(a, count)` shifts by a runtime-variable count stored in
a separate XMM register (only the low 64 bits used as count).

**ARM64**: NEON uses `vshlq_s32(a, count_vec)` where `count_vec` is a vector of
shift amounts (positive = left shift, negative = right shift). The count must be
broadcast to a vector:

```cpp
// x64:
__m128i _Shifted = _mm_sll_epi32(data, _mm_cvtsi32_si128(n));

// ARM64:
int32x4_t _Shifted = vshlq_s32(vreinterpretq_s32_u32(data), vdupq_n_s32(n));
// For right shift: vdupq_n_s32(-n)
```

For **immediate** (compile-time constant) shifts, use `vshlq_n_u32(a, n)` which
is more efficient than the variable-count form.

---

## The 4-byte Tail UB Trap

**x64**: The scalar tail in x64 code often uses `memcpy` or direct pointer casts
for 4-byte and 8-byte chunks:
```cpp
unsigned long long _Val;
memcpy(&_Val, ptr, 8);  // x64 scalar tail — fine
```

**ARM64**: Direct `*(uint32_t*)ptr` dereference is **undefined behavior** for
non-4-byte-aligned pointers. The NEON lane intrinsic handles alignment safely:

```cpp
// WRONG on ARM64 (UB for unaligned ptr):
uint32_t _Val = *static_cast<uint32_t*>(ptr);

// CORRECT:
uint32x2_t _V = vdup_n_u32(0);
_V = vld1_lane_u32(static_cast<uint32_t*>(ptr), _V, 0);
uint32_t _Val = vget_lane_u32(_V, 0);
```

This is a subtle but real bug that appears when porting x64 scalar tail code to ARM64.
The STL consistently uses `vld1_lane_u32` / `vst1_lane_u32` for 4-byte tails.

---

## Cross-128-bit-Lane Operations

**x64**: AVX2 can move data across the 128-bit halves of a YMM register —
`_mm256_permutevar8x32_epi32`, `_mm256_permute2x128_si256`,
`_mm256_permute4x64_epi64`, `_mm512_permutexvar_*`.

**ARM64**: no such instruction exists, because a NEON vector *is* 128 bits. But
before reaching for a `vqtbl2q_u8`/`vqtbl4q_u8` emulation, classify the permute:

**(a) Repair permute — delete it.** x86's unpack/shuffle family
(`_mm256_unpacklo_epi8/16/32/64`, `_mm256_unpackhi_*`, `_mm256_shuffle_epi32`)
operates **independently within each 128-bit half**. A 256-bit transpose built
from them therefore ends with its words in a *mis-ordered* arrangement, and the
kernel appends one cross-lane permute purely to fix that. Example — c-blosc2's
`shuffle4_avx2` ends with `_mm256_permutevar8x32_epi32(v, {0,4,1,5,2,6,3,7})`.
A NEON port that decomposes the network into two genuinely separate 128-bit
halves **never creates the mis-ordering**, so the permute has nothing to repair:
translating it re-scrambles already-correct data. Work the lane bookkeeping
through the decomposed network, and keep a permute only if the required output
order still differs. This is the common case for transpose/interleave kernels,
and it is a silent-corruption bug when got wrong (the output is well-formed, just
permuted).

**(b) Genuine cross-lane data movement — emulate it.** A permute that shuffles
live data (not a repair) does need work: `vqtbl2q_u8` / `vqtbl4q_u8` over the
concatenated halves for byte-granular tables, or explicit
`vextq_*` / `vcombine_*` / `vzip1q_*`+`vzip2q_*` of the two halves for
structured moves.

**Diagnostic**: if removing the permute from the ported kernel makes it *match*
the x86 output, it was case (a). Always gate the decision on a byte-exact
comparison against the x86 result, never on inspection.

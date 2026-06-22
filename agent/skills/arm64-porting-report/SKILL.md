---
name: arm64-porting-report
description: "Generate an x64-to-ARM64 porting report in YAML format. Triggers when the user asks to generate/create/write an ARM64 porting report or migration analysis. Trigger phrases include: generate arm64 porting report, create porting report, write porting report, arm64 porting analysis, generate migration report, porting analysis for this code."
author: Hao Zeng
---

# ARM64 Porting Report Generator

Generate a structured YAML porting report when the user asks to create an ARM64 porting report.

## Trigger Phrases

generate arm64 porting report / create porting report / write porting report / arm64 porting analysis / generate migration report / porting analysis for this code / generate porting analysis

## Output Format

Always output the report as a fenced YAML code block (`\`\`\`yaml`), followed by a brief summary section.

The YAML **must** conform to the `x64-to-arm64-porting` schema. See [schema.md](references/schema.md) for the full field reference.

### Top-level structure

```yaml
schema: x64-to-arm64-porting
description: |
  <one or two sentences describing the overall porting scope>

porting_items:
  - <one entry per logical porting unit>
```

### Per-item field reference

| Field | Required | Notes |
|---|---|---|
| `id` | yes | kebab-case unique identifier, e.g. `function-prolog` |
| `title` | yes | Human-readable title |
| `description` | yes | Multi-line block scalar; describe what the code does and why it needs porting |
| `source_architecture` | yes | Always `x86_64` |
| `target_architecture` | yes | Always `AArch64 (ARM64)` |
| `calling_convention` | yes | `Microsoft x64 (Windows)` or `AAPCS64 (Linux)` |
| `file_path` | yes | Source file path, e.g. `src/compute.asm` |
| `code_range` | yes | Line range, e.g. `21-30` |
| `semantics` | yes | Numbered list block scalar: what each step of the original code does |
| `constraints` | yes | YAML sequence of ARM64-specific constraints and porting notes |
| `register_mapping` | yes | YAML mapping: `x64_reg: arm64_reg  # comment` |
| `intrinsic_equivalents` | only for SIMD | YAML mapping: `sse_pattern: neon_intrinsic` |
| `target_feature` | when emitting one of several ARM64 variants of the same x86 kernel | string identifying the ARM64 hardware-feature variant this item targets (e.g. `armv8-a+crc`, `armv8.2-a+crc+crypto+sha3`, `armv8-a+sve2`); when present, items that share `file_path` MAY have overlapping `code_range` (Completeness Rule #6) |
| `variant_group` | when emitting variants | string id linking the items that share an x86 kernel but target different ARM64 features; items in the same group MUST have the same `id` prefix and matching `file_path`/`code_range`. See "Architectural Variants" below. |

## Scoping the `code_range`

The `code_range` is what the downstream `easywos-spec` matcher actually reads. Two scoping bugs are common and produce empty match sets:

### Rule A — Template-Body Recursion (`#include "*_tpl.h"`)

Many SIMD kernels in real codebases are **thin wrappers** over a template header:

```c
/* arch/x86/crc32_vpclmulqdq_avx512.c */
#include "crc32_pclmulqdq_tpl.h"   /* ← all the _mm512_clmulepi64_epi128 lives here */

Z_INTERNAL uint32_t crc32_vpclmulqdq_avx512(uint32_t crc, ...) {
    return crc32_copy_impl(crc, NULL, buf, len, 0);   /* ← 3-line wrapper */
}
```

If you scope `code_range` at the wrapper alone (e.g. lines `10-12`), the matcher reads 3 lines that contain **zero intrinsics** and reports no candidates — even though the real porting work is dense with `_mm512_*` calls inside the included template. This is the most common scoping mistake.

**Required behaviour**: when a `.c` file `#include`s a `*_tpl.h` (or `*_p.h`, or any header that lives under the same `arch/<name>/` directory or `arch/shared/`), and that header contains SIMD intrinsics or other architecturally significant constructs, do one of the following:

1. **Preferred — scope `code_range` to span both the wrapper *and* the template body**. Emit `code_range` as the union of:
   - the wrapper function's lines in the `.c` file, AND
   - the relevant body region in the template header.

   Express this as a multi-range string: `code_range: "10-12, ../shared/crc32_pclmulqdq_tpl.h:140-220"` — the matcher already accepts comma-separated ranges with optional `path:` prefixes.

2. **Acceptable** — emit a separate sibling `porting_item` for the template body (with its own `id`, e.g. `crc32-pclmulqdq-tpl-body`) and reference it from the wrapper item via the `description` field. Use this form only when the template body is genuinely shared across multiple wrappers (e.g. a CRC template instantiated by both AVX2 and AVX-512 wrappers); the body item must appear *before* its wrapper items in the `porting_items` array so dependencies resolve top-down.

**How to detect template inclusion**: scan the wrapper file for `#include "<basename>_tpl.h"`, `#include "<basename>_p.h"`, or any `#include` whose path resolves under `arch/`. Then `grep -c "_mm[0-9]*_\|__m[0-9]+\|__mmask\|vpclmulqdq" <header>`. If the count is > 5, the body is intrinsic-heavy and Rule A applies.

### Rule B — Capture macro-instantiation hooks

A wrapper may also use `#define LONGEST_MATCH foo` / `#include "match_tpl.h"` to instantiate a template under a configured name. The 10-line `#define`-block alone has zero intrinsics. Apply Rule A: include the template body in `code_range` (or emit a sibling item for the template body).

## Architectural Variants — One x86 Kernel, Multiple ARM64 Targets

A single x86 SIMD kernel often deserves **more than one** ARM64 implementation, gated on different runtime CPU features. The classic case is CRC32:

| x86 kernel | ARM64 baseline (always available on ARMv8) | ARM64 fast path (when SHA3 + fast PMULL) |
|---|---|---|
| `crc32_vpclmulqdq_avx512` | `crc32_armv8` (uses `__crc32d`) | `crc32_armv8_pmull_eor3` (uses `vmull_p64` + `EOR3`, 192 bytes/iter) |

zlib-ng upstream ships **both** variants and lets the runtime functable pick the fastest one the CPU supports. If your report emits only one porting_item for the x86 kernel, the dispatcher will produce only one ARM64 variant and the project loses the fast-path option.

**Required behaviour**: when an x86 SIMD kernel can plausibly map to multiple ARM64 implementations (typically when the source uses CLMUL / PCLMULQDQ / VPCLMULQDQ, AES, SHA, or any operation with both a baseline ARMv8 instruction *and* an extension-based fast path), emit one `porting_item` per ARM64 variant:

- All variant items share the same `variant_group` value (e.g. `variant_group: crc32-vpclmulqdq`).
- Each item carries a distinct `target_feature` (e.g. `armv8-a+crc`, `armv8.2-a+crc+crypto+sha3`, `armv8-a+sve2`).
- All variant items in the group point at the same `file_path` and the same `code_range` — Completeness Rule #6's "no overlap" prohibition does not apply within a `variant_group` (see Rule #6 below).
- Each item's `id` MUST start with the variant_group prefix and end with the variant tag, e.g. `crc32-vpclmulqdq-armv8-crc` and `crc32-vpclmulqdq-pmull-eor3`.
- Each item's `description`, `constraints`, and `intrinsic_equivalents` describe the **ARM64 variant**, not the x86 source — that is, two variants of the same x86 code will have *identical* `semantics` (same algorithm) but *different* `constraints` and `intrinsic_equivalents` (different ARM64 instruction families).

### When to emit variants — decision table

| x86 construct seen | Emit baseline item | Emit fast-path variant |
|---|---|---|
| `_mm512_clmulepi64_epi128`, `_mm_clmulepi64_si128`, `pclmulqdq` (any form) | yes (`+crc`) | yes (`+crc+crypto+sha3` if EOR3 makes sense; or `+crypto` for plain PMULL) |
| `_mm_aes*`, `vaesenc*`, `_mm_aesenc*` | yes (`+crypto+aes`) | only if SVE2 / AESPMULL extension is in scope |
| `_mm_sha*`, `_mm256_sha*` | yes (`+crypto+sha2`) | yes if SHA3 extension is in scope |
| `_mm512_dpbusd_epi32` (VNNI) | yes (`+dotprod`) | yes (`+i8mm`) when ARMv8.6 i8mm is in scope |
| Plain `_mm*_add/sub/mul/load/store` (no specialty) | no, single item | no |

If unsure, **do not** emit a fast-path variant — a missing variant is fixable downstream by widening the report; an over-emitted variant produces redundant porting work.

## How to Fill Each Field

### `calling_convention`
- Use `Microsoft x64 (Windows)` when targeting MSVC/Windows ARM64 or when source was compiled for Windows.
- Use `AAPCS64 (Linux)` when targeting Linux/Android ARM64.

### `register_mapping` — Microsoft x64 to ARM64

Integer parameters:
```
rcx -> x0    rdx -> x1    r8  -> x2    r9  -> x3
rax -> x0   (return value)
rbp -> x29  (frame pointer)
rsp -> sp   (stack pointer)
rbx -> x19  rsi -> x20  rdi -> x21  r12 -> x22  r13 -> x23  r14 -> x24  r15 -> x25
```

Floating-point:
```
xmm0 -> v0   xmm1 -> v1   ...  xmm7 -> v7   (parameters/scratch)
xmm8 -> v8   ...  xmm15 -> v15              (callee-saved on ARM64: d8-d15)
```

### `constraints` — Common entries

Always include relevant ones from:
- Stack must remain 16-byte aligned on ARM64
- ARM64 uses x29 (FP) and x30 (LR) as frame pointer and link register
- Callee-saved registers on ARM64 (AAPCS64): x19-x28, d8-d15
- Use STP/LDP for paired register save/restore
- Parameters arrive in x0-x7, not rcx/rdx/r8/r9
- For SIMD: ARM64 NEON uses 128-bit V registers (v0-v31) with typed lanes
- For SIMD: Use LD1 for potentially unaligned loads (not LDR q-form)
- For SIMD: ARM64 loop control uses CBZ/CBNZ or CMP+B.cc
- For SIMD: FADDP (pairwise add) preferred for horizontal reduction
- No direct movhlps equivalent; use EXT or DUP+FADDP

### `intrinsic_equivalents` — Common NEON mappings

```yaml
movups_load:        vld1q_f32(ptr)
movdqu_load:        vld1q_s32((const int32_t*)ptr)
addps:              vaddq_f32(a, b)
addpd:              vaddq_f64(a, b)
subps:              vsubq_f32(a, b)
mulps:              vmulq_f32(a, b)
andps:              vandq_s32(a, b)
paddb/paddw/paddd:  vaddq_s8 / vaddq_s16 / vaddq_s32
psubb/psubw/psubd:  vsubq_s8 / vsubq_s16 / vsubq_s32
pmullw:             vmulq_s16(a, b)
pcmpeqd:            vceqq_s32(a, b)
pslld_imm:          vshlq_n_s32(a, imm)
psrld_imm:          vshrq_n_u32(a, imm)
horizontal_sum_f32: vaddvq_f32(v)
movhlps_hi_to_lo:   vget_high_f32(v)
shufps_dup_hi:      vdupq_laneq_f32(v, 2)
```

## Completeness Rules

1. **One porting_item per logical unit** — separate function prologs, loop bodies, SIMD kernels, and epilogs into distinct items.
2. **Accurate register_mapping** — only include registers that actually appear in the code.
3. **semantics as numbered steps** — each step describes one logical operation. Keep steps atomic.
4. **All constraints must be actionable** — phrase each as a rule the ARM64 implementer must follow.
5. **intrinsic_equivalents only for SIMD items** — omit this field for scalar or control-flow-only items.
6. **No accidental overlapping code_range intervals** — when two or more items share the same `file_path`, their `code_range` values MUST NOT overlap **unless** they are members of the same `variant_group` (see "Architectural Variants" above). Three sub-cases:
   - **No `variant_group` on either side** → overlap is a bug. Read the overlapping lines: if they contain SIMD intrinsics, merge the items; if they are only `#define` / `#include` / pure-C boilerplate, trim the dependent item's `code_range` to cover only its own new lines.
   - **Same `variant_group` on both sides** → overlap is **expected and required**: the two items are different ARM64 variants of the same x86 kernel and must point at the same source bytes. Do not merge or trim.
   - **Different `variant_group` (or one has none)** → overlap is a bug; treat as the first case.
7. **Template-body inclusion is mandatory when the wrapper is thin** — see Rule A above. A `code_range` that points at a 1-10 line wrapper whose body is `return tpl_impl(...)` over an `#include`d template header MUST extend `code_range` to cover the template body (or emit a sibling template-body item). A purely-wrapper `code_range` is a defect even if the file compiles.

## Validation

After generating a report, apply these checks before finalising item count and `code_range` values:

1. **Detect overlap** — for every pair of items with identical `file_path`, parse `code_range` as `[start, end]` integers and test `max(start1, start2) <= min(end1, end2)`. Any pair that satisfies this condition has an overlap.
2. **Classify the overlap** —
   - If both items in the overlapping pair carry the **same `variant_group`** value, the overlap is intentional (Architectural Variants). Verify their `id` values share the variant_group prefix and that each item carries a distinct `target_feature`. No further action.
   - Else, read the overlapping lines. If they contain SIMD intrinsics (e.g. `_mm_`, `_mm256_`, `_mm512_`, `vmull`, `vaddq_`), the items are duplicating real porting work → merge them into one item with a combined `code_range`.
3. **Trim boilerplate overlap** — if the overlapping lines are only `#define`, `#include`, macro closures, or template instantiation hooks (no intrinsics), adjust the dependent item's `code_range` to start at the first non-overlapping line, making all ranges disjoint.
4. **Audit thin wrappers** — for every item whose `code_range` spans fewer than 12 lines, read those lines. If the body is dominated by `#include "<basename>_tpl.h"` / `#include "<basename>_p.h"` and a single delegating call (e.g. `return foo_impl(...);`), extend `code_range` per Rule A. A `code_range` that yields zero SIMD intrinsics on a scan of its bytes when the *named operation* (CRC32, AES, CLMUL, etc.) is clearly SIMD-bound is a strong signal that the template body was missed.
5. **Audit missing variants** — for every item whose intrinsics include CLMUL / PCLMULQDQ / VPCLMULQDQ / AES / SHA, check whether a fast-path ARMv8.2-A variant should also be emitted (Architectural Variants decision table). Either emit the variant or note in the item's `description` why it was deliberately skipped.
6. **Update the item count** — after merging, trimming, extending, or splitting, recount items and update the top-level `description` if it states a count.

## After the YAML Block

After the closing ` ``` `, add a **Porting Notes** section (3-6 bullet points) summarising:
- The most complex/risky translation decisions
- Any intrinsics with no 1:1 NEON equivalent and the workaround
- Calling convention differences that affect all items
- Performance implications (e.g., horizontal reduction cost on ARM64)

## Example Output Skeleton

```yaml
schema: x64-to-arm64-porting
description: |
  Porting report for <project/function name>: translates <N> x86_64 code
  sections to AArch64, covering <summary of what is being ported>.

porting_items:

  - id: <kebab-case>
    title: <Title>
    description: |
      <What this code does and why it requires porting attention.>

    source_architecture: x86_64
    target_architecture: AArch64 (ARM64)
    calling_convention: Microsoft x64 (Windows)

    file_path: <path/to/file.asm>
    code_range: <start>-<end>

    semantics: |
      1. <First logical operation>
      2. <Second logical operation>

    constraints:
      - <Constraint 1>
      - <Constraint 2>

    register_mapping:
      <x64>: <arm64>  # <role comment>

    intrinsic_equivalents:  # include only for SIMD items
      <sse_op>: <neon_op>
```

## Worked Example — CRC32 Wrapper + Template Body + Two ARM64 Variants

Demonstrates Rule A (template-body recursion) and Architectural Variants together. The x86 kernel is `crc32_vpclmulqdq_avx512` — a 3-line wrapper in `arch/x86/crc32_vpclmulqdq_avx512.c` over the SIMD-heavy `arch/x86/crc32_pclmulqdq_tpl.h` template (which contains `_mm512_clmulepi64_epi128`, `_mm512_ternarylogic_epi32`, etc.). On ARM64 this maps to two implementations: a baseline `+crc` path using hardware CRC32 instructions, and an ARMv8.2 `+crc+crypto+sha3` fast path using `vmull_p64` + 3-way EOR3 fold.

```yaml
porting_items:

  - id: crc32-vpclmulqdq-armv8-crc
    title: CRC32 (VPCLMULQDQ+AVX512 → ARMv8 hardware CRC)
    variant_group: crc32-vpclmulqdq
    target_feature: armv8-a+crc
    description: |
      Baseline ARMv8 hardware CRC variant of crc32_vpclmulqdq_avx512.
      Uses the __crc32d / __crc32w / __crc32h / __crc32b instructions
      from <arm_acle.h>. Always available on ARMv8-A; no CLMUL emulation.
      Pair with the +crc+crypto+sha3 variant below for cores that
      support PMULL+EOR3.

    source_architecture: x86_64
    target_architecture: AArch64 (ARM64)
    calling_convention: AAPCS64 (Linux)

    file_path: arch/x86/crc32_vpclmulqdq_avx512.c
    # NOTE: Rule A — wrapper is 3 lines, body is in the included template;
    # the range below covers BOTH the wrapper AND the template body.
    code_range: "10-12, arch/x86/crc32_pclmulqdq_tpl.h:140-220"

    semantics: |
      1. Process 64-byte blocks: 8x __crc32d unrolled
      2. Reduce trailing bytes (< 64) with __crc32w / __crc32h / __crc32b
      3. Apply the standard ~crc / ~crc post-condition pair

    constraints:
      - Hardware CRC32 requires -march=armv8-a+crc (or MSVC /arch:armv8.0)
      - Use Z_TARGET_CRC = __attribute__((target("crc"))) on the function
      - Align src to 8 bytes before the unrolled __crc32d main loop
      - No CLMUL emulation needed; do not pull in <arm_neon.h> for this variant

    register_mapping:
      rdi: x0    # crc / buf (depending on variant)
      rsi: x1    # buf / src
      rdx: x2    # len

    intrinsic_equivalents:
      _mm512_clmulepi64_epi128: __crc32d(crc, *src64++)   # direct hardware
      scalar_tail_word: __crc32w(crc, w32)
      scalar_tail_hword: __crc32h(crc, w16)
      scalar_tail_byte: __crc32b(crc, b)

  - id: crc32-vpclmulqdq-pmull-eor3
    title: CRC32 (VPCLMULQDQ+AVX512 → PMULL + EOR3 fast path)
    variant_group: crc32-vpclmulqdq
    target_feature: armv8.2-a+crc+crypto+sha3
    description: |
      Fast-path ARMv8.2 variant of crc32_vpclmulqdq_avx512. Uses vmull_p64
      / vmull_high_p64 (PMULL) for carry-less multiply and EOR3 (3-way XOR
      from the SHA3 extension) to fold 192 bytes per iteration via 3-way
      parallel scalar CRC + 9-lane PMULL fold. 2-3x faster than the +crc
      baseline on Apple M-series, Cortex-X4, and Neoverse V2+.

      The functable picks this variant when cf.arm.has_crc32 &&
      cf.arm.has_pmull && cf.arm.has_eor3 && cf.arm.has_fast_pmull;
      otherwise the baseline +crc variant is used.

    source_architecture: x86_64
    target_architecture: AArch64 (ARM64)
    calling_convention: AAPCS64 (Linux)

    file_path: arch/x86/crc32_vpclmulqdq_avx512.c
    # Same code_range as the +crc variant — they are different ARM64
    # implementations of the same x86 source bytes (overlap is allowed
    # within a variant_group; see Completeness Rule #6).
    code_range: "10-12, arch/x86/crc32_pclmulqdq_tpl.h:140-220"

    semantics: |
      1. Process 192-byte blocks: 3 parallel scalar CRC streams
         (3x 64-byte segments via 8x __crc32d each) plus a 9-lane PMULL
         fold accumulator
      2. Reduce the three scalar CRCs into one via PMULL multiply by
         the appropriate fold polynomial
      3. Reduce the PMULL accumulator to a 32-bit residual via Barrett
      4. Combine scalar + PMULL residuals; apply ~crc post-condition

    constraints:
      - Requires -march=armv8.2-a+crc+crypto+sha3 (or MSVC equivalent)
      - Use Z_TARGET_PMULL_EOR3 = __attribute__((target("+crc+crypto+sha3")))
      - vmull_p64 and vmull_high_p64 from <arm_acle.h>; poly128_t result
      - veor3q_u64 / veor3q_u8 from <arm_neon.h> (SHA3 extension)
      - Runtime guard: HWCAP_PMULL && HWCAP_SHA3 && fast-PMULL detection
      - Define clmul_lo_lo / clmul_hi_lo / clmul_lo_hi / clmul_hi_hi
        macros (see crc32-pmull spec) to avoid inline reinterpret chains
      - 192-byte iteration count must be tuned: smaller buffers should
        fall through to the baseline +crc variant via a length threshold

    register_mapping:
      rdi: x0    # crc / buf (depending on variant)
      rsi: x1    # buf / src
      rdx: x2    # len

    intrinsic_equivalents:
      _mm512_clmulepi64_epi128: vmull_p64(...) / vmull_high_p64(...)
      _mm512_ternarylogic_epi32: veor3q_u8(a, b, c)   # 3-way XOR via EOR3
      _mm_xor_si128: veorq_u8(a, b)
      _mm_load_si128: vld1q_u8(ptr)
      _mm_store_si128: vst1q_u8(ptr, v)
      barrett_reduction_step: clmul_hi_lo + clmul_lo_hi + veorq_u8
```

After such a report runs through the easywos-spec pipeline, the dispatcher
sees both items in the matched YAML, generates `crc32_armv8.c` for the
baseline variant, and `crc32_armv8_pmull_eor3.c` for the fast-path variant
— matching the upstream zlib-ng layout exactly.

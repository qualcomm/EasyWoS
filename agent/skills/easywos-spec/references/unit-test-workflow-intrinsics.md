# Unit Test Generation Workflow — Intrinsics Variant

Sister specification of [unit-test-workflow.md](unit-test-workflow.md).

Use this flow when leaf-skill outputs are C/intrinsics files (NEON, SVE,
hardware-CRC, etc.) rather than hand-written `*.asm`. Both flows share the
per-item fixture rule, function signature patterns, correctness verification,
and boundary condition lists. Only the *test seam* and the *build pipeline*
change.

## When to pick this flow vs the assembly variant

| Trigger | Flow |
|---|---|
| Leaf-skill outputs include any `*.asm` file with `EXPORT` directives | [unit-test-workflow.md](unit-test-workflow.md) (assembly) |
| Leaf-skill outputs are all `*.c` / `*.h` calling `<arm_neon.h>` / `<arm_acle.h>` intrinsics | This file (intrinsics) |
| Mixed (some items dispatch to asm leaf skills, others to intrinsic ones) | Generate both — one driver per language family, separate gtest binaries |

A practical detector: look at the dispatcher's `source` field for the matched
specs. If at least one resolves to `x64-to-arm64-asm-porting` or
`x64-asm-to-arm64-asm`, the assembly flow applies for that item; if it
resolves to `sse-avx-to-neon` or `intrinsics-x64-to-arm64/intrinsic-mapping`,
the intrinsics flow applies.

## Per-porting-item Rule

Same as the assembly variant: each porting item gets its own gtest fixture
class and its own kernel-under-test entry point. Items MUST NOT be merged.

## Test Seam — Why You Need a `test_kernels_<arch>.c` Wrapper

Hand-written assembly already has a clean test seam: each porting item is a
function with `EXPORT` and a documented C ABI. The test calls it via
`extern "C"` and the linker resolves it from the `.obj` produced by `armasm64`.

Intrinsics ports don't get that for free. The leaf-skill output (e.g.,
`adler32_neon.c`, `slide_hash_neon.c`) typically pulls in project-specific
headers (`zbuild.h`, `deflate.h`, project-defined typedefs) and uses
project-specific function names that take project types. A test binary cannot
link against those without dragging the entire project's build into the test.

**Solution: a sibling file `test_kernels_<arch>.c` that re-exposes each SIMD
kernel with a clean C ABI**, byte-equivalent to the leaf-skill body but with:

- raw integer / pointer parameters instead of project typedefs
  (e.g., `uint16_t *table` instead of `Pos *table`,
  `const uint8_t *src` instead of `deflate_state *s`);
- only `<arm_neon.h>`, `<arm_acle.h>` (or the MSVC `<intrin.h>` shim — see
  below), `<stdint.h>`, `<string.h>` includes;
- no calls to project allocators, asserts, or compatibility macros.

This is the *intrinsics counterpart of `EXPORT test_<func>`*: a stand-alone
unit with a clean C ABI.

## Test Function Signature Patterns

Same three patterns as the assembly variant — repeat here for completeness:

**Compute pattern** — verifies SIMD computation:
```c
uint32_t test_adler32_neon(uint32_t adler, const uint8_t *src, size_t len);
uint32_t test_compare256_neon(const uint8_t *a, const uint8_t *b);
```

**Transform pattern** — verifies in-place or output-buffer transforms:
```c
void test_slide_hash_neon(uint16_t *table, uint32_t entries, uint16_t wsize);
void test_chunkcopy_neon(uint8_t *dst, const uint8_t *src, size_t len);
```

**Compute + transform combined** — the copy variants:
```c
uint32_t test_crc32_copy_armv8(uint32_t crc, uint8_t *dst, const uint8_t *src, size_t len);
```

The prolog/epilog pattern from the assembly variant rarely applies to
intrinsics ports (it tests register save/restore which the C compiler handles
automatically). Skip it unless the kernel does inline asm.

## MSVC ARM64 Compatibility Shim — Required Boilerplate

Every intrinsics test must include this block at the top of
`test_kernels_<arch>.c` to compile on both MSVC ARM64 and GCC/Clang:

```c
#include <stdint.h>
#include <string.h>
#include <arm_neon.h>
#if defined(_MSC_VER)
#  include <intrin.h>      /* MSVC ARM64: declares __crc32b/h/w/d directly */
static inline int neon_ctzll(uint64_t x) {
    unsigned long idx = 0;
    _BitScanForward64(&idx, x);
    return (int)idx;
}
#  define NEON_CTZLL(x) neon_ctzll(x)
#else
#  include <arm_acle.h>
#  define NEON_CTZLL(x) __builtin_ctzll(x)
#endif
```

Two specific compatibility issues this addresses:

| Issue | GCC/Clang | MSVC ARM64 | Shim |
|---|---|---|---|
| ARMv8 CRC intrinsics (`__crc32b/h/w/d`) | `<arm_acle.h>` | `<intrin.h>` (same names, different header) | conditional include |
| 64-bit count-trailing-zeros | `__builtin_ctzll` | `_BitScanForward64` (different signature, returns via out-param) | wrapper function |

If your kernel uses additional GCC-isms (`__builtin_clzll`, `__builtin_popcountll`,
`__builtin_bswap64`, etc.) add the corresponding `_BitScanReverse64` /
`__popcnt64` / `_byteswap_uint64` wrappers in the same block.

## Test Correctness Verification

Same rule as assembly: derive expected values from the algorithm's
mathematical definition, not from a runtime x64 reference. Provide pure-C
scalar reference functions in `test_<name>.cpp` (`adler32_ref`,
`crc32_ref`, etc.) and `EXPECT_EQ` against them.

## Boundary Condition Tests

Same lists as the assembly variant. Apply per the kernel's signature pattern:

- **Compute pattern** — empty input, count below SIMD width, count not a
  multiple of SIMD lane width, very large / small / denormalized values, all
  zeros, all ones, mixed-magnitude, large counts (4096+), non-default initial
  accumulator.
- **Transform pattern** — count = 0, count = 1, count not a multiple of SIMD
  width, max representable values, misaligned src and dst.

The assembly variant adds prolog/epilog boundary tests; skip those for
intrinsics unless the kernel uses inline asm.

## Generated File Structure

For each dispatcher run that produces intrinsics output, generate:

| File | Purpose |
|------|---------|
| `<file>_neon.c` (or `<file>_armv8.c`) — one per dispatched item or item-group | Leaf-skill output. Project-specific. NOT linked into the test binary directly. |
| `test_kernels_<arch>.c` | Clean-C-ABI extractions of each kernel from the leaf-skill outputs. Single file, no project deps. Includes the MSVC shim block above. |
| `test_<name>.cpp` | gtest source with `extern "C"` declarations for each kernel, scalar reference functions, one fixture per porting item, normal + boundary tests. |
| `CMakeLists.txt` | ARM64-only build with FetchContent gtest. See [cmake-template-intrinsics.md](cmake-template-intrinsics.md). |
| `build_and_compare.bat` | Build script — same shape as assembly variant. See [build-script-template.md](build-script-template.md). |

## Comparison with the Assembly Flow

| Step | Assembly | Intrinsics |
|---|---|---|
| Test seam | `EXPORT test_<func>` in `.asm` | `test_kernels_<arch>.c` re-exporting each kernel |
| Build step | `armasm64` custom command produces `.obj` | normal C `add_library` produces `.lib` |
| Header concerns | none (asm is self-contained) | MSVC shim block required (CRC32 + ctzll) |
| Compile flags | none beyond ARM64 default | `-march=armv8-a+crc` for non-MSVC; MSVC enables by default |
| Failure mode if seam is missing | linker error: undefined `test_<func>` | linker error: undefined kernel symbol; or compiler error trying to drag in project headers |

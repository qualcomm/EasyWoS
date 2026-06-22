# Unit Test Generation Workflow

After the dispatcher executes leaf skills and produces ARM64 assembly output, generate unit tests to verify functional correctness.

> **Asm-only flow.** This file covers the assembly flow (leaf-skill outputs are
> hand-written `*.asm` with `EXPORT` directives). For C/intrinsic kernels (NEON,
> ARMv8 hardware-CRC, etc.), see the sister spec
> [unit-test-workflow-intrinsics.md](unit-test-workflow-intrinsics.md). The
> selection rule is in [../SKILL.md](../SKILL.md) Section 7.3.

## Per-porting-item Rule

Each porting item in the matched YAML SHALL have its own:
- Separately exported ARM64 assembly function (e.g., `test_prolog_epilog`, `test_simd_sum`)
- Corresponding gtest test fixture class (e.g., `PrologEpilogTest`, `SimdSumTest`)

Porting items MUST NOT be combined into a single test function. This enables isolating which porting item's implementation fails.

## Test Function Signature Patterns

The test function's signature is derived from the porting item's `semantics`, `constraints`, and `register_mapping` fields. Supported patterns:

**Prolog/epilog pattern** — verifies callee-saved register preservation and frame correctness:
```c
void* test_prolog_epilog(void* p1, unsigned int p2, void* p3);
```
Takes pointer + integer args, returns the first pointer unchanged. If return != input, callee-saved registers were corrupted.

**Compute pattern** — verifies SIMD/scalar computation correctness:
```c
float test_simd_sum(const float *array, unsigned int count);
```
Takes data pointer + count, returns a computed scalar result. Verified against mathematically expected value.

**Transform pattern** — verifies in-place or output-buffer transforms:
```c
void test_transform(const float *input, float *output, unsigned int count);
```
Takes input pointer + output pointer + count, writes result to output buffer. Verified element-by-element.

## Test Correctness Verification

Tests verify ARM64 assembly output against expected values derived from the porting item's `semantics` field:
- No x64 reference implementation is needed
- Expected values are computed from the algorithm's mathematical definition
- Use `EXPECT_NEAR` with appropriate epsilon for floating-point results
- Use `EXPECT_EQ` for pointer/integer results

## Boundary Condition Tests

Every generated test fixture SHALL include boundary condition tests exercising edge cases specific to the function's signature pattern.

**Prolog/epilog pattern mandatory boundary tests:**
- NULL pointer input
- UINTPTR_MAX pointer value
- Max uint32 argument (0xFFFFFFFF)
- Misaligned pointer (e.g., 0x10003)
- All arguments at extreme values simultaneously

**Compute pattern mandatory boundary tests:**
- Count below SIMD lane width (e.g., count=2 when SIMD width is 4)
- Count not a multiple of SIMD lane width (e.g., 9, 13)
- Very large float values near overflow (1e30)
- Very small float values near underflow (1e-30)
- Denormalized floats (std::numeric_limits<float>::denorm_min())
- Negative zero (-0.0f)
- Maximum safe accumulation values (FLT_MAX / N)
- All-negative values
- Mixed-magnitude values causing cancellation (e.g., 1e10 + 1.0 + -1e10 + 1.0)
- Large element counts (4096+)

**Transform pattern mandatory boundary tests:**
- Count = 0
- Count = 1
- Count not a multiple of SIMD lane width
- Maximum representable values in the data type
- Input and output buffers at different alignments

## Generated File Structure

For each dispatcher execution output, generate:

| File | Purpose |
|------|---------|
| `test_<name>.cpp` | gtest source with extern "C" declarations, test fixtures, normal + boundary tests |
| `<name>_arm64.asm` | ARM64 armasm64 assembly with one EXPORT per porting item |
| `CMakeLists.txt` | ARM64-only build with FetchContent gtest + armasm64 custom command |
| `build_and_compare.bat` | Build script: cmake configure → build → run tests → report |

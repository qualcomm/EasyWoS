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

## Avoiding False Greens (verification anti-patterns)

A passing test is meaningless until the same mechanism has been *observed
failing*. Per the negative-control discipline, deliberately feed each check
something known-wrong and confirm it reports failure before trusting any pass.
The following traps have all produced **false greens** (a "pass" that tested
nothing, or absorbed a real error) in practice — guard against each:

### The runner tested nothing (name-filter no-op)

A test harness selected by a name string silently exits 0 when the name matches
**no** registered suite — every suite is skipped by the filter and the run
"passes" having executed zero assertions. Always confirm the target was actually
exercised: look for the suite's own banner line (e.g. `== <name> primitives ==`),
a non-zero assertion/case count, or print a marker from inside the kernel. Use
the runner's *real* registered name, not the file/source name (they often
differ). A check that passes instantly or on an empty set is suspect.

### Skipped-when-unwired ≠ complete (tested-when-wired audit)

A harness that only exercises *registered/non-NULL* entries means "exit 0" does
**not** mean "everything was tested" — unwired items are silently skipped, not
failed. After a green run, audit which entries were actually live: an item left
on the fallback is invisible to the oracle. Enumerate the expected set and diff
it against what the run reported exercising; never infer completeness from a pass.

### The negative control was absorbed (perturb the right operand)

When injecting a known-wrong value to prove a check can fail, perturbing a
**rounding/bias constant by ±1 ahead of a large right-shift** is often absorbed
for almost all inputs (`(x + bias) >> 12` swallows a ±1 bias change) → the run
still passes and you wrongly conclude the check is live. Prefer perturbing the
**shift amount** or a **multiplier** — a reliable, non-absorbable break. Match
the perturbation magnitude to the kernel: if the output passes through a large
divisor, the injected error must survive it. Conversely a plain (un-shifted)
output makes a bias perturbation visible.

### Source edits with no effect → look for a duplicate definer

If editing a kernel produces **no observable change** in the result (every
rebuild gives the identical wrong value, even after replacing the body with a
trivial stub), do **not** keep debugging the logic — FIRST check whether a second
translation unit defines the same symbol and the linker bound the reference to
*that* copy. Decomposition/variant artifacts (`*_internal`, `*_aligned`,
size-specific duplicates) frequently shadow the canonical kernel. List every
definer of the symbol (`nm`/`llvm-nm` each candidate object, find which share the
public name) and exclude the redundant ones from the build before resuming.

### A "self-contained superset" file may be a *reduced* implementation

When several translation units define the same symbol and you must pick one,
do **not** assume the largest / most-sizes file is the most complete. A
self-contained superset TU can implement *fewer code paths* per entry — e.g.
omitting an optional argument's conditional branch (an edge-case / "filter
enabled" path) that the dedicated per-size TUs handle. Choosing it passes the
common case and fails only when the harness exercises the omitted path. Prefer the dedicated per-entry TU,
and verify each optional argument / conditional path is actually present in the
file you select (grep the body for the branch, don't infer it from the symbol
set). Trim the superset to only the entries for which it is genuinely complete.

### End-to-end / integration comparison false positives

When validating asm-vs-reference at the *application* level (encode/decode/
round-trip, not per-kernel), traps recur:
- **Embedded config strings.** The output may embed a configuration/identity
  string (build flags, a CPU-feature id, timestamps) that legitimately differs
  between the asm and reference runs, producing a byte mismatch that is **not** a
  computation bug. Suppress such metadata (an info-/banner-off switch) before
  byte-comparing, or compare only the payload.
- **A cosmetic "no acceleration" banner is not proof.** A CLI printing "using
  cpu capabilities: none" may simply lack a name-table entry; the accelerated
  path can still be wired unconditionally. Confirm via a negative control (break
  a kernel, observe the integrated output change), not via the banner.
- **Integration pass is necessary, not sufficient, per input.** A wrong
  primitive only changes integrated output when it flips a downstream decision;
  on some content/config the corrupted kernel leaves the result identical. The
  authoritative per-kernel proof remains the isolated numeric harness (random +
  **boundary** inputs); the e2e layer proves wiring/ABI integration, not kernel
  correctness in isolation. Keep both.

## Generated File Structure

For each dispatcher execution output, generate:

| File | Purpose |
|------|---------|
| `test_<name>.cpp` | gtest source with extern "C" declarations, test fixtures, normal + boundary tests |
| `<name>_arm64.asm` | ARM64 armasm64 assembly with one EXPORT per porting item |
| `CMakeLists.txt` | ARM64-only build with FetchContent gtest + armasm64 custom command |
| `build_and_compare.bat` | Build script: cmake configure → build → run tests → report |

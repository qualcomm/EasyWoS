# Build & Test Command Detection (generic, per project)

The orchestrator must build the WHOLE project for ARM64 and run the project's
OWN test/bench suite (SKILL.md §7.1). These commands are project-specific, so
they are either passed as `--build-cmd`/`--test-cmd` or discovered here. When
discovered, they MUST be confirmed before use — a wrong test command silently
reports false green, so an ambiguous test command is a mandatory STOP.

## Step 1 — detect the build system

Reuse `enable-windows-arm64`'s detector rather than reinventing it:

```bash
python skills/enable-windows-arm64/scripts/detect_build_system.py <project-path>
```

Priority order: cmake > visual_studio > make > ninja > autotools > bazel > qmake
> scons. Also run the enable step so an ARM64 configuration/preset exists.

## Step 2 — derive the BUILD command

| Build system | ARM64 build command (Windows unless noted) |
|---|---|
| CMake (preset) | `cmake --preset <arm64-preset> && cmake --build --preset <arm64-preset>` |
| CMake (no preset) | `cmake -S <src> -B <build> -A ARM64 -T ClangCL [flags] && cmake --build <build> --config Release` |
| CMake (existing toolchain file) | `cmake -S <src> -B <build> -G Ninja -DCMAKE_TOOLCHAIN_FILE=<arm64-toolchain.cmake> [flags] && cmake --build <build>` |
| CMake (aarch64 Linux) | same with the project's aarch64 crosscompile.cmake toolchain |
| Visual Studio | `msbuild <sln> /p:Configuration=Release /p:Platform=ARM64` |
| Make | `make CFLAGS+=... ARCH=arm64` (per project) |
| Ninja | `ninja -C <arm64-build-dir>` |

Prefer the project's OWN ARM64 wiring if it already has one (a `CMakePresets.json`
ARM64 preset, a `build/arm64-*/toolchain.cmake`, a documented cross build) over
a synthesized command — it encodes the project's real flags and sysroot.

**Enabling the test suite is part of the build.** Many projects gate tests behind
a flag (`-DENABLE_TESTS=ON`, `-DBUILD_TESTING=ON`, `--enable-tests`,
`-Dtests=true`). Fold the right flag into the build command so the test target is
actually produced.

## Step 3 — discover the project's OWN test/bench suite

Do NOT settle for the isolated verify-gtest that easywos-spec generated for
per-kernel checking — that is the inner-loop oracle. The outer loop needs the
project's real suite. Search, in priority order:

1. **CTest**: a `CTestTestfile.cmake` / `add_test()` / `enable_testing()` →
   `ctest --test-dir <build> -C Release --output-on-failure`.
2. **A dedicated test/bench target or binary**: names like `*TestBench`,
   `*-test`, `*_test`, `check`, `checkasm`, `unittest`, `gtest_*`. Build it, then
   run the produced binary. (E.g. media codecs often ship a `TestBench` /
   `checkasm` that self-checks every asm primitive against its C reference — that
   is exactly the suite that will catch a ported-kernel regression.)
3. **Build-system test verb**: `make check`, `ninja test`, `meson test`,
   `bazel test //...`, `ctest`.
4. **CI / docs**: the test command in the project's README, CONTRIBUTING, or CI
   config (`.github/workflows/*`, `.gitlab-ci.yml`) is authoritative — copy it and
   adapt the platform to ARM64.

Record the exact command. If more than one plausible suite exists, or none can be
found, STOP and ask the user which command constitutes "the project's tests" —
do not guess, because a green from the wrong command is a false green.

## Step 4 — confirm the test command actually SELECTS tests (zero-test trap)

**A test command that runs zero tests exits 0 and looks green — this is a false
pass, not a pass.** Before trusting any run, confirm the command selected a
non-zero count. This bites hardest with filters: many projects register their
functional tests in CTest under names unrelated to the code area, while the
unit assertions for a kernel live *inside a gtest binary*. Filtering CTest by the
kernel name can then match nothing.

- Real example (zlib-ng): `ctest -R "crc32|adler32|compare256"` matched **0**
  registered tests (CTest registers `example`/`infcover`/`CVE-*`/`minigzip-*`),
  so ctest ran nothing and returned success — a false 1303/1303. The real seam
  was `gtest_zlib.exe --gtest_filter="*crc32*:*adler32*:*compare256*"` = 1303 cases.
- Rule for the driver: verify test count > 0 (`ctest -N -R <filter>` must list
  tests; or the gtest binary's `--gtest_list_tests` under the filter is non-empty).
  A command that executes 0 tests is a **STALL ("no tests executed") / wiring
  bug**, never a green. Prefer running the gtest binary directly with a
  `--gtest_filter` when the assertions live inside it.

## Step 5 — confirm the test can fail (negative control)

Before the outer loop trusts any green from the discovered test command, apply
the negative-control principle once to the suite itself: confirm that a
deliberately broken kernel (or a globally perturbed reference) turns the suite
RED. A suite that stays green under a known-wrong kernel is not actually
exercising the ported code — treat that as the first bug to fix, not as a pass.
(See outer-loop.md "Negative-control gate".)

- Real example (zlib-ng): perturbing `crc32_acle.c` (`return ~crc;` → `return
  crc;`) turned 325 `crc32_copy_variant.acle/*` cases RED — proving both that the
  harness reports failure and that the `.acle` cases exercise the ported ACLE
  kernel (not a generic fallback). Reverting restored 1303/1303.

## Notes on the ARM64 host

- `arm64-windows`: run build+test on a NATIVE Windows-on-ARM64 host (no
  emulation). MSVC ARM64 tools + ClangCL; `armasm64` only if outputs are
  armasm-dialect `.asm` (GAS `.S` uses clang's integrated assembler). cmake 3.14+.
- `arm64-linux`: an aarch64 host, or a cross toolchain with a matching sysroot;
  running the test suite then requires either the aarch64 host or a qemu-user
  runner (note in the report if tests were run under emulation — that is weaker
  evidence than native).

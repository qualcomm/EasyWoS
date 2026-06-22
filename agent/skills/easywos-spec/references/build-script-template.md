# build_and_compare.bat Template

ARM64-only build and test execution script.

> **Shared between flows.** This template is identical for the assembly flow
> ([unit-test-workflow.md](unit-test-workflow.md)) and the intrinsics flow
> ([unit-test-workflow-intrinsics.md](unit-test-workflow-intrinsics.md)).
> Only the test binary's name (`test_<name>.exe`) varies — the build/run
> sequence and error handling are common.

```batch
@echo off
setlocal

set OUTDIR=%~dp0

echo === Building ARM64 unit tests ===
cmake -S %OUTDIR% -B %OUTDIR%build -A ARM64
if errorlevel 1 goto :cmake_fail
cmake --build %OUTDIR%build --config Release
if errorlevel 1 goto :build_fail

echo.
echo === Running ARM64 tests ===
%OUTDIR%build\Release\test_<name>.exe
if errorlevel 1 goto :test_fail

echo.
echo PASS: All ARM64 tests passed
exit /b 0

:cmake_fail
echo ERROR: CMake configure failed
exit /b 1
:build_fail
echo ERROR: Build failed
exit /b 1
:test_fail
echo ERROR: Tests failed
exit /b 1
```

Replace `<name>` with the actual project name (e.g., `compute_sum`).

## Prerequisites

- Windows ARM64 machine (native execution, no emulation) **or** aarch64 Linux host (intrinsics flow only — the asm flow's `armasm64` is Windows-specific).
- MSVC toolchain with ARM64 build tools (Visual Studio 2019+).
- `armasm64` is required only for the assembly flow; it ships with MSVC ARM64.
- CMake 3.14+ (for FetchContent).
- Internet access during first build (to fetch Google Test).

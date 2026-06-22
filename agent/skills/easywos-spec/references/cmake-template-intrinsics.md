# CMakeLists.txt Template — Intrinsics Variant

ARM64-only build for C/intrinsic kernels using FetchContent gtest. Sister
template of [cmake-template.md](cmake-template.md). Use this when leaf-skill
outputs are `*.c` files containing NEON / ARMv8 intrinsics, not hand-written
`*.asm`.

```cmake
cmake_minimum_required(VERSION 3.14)
project(<name>_porting_test LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)

# --- Sanity: this template targets ARM64 native ------------------------------
if(NOT CMAKE_SYSTEM_PROCESSOR MATCHES "^(arm64|ARM64|aarch64)$" AND
   NOT CMAKE_GENERATOR_PLATFORM MATCHES "^(arm64|ARM64)$")
    message(WARNING
        "Generator platform is '${CMAKE_GENERATOR_PLATFORM}'. "
        "These tests require ARM64 (configure with -A ARM64 on Windows, or run on aarch64 Linux).")
endif()

# --- Compiler flags for ARMv8 NEON + CRC32 -----------------------------------
if(MSVC)
    # MSVC for ARM64 enables NEON / CRC32 intrinsics by default; nothing extra.
    add_compile_options(/W3 /permissive-)
else()
    add_compile_options(-march=armv8-a+crc -O2 -Wall -Wextra)
endif()

# --- Google Test via FetchContent --------------------------------------------
include(FetchContent)
FetchContent_Declare(
    googletest
    GIT_REPOSITORY https://github.com/google/googletest.git
    GIT_TAG        v1.14.0
)
set(gtest_force_shared_crt ON CACHE BOOL "" FORCE)
FetchContent_MakeAvailable(googletest)

enable_testing()

# --- Kernel library (the C unit under test) ----------------------------------
# test_kernels_<arch>.c is a clean-C-ABI extraction of the SIMD bodies from
# the leaf-skill output files. It has no project dependencies, so the test
# binary compiles in isolation.
add_library(<name>_kernels STATIC test_kernels_<arch>.c)
target_include_directories(<name>_kernels PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})

# --- Test binary -------------------------------------------------------------
add_executable(test_<name> test_<name>.cpp)
target_link_libraries(test_<name>
    PRIVATE
        <name>_kernels
        GTest::gtest
        GTest::gtest_main)

include(GoogleTest)
gtest_discover_tests(test_<name>)

# --- Convenience target ------------------------------------------------------
# `cmake --build build --target run_<name>_tests` builds and runs in one shot.
add_custom_target(run_<name>_tests
    COMMAND $<TARGET_FILE:test_<name>>
    DEPENDS test_<name>
    USES_TERMINAL)
```

Replace all `<name>` placeholders with the project name (e.g., `zlibng_neon`),
and `<arch>` with the target architecture suffix on the kernel file
(e.g., `neon`, `armv8`, `sve`).

## Key differences vs the assembly template

| Template line | Assembly variant | Intrinsics variant |
|---|---|---|
| Languages | `LANGUAGES CXX` only | `LANGUAGES C CXX` (need C for the kernel file) |
| Compiler flags | none beyond ARM64 default | `-march=armv8-a+crc` for non-MSVC |
| Assembler step | `find_program(ARMASM64 …)` + `add_custom_command` invoking `armasm64` | (deleted — none needed) |
| Unit-under-test | `${ASM_OBJ}` linked directly into the test executable | `add_library(<name>_kernels STATIC test_kernels_<arch>.c)` then linked into the test executable |
| `set_source_files_properties(${ASM_OBJ} … EXTERNAL_OBJECT)` | required to convince CMake to link the asm-produced .obj | not needed |

## Prerequisites

- Windows ARM64 host (native; no x64 emulation) **or** aarch64 Linux host.
- MSVC toolchain with ARM64 cross-compiler (Visual Studio 2019+ with
  ARM64 build tools) **or** GCC/Clang with `-march=armv8-a+crc` support.
- CMake 3.14+ (for FetchContent).
- Internet access during first build (gtest fetch from GitHub).

## Pitfalls

- **`gtest_discover_tests` post-build step requires PowerShell.** On a stripped
  Windows install, you may see `'pwsh.exe' is not recognized`. Tests still
  build and run via the binary directly; only `ctest` discovery is affected.
- **`<arm_acle.h>` is not present in MSVC ARM64.** The kernel file MUST use
  the conditional include from
  [unit-test-workflow-intrinsics.md](unit-test-workflow-intrinsics.md)
  (MSVC compatibility shim section), or the build will fail at the first
  `#include`.
- **Don't try to link the leaf-skill output (`.c` files inside the project
  source tree) directly into the test binary.** They depend on project headers
  the test doesn't have. Always go through the `test_kernels_<arch>.c` seam.

# CMakeLists.txt Template

ARM64-only build using armasm64 via `add_custom_command` and Google Test via FetchContent.

> **Asm-only template.** This is for the assembly flow (leaf-skill outputs are
> `*.asm`). For C/intrinsic kernels see
> [cmake-template-intrinsics.md](cmake-template-intrinsics.md). Selection rule:
> [../SKILL.md](../SKILL.md) Section 7.3.

```cmake
cmake_minimum_required(VERSION 3.14)
project(<name>_porting_test LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)

include(FetchContent)
FetchContent_Declare(
    googletest
    GIT_REPOSITORY https://github.com/google/googletest.git
    GIT_TAG v1.14.0
)
set(gtest_force_shared_crt ON CACHE BOOL "" FORCE)
FetchContent_MakeAvailable(googletest)

enable_testing()

set(ASM_SOURCE ${CMAKE_CURRENT_SOURCE_DIR}/<name>_arm64.asm)
set(ASM_OBJ ${CMAKE_CURRENT_BINARY_DIR}/<name>_arm64.obj)

find_program(ARMASM64 armasm64
    HINTS "$ENV{VCToolsInstallDir}/bin/Hostarm64/arm64"
          "$ENV{VCToolsInstallDir}/bin/Hostx64/arm64"
)
if(NOT ARMASM64)
    set(ARMASM64 armasm64)
endif()

add_custom_command(
    OUTPUT ${ASM_OBJ}
    COMMAND ${ARMASM64} -o ${ASM_OBJ} ${ASM_SOURCE}
    DEPENDS ${ASM_SOURCE}
    COMMENT "Assembling ARM64: <name>_arm64.asm"
)

add_executable(test_<name>
    test_<name>.cpp
    ${ASM_OBJ}
)

set_source_files_properties(${ASM_OBJ} PROPERTIES
    EXTERNAL_OBJECT TRUE
    GENERATED TRUE
)

target_link_libraries(test_<name> GTest::gtest_main)

include(GoogleTest)
gtest_discover_tests(test_<name>)
```

Replace all `<name>` placeholders with the actual project name (e.g., `compute_sum`).

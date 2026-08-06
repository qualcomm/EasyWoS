---
name: enable-windows-arm64
description: Detect a project's build system and modify its build files to add a Windows ARM64 build configuration. Use when the user wants to "enable ARM64", "add ARM64 support", "support Windows on ARM"/"Windows on ARM64"/"WoA", "build for ARM64", "make project ARM64 compatible", "add an ARM64 target/platform/preset", or "cross-compile for ARM64". Detects and edits cmake (CMakePresets.json), visual_studio (.vcxproj/.sln), make (Makefile), ninja (build.ninja), autotools (configure.ac/Makefile.am), bazel (BUILD/WORKSPACE), qmake (.pro/.pri), and scons (SConstruct/SConscript). Also covers porting a Linux-only make/GCC project to a Windows-ARM64 clang build (GCC-only headers, missing make, clang target triple, +crypto feature flag, POSIX/libc compat shim) — see references/linux-make-to-windows-clang.md.
author: Hao Zeng
---

# Overview

The skill automatically detects and enables Windows ARM64 compilation support in software projects. For a detailed case study of enabling ARM64 support in Visual Studio projects, see [references/case-study-activemq-cpp.md](references/case-study-activemq-cpp.md).

**Two situations, handled differently:**
1. **The project already builds on Windows** (has CMake / a `.vcxproj`, MSVC-buildable). Add an ARM64 configuration/preset — the common case, covered by the scripts below.
2. **The project only builds on Linux with make/GCC** (GNU `Makefile`/autotools, `#include <x86intrin.h>`/`<cpuid.h>`/`<sched.h>`, no MSVC project files, no `make`/`gcc` on the Windows host). Adding `-march=armv8-a` to the Makefile does **not** work — the Makefile does not even run, and the source pulls in GCC/Linux-only headers and libc functions. Drive the VS-bundled **clang** directly and add a small Windows compat layer. See **[references/linux-make-to-windows-clang.md](references/linux-make-to-windows-clang.md)** for the full, verified checklist.

## Quick Start

```bash
# Enable ARM64 support in a project
python scripts/enable_arm64_workflow.py /path/to/project

# Without creating backups (use with version control)
python scripts/enable_arm64_workflow.py /path/to/project --no-backup
```

## What It Does

1. **Detects build system** with priority: cmake > visual_studio > make > ninja > autotools > bazel > qmake > scons
2. **Checks existing support** - Reports if ARM64 is already enabled
3. **Modifies build files** - Adds ARM64 configurations if needed

## What Gets Added

### CMake

Adds a `windows-arm64` configure preset to `CMakePresets.json`. This is non-intrusive and does not modify `CMakeLists.txt`.

**Note:** CMake projects typically work out-of-the-box for ARM64 once the preset is added.

```json
{
  "name": "windows-arm64",
  "displayName": "Windows ARM64",
  "architecture": {
      "value": "ARM64",
      "strategy": "set"
  },
  "cacheVariables": {
      "CMAKE_BUILD_TYPE": "Release"
  }
}
```

### Visual Studio
- Adds ARM64 platform to ProjectConfigurations
- Creates ARM64 PropertyGroups for Debug/Release
- **Clones ItemDefinitionGroups** (compiler/linker settings) - CRITICAL
- Updates .sln with ARM64 configurations

**Important:** Visual Studio projects require careful handling:
1. **ItemDefinitionGroups must be cloned** - Contains compiler flags, include paths, library paths
2. **Dependency paths may need adjustment** - e.g., `$(APR_DIST)\$(PlatformName)\include` → `$(APR_DIST)\include\apr-2`
3. **External dependencies must be built for ARM64** - APR, OpenSSL, Boost, etc.

### Make

For a Makefile that **already builds on Windows** (e.g. via mingw/clang on PATH),
add an ARM64 branch:

```makefile
ifeq ($(OS),Windows_NT)
    ifeq ($(PROCESSOR_ARCHITECTURE),ARM64)
        CFLAGS += -DWINDOWS_ARM64 -march=armv8-a
    endif
endif
```

> ⚠️ **A GNU/Linux-only Makefile does NOT build this way on Windows ARM64.** If
> the project is Linux/GCC-only (no `make` on the Windows host, source uses
> `<x86intrin.h>`/`<cpuid.h>`/`<sched.h>`, GCC dialect), this Make edit is a
> no-op — there is no `make` to run it, and even if there were, `cl`/GCC can't
> build the source. Do not rely on `$(PROCESSOR_ARCHITECTURE)` either: the
> Windows-ARM64 dev shell runs under x64 emulation and reports `AMD64`.
> Instead drive the VS-bundled **clang** (`--target=aarch64-pc-windows-msvc
> -march=armv8-a+crypto`) directly and add a Windows compat layer
> (`-include win_compat.h` + empty `winshim/` stub headers), then optionally add
> a `CMakeLists.txt`. Full verified procedure:
> **[references/linux-make-to-windows-clang.md](references/linux-make-to-windows-clang.md)**.

## Supported Build Systems

| Build System | Files Modified | Priority |
|--------------|----------------|----------|
| CMake | CMakePresets.json | 1 (Highest) |
| Visual Studio | .vcxproj, .sln | 2 |
| Make | Makefile | 3 |
| Ninja | build.ninja | 4 |
| Autotools | configure.ac, Makefile.am | 5 |
| Bazel | BUILD, WORKSPACE | 6 |
| QMake | .pro, .pri | 7 |
| SCons | SConstruct, SConscript | 8 |

## Individual Scripts

For fine-grained control, use individual scripts:

```bash
# Detect only
python scripts/detect_build_system.py /path/to/project

# Check only
python scripts/check_arm64_support.py cmake CMakeLists.txt

# Enable specific file
python scripts/enable_cmake_arm64.py CMakeLists.txt
python scripts/enable_visual_studio_arm64.py project.vcxproj
python scripts/enable_make_arm64.py Makefile
```

## Common Scenarios

**Multi-build system project**: Only the highest priority system is modified.

**Already has ARM64**: Script reports existing support and exits.

**Multiple build files**: All files of the detected build system are modified.

## Backup Files

By default, `.bak` files are created for build systems that require file modification (Visual Studio, Make, etc.). CMake support connects via `CMakePresets.json` and does not require backups of source files.

Restore others with:
```bash
mv Makefile.bak Makefile
```

## Troubleshooting

**No build system detected**: Ensure build files exist and contain valid syntax.

**Modification failed**: Check file permissions and syntax validity.

**Wrong build system selected**: Use individual scripts to target specific files.

### GCC/Linux Source on Windows ARM64 (clang path)

**`make` / `gcc` not found, or the Makefile "runs" but nothing is built for ARM64**:
- The project is Linux/GCC-only. Don't patch the Makefile — build with the
  VS-bundled clang directly. See
  [references/linux-make-to-windows-clang.md](references/linux-make-to-windows-clang.md).

**`fatal error: 'x86intrin.h' file not found`** (or `cpuid.h`, `emmintrin.h`):
- x86-only compiler headers. Arch-guard the include and provide a NEON path:
  `#if defined(_M_ARM64) || defined(_M_ARM64EC) || defined(__aarch64__) ... #else #include <x86intrin.h> #endif`.

**`fatal error: 'sched.h' file not found`** (or `unistd.h`, `netinet/in.h`):
- Linux OS headers. Add empty stub headers under `winshim/` + `-Iwinshim`, and
  supply the real symbols via `-include win_compat.h` (`sched_setaffinity`→
  `SetThreadAffinityMask`, `ntohl`→`_byteswap_ulong`, `ftime`→`_ftime`, a compact
  `getopt`, `strcasecmp`→`_stricmp`). Don't stub headers clang actually ships
  (e.g. `<sys/timeb.h>`).

**`always_inline function 'vmull_p64' requires target feature 'aes'`** (or `vaes*`, `vsha*`):
- PMULL/AES/SHA are gated behind `+crypto`. Add `-march=armv8-a+crypto`. These
  are baseline on Windows ARM64 — enable at compile time, no runtime guard needed.

**`argument to '__builtin_neon_vgetq_lane_i64' must be a constant integer`**:
- A NEON lane index came from a runtime value. Lane selection must be compile-time
  constant — use fixed-lane macros, not a computed index (see the CRC32 PMULL spec
  in `sse-avx-to-neon`).

### Visual Studio Specific Issues

**Build fails with "cannot open include file"**:
- Check dependency paths in ItemDefinitionGroup
- Verify environment variables point to ARM64 versions
- Example: `$env:APR_DIST = "C:\apr-arm64"`

**Linker errors (LNK1181, LNK2001)**:
- Ensure all libraries are built for ARM64
- Check AdditionalLibraryDirectories paths
- Verify library names (e.g., `libapr-2.lib` not `libapr-1.lib`)

**Platform 'ARM64' not found**:
- Install Visual Studio 2022 ARM64 build tools
- Go to: Visual Studio Installer → Modify → Individual Components
- Search: "ARM64" and install "MSVC v143 - VS 2022 C++ ARM64 build tools"

**ItemDefinitionGroup missing**:
- Re-run the script (older versions didn't clone ItemDefinitionGroups)
- Manually verify: Open .vcxproj and search for `Condition="'$(Configuration)|$(Platform)'=='Release|ARM64'"`
- Should appear in both `<PropertyGroup>` AND `<ItemDefinitionGroup>`

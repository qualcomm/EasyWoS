---
name: enable-windows-arm64
description: Guide for enabling Windows ARM64 support in software projects. This skill will be used when users want to "enable ARM64", "add ARM64 support", "support Windows on ARM", or "make project ARM64 compatible". It detects build systems (cmake, visual_studio, autotools, bazel, make, ninja, qmake, scons) with priority ordering, checks if ARM64 is already supported, and modifies build files to add ARM64 configurations.
---

# Enable Windows ARM64 Support

Automatically detect and enable Windows ARM64 compilation support in software projects.

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

**Real-world example:** ActiveMQ-CPP required:
- APR 2.x built for ARM64
- Path adjustments for APR headers
- Environment variable: `$env:APR_DIST = "C:\path\to\apr-arm64"`

### Make
```makefile
ifeq ($(OS),Windows_NT)
    ifeq ($(PROCESSOR_ARCHITECTURE),ARM64)
        CFLAGS += -DWINDOWS_ARM64 -march=armv8-a
    endif
endif
```

See [references/examples.md](references/examples.md) for all build systems.

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

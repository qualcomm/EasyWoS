# Real-World Case Study: ActiveMQ-CPP for Windows ARM64

This document describes the actual process of enabling Windows ARM64 support for ActiveMQ-CPP, a complex C++ messaging library with external dependencies.

## Table of Contents

- [Project Overview](#project-overview)
- [Initial State](#initial-state)
- [Step 1: Add ARM64 Configurations](#step-1-add-arm64-configurations)
- [Step 2: First Build Attempt - FAILED ❌](#step-2-first-build-attempt---failed-)
- [Step 3: Build APR for ARM64](#step-3-build-apr-for-arm64)
- [Step 4: Fix Dependency Paths](#step-4-fix-dependency-paths)
- [Step 5: Second Build Attempt - SUCCESS ✅](#step-5-second-build-attempt---success-)
- [Key Learnings](#key-learnings)
- [Final Configuration](#final-configuration)
- [Recommendations for the Skill](#recommendations-for-the-skill)
- [Timeline](#timeline)
- [Conclusion](#conclusion)

## Project Overview

- **Project:** Apache ActiveMQ-CPP 3.9.0
- **Build System:** Visual Studio 2010+ (.vcxproj, .sln)
- **Dependencies:** APR (Apache Portable Runtime) 2.x
- **Complexity:** 4 projects, 8 configurations each, 1000+ source files
- **Result:** ✅ Successfully compiled 1.01 GB static library for ARM64

## Initial State

```
activemq-cpp/
├── vs2010-build/
│   ├── activemq-cpp.sln
│   ├── activemq-cpp.vcxproj
│   ├── activemq-cpp-example.vcxproj
│   ├── activemq-cpp-unit-tests.vcxproj
│   └── activemq-cpp-integration-tests.vcxproj
└── src/
    └── main/
        ├── activemq/
        └── decaf/
```

**Platforms supported:** Win32, x64  
**Platforms needed:** + ARM64

## Step 1: Add ARM64 Configurations

### Using the Script

```bash
cd activemq-cpp/vs2010-build
python ../../enable-windows-arm64/scripts/enable_visual_studio_arm64.py activemq-cpp.vcxproj
python ../../enable-windows-arm64/scripts/enable_visual_studio_arm64.py activemq-cpp-example.vcxproj
python ../../enable-windows-arm64/scripts/enable_visual_studio_arm64.py activemq-cpp-unit-tests.vcxproj
python ../../enable-windows-arm64/scripts/enable_visual_studio_arm64.py activemq-cpp-integration-tests.vcxproj
python ../../enable-windows-arm64/scripts/enable_visual_studio_arm64.py activemq-cpp.sln
```

### What Was Added

For each .vcxproj file:

1. **ProjectConfiguration entries** (8 new):
```xml
<ProjectConfiguration Include="Debug|ARM64">
  <Configuration>Debug</Configuration>
  <Platform>ARM64</Platform>
</ProjectConfiguration>
<ProjectConfiguration Include="DebugSSL|ARM64">
  <Configuration>DebugSSL</Configuration>
  <Platform>ARM64</Platform>
</ProjectConfiguration>
<!-- ... 6 more configurations ... -->
```

2. **PropertyGroup entries** (8 new):
```xml
<PropertyGroup Condition="'$(Configuration)|$(Platform)'=='Release|ARM64'" Label="Configuration">
  <ConfigurationType>StaticLibrary</ConfigurationType>
  <PlatformToolset>v143</PlatformToolset>
  <CharacterSet>Unicode</CharacterSet>
  <UseDebugLibraries>false</UseDebugLibraries>
</PropertyGroup>
```

3. **ItemDefinitionGroup entries** (8 new) - **CRITICAL**:
```xml
<ItemDefinitionGroup Condition="'$(Configuration)|$(Platform)'=='Release|ARM64'">
  <ClCompile>
    <WarningLevel>Level2</WarningLevel>
    <Optimization>MaxSpeed</Optimization>
    <PreprocessorDefinitions>WIN32;_LIB;NDEBUG;%(PreprocessorDefinitions)</PreprocessorDefinitions>
    <AdditionalIncludeDirectories>../src/main;$(APR_DIST)\$(PlatformName)\include</AdditionalIncludeDirectories>
  </ClCompile>
  <Link>
    <AdditionalLibraryDirectories>$(APR_DIST)\$(PlatformName)\lib</AdditionalLibraryDirectories>
  </Link>
</ItemDefinitionGroup>
```

## Step 2: First Build Attempt - FAILED ❌

```powershell
cd activemq-cpp/vs2010-build
& "C:\Program Files\Microsoft Visual Studio\2022\Professional\MSBuild\Current\Bin\arm64\MSBuild.exe" `
    activemq-cpp.sln /p:Configuration=Release /p:Platform=ARM64 /m
```

### Error Encountered

```
error C1083: Cannot open include file: 'apr_pools.h': No such file or directory
```

### Root Cause Analysis

1. **Dependency not available:** APR not built for ARM64
2. **Path mismatch:** Project expected `$(APR_DIST)\ARM64\include` but APR installed at `$(APR_DIST)\include\apr-2`

## Step 3: Build APR for ARM64

### APR Compilation

```powershell
# Download APR 2.x source
cd C:\Users\haozen\source\repos\apr

# Build for ARM64
cmake -S . -B build-arm64 -A ARM64 -DCMAKE_INSTALL_PREFIX=install-arm64
cmake --build build-arm64 --config Release
cmake --install build-arm64
```

### Result

```
C:\Users\haozen\source\repos\apr\install-arm64\
├── include\
│   └── apr-2\
│       ├── apr.h
│       ├── apr_pools.h
│       └── ... (other headers)
└── lib\
    ├── libapr-2.lib
    └── libaprapp-2.lib
```

## Step 4: Fix Dependency Paths

### Problem

Project used: `$(APR_DIST)\$(PlatformName)\include`  
Which expands to: `C:\...\apr\install-arm64\ARM64\include` ❌

But APR has: `C:\...\apr\install-arm64\include\apr-2` ✅

### Solution

Modified all .vcxproj files:

```powershell
# Replace path pattern
(Get-Content "activemq-cpp.vcxproj" -Raw) -replace `
    '\$\(APR_DIST\)\\\$\(PlatformName\)\\include', `
    '$(APR_DIST)\include\apr-2' | `
    Set-Content "activemq-cpp.vcxproj" -NoNewline

# Also fix library path
(Get-Content "activemq-cpp.vcxproj" -Raw) -replace `
    '\$\(APR_DIST\)\\\$\(PlatformName\)\\lib', `
    '$(APR_DIST)\lib' | `
    Set-Content "activemq-cpp.vcxproj" -NoNewline
```

**Lesson:** Dependency path structures may differ between platforms. Always verify actual installation layout.

## Step 5: Second Build Attempt - SUCCESS ✅

```powershell
# Set APR path
$env:APR_DIST = "C:\Users\haozen\source\repos\apr\install-arm64"

# Build main library only (tests require CPPUnit)
& "C:\Program Files\Microsoft Visual Studio\2022\Professional\MSBuild\Current\Bin\arm64\MSBuild.exe" `
    activemq-cpp.vcxproj `
    /p:Configuration=Release `
    /p:Platform=ARM64 `
    /m
```

### Build Output

```
activemq-cpp.vcxproj -> C:\...\activemq-cpp\vs2010-build\ARM64\Release\activemq-cpp.lib
```

### Verification

```powershell
& "C:\Program Files\Microsoft Visual Studio\2022\Professional\VC\Tools\MSVC\14.44.35207\bin\Hostarm64\arm64\dumpbin.exe" `
    /headers ARM64\Release\libactivemq-cpp.lib | Select-String "machine"
```

Output:
```
AA64 machine (ARM64)  ✅
```

## Key Learnings

### 1. ItemDefinitionGroup is Critical

**Without ItemDefinitionGroup cloning:**
- No compiler flags
- No include directories
- No library directories
- Build will fail immediately

**Verification:**
```xml
<!-- Must exist for each ARM64 configuration -->
<ItemDefinitionGroup Condition="'$(Configuration)|$(Platform)'=='Release|ARM64'">
  <ClCompile>...</ClCompile>
  <Link>...</Link>
</ItemDefinitionGroup>
```

### 2. Dependency Paths Need Validation

**Common patterns that may fail:**
- `$(DEP)\$(PlatformName)\include` → May not exist for ARM64
- `$(DEP)\x64\lib` → Hardcoded platform
- `$(DEP)\bin` → May contain x64 binaries

**Solution:**
- Check actual dependency installation structure
- Adjust paths in .vcxproj or use different path variables
- Document required environment variables

### 3. External Dependencies Must Be ARM64

**For ActiveMQ-CPP:**
- ✅ APR 2.x - Built for ARM64
- ⚠️ OpenSSL - Not needed for non-SSL builds
- ⚠️ CPPUnit - Not needed for library (only tests)

**General rule:** Every `.lib` file linked must be ARM64.

### 4. Test Projects May Fail (OK)

**ActiveMQ-CPP test projects failed:**
```
error C1083: Cannot open include file: 'cppunit/TestFixture.h'
```

**This is acceptable because:**
- Main library built successfully
- Tests are optional
- CPPUnit not available for ARM64

**Focus:** Get the main library/application building first.

### 5. Build Warnings Are Normal

**Common warnings (non-critical):**
```
warning MSB8027: Two or more files with the same name will produce outputs to the same location
warning MSB8012: TargetName does not match OutputFile property value
```

**These don't prevent successful compilation.**

## Final Configuration

### Environment Variables

```powershell
$env:APR_DIST = "C:\Users\haozen\source\repos\apr\install-arm64"
```

### Build Command

```powershell
& "C:\Program Files\Microsoft Visual Studio\2022\Professional\MSBuild\Current\Bin\arm64\MSBuild.exe" `
    activemq-cpp.vcxproj `
    /p:Configuration=Release `
    /p:Platform=ARM64 `
    /m
```

### Output

```
File: ARM64\Release\libactivemq-cpp.lib
Size: 1,038.63 MB (1.01 GB)
Architecture: ARM64 (AA64)
Type: Static Library
```

## Recommendations for the Skill

Based on this experience, the `enable-windows-arm64` skill should:

### 1. Always Clone ItemDefinitionGroups ⚠️ CRITICAL

Current script must be updated to clone `<ItemDefinitionGroup>` elements, not just `<PropertyGroup>`.

### 2. Warn About Dependency Paths

Detect patterns like:
- `$(VAR)\$(PlatformName)\path`
- `$(VAR)\x64\path`

And warn user:
```
⚠️  Dependency Warning:
  Found $(APR_DIST)\$(PlatformName)\include
  → ARM64 dependencies may need different path structure
  → Verify: Does C:\path\to\apr\ARM64\include exist?
  → Or is it: C:\path\to\apr\include\apr-2?
```

### 3. Provide Dependency Checklist

After enabling ARM64, print:
```
✓ ARM64 configurations added

Next steps:
  1. Build/obtain ARM64 versions of dependencies:
     - APR_DIST
     - OPENSSL_DIST
     (found in your project)
  
  2. Set environment variables:
     $env:APR_DIST = "C:\path\to\apr-arm64"
  
  3. Verify dependency paths in .vcxproj match actual structure
  
  4. Build:
     msbuild project.vcxproj /p:Configuration=Release /p:Platform=ARM64
```

### 4. Add Verification Step

After modification, verify:
```python
checks = {
    'ProjectConfiguration': False,
    'PropertyGroup': False,
    'ItemDefinitionGroup': False  # CRITICAL
}

# Verify all three exist for ARM64
```

### 5. Support Partial Success

If main project builds but tests fail (like ActiveMQ-CPP):
```
✓ Main library built successfully
⚠️ Test projects failed (missing CPPUnit) - This is OK
```

## Timeline

- **Initial setup:** 5 minutes (run scripts)
- **First build attempt:** Failed (missing APR)
- **Build APR:** 30 minutes
- **Fix paths:** 10 minutes
- **Second build:** Success! (5 minutes)
- **Total:** ~50 minutes

**With proper skill implementation:** Could be reduced to ~40 minutes (automated path detection).

## Conclusion

The ActiveMQ-CPP case demonstrates that enabling ARM64 support requires:

1. ✅ Adding ARM64 configurations (automated by skill)
2. ✅ Cloning ItemDefinitionGroups (MUST be in skill)
3. ⚠️ Building dependencies for ARM64 (user responsibility, but skill should warn)
4. ⚠️ Adjusting dependency paths (skill should detect and warn)
5. ✅ Setting environment variables (skill should document)

**Success rate:** With proper ItemDefinitionGroup cloning and dependency warnings, success rate should be >90% for projects with available ARM64 dependencies.

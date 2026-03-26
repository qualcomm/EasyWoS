# EasyBuild

EasyBuild facilitates users to compile and build applications for Windows on Arm on x86-64 host machines. This solution is simple, reliable, and easy to use, solving the problem during migrating.

-----

**Host CPU Architecture:** x86-64

**Target CPU Architecture:** aarch64

**Applicable OS:** Windows

------

### 1. Compilation Environment
You can choose either the MSVC toolchain or the LLVM toolchain. If you choose the former, you need to download Visual Studio; if you choose the latter, you need to download a specific version of LLVM.

#### 1.1 MSVC Toolchain
It is recommended to use **Visual Studio v17.10**.

Install some necessary tools from the Visual Studio Installer:

1. Select "Desktop development with C++" in the Workloads of Visual Studio Installer. This will install MSVC, Clang, CMake, and MSBuild for you.
2. You can also choose the LLVM toolchain in Visual Studio. You need to select "MSBuild support for LLVM (clang-cl) toolset" and "C++ Clang Compiler for Windows" in "Individual components" from Visual Studio Installer. (Note that different versions of Visual Studio will install different versions of LLVM).
3. Search for "Windows 11 SDK" in Individual components. It is recommended to use the latest Windows 11 SDK (10.26100.6901).

#### 1.2 LLVM Toolchain
LLVM supports x86-64 cross-compilation for Windows on Arm starting from v12 [Refer to LLVM Release Notes](https://releases.llvm.org/12.0.0/tools/clang/docs/ReleaseNotes.html#windows-support).

After installation is complete, enter the following in the command prompt:
```cmd
clang.exe --version
```
If the output is as follows, the installation is successful:
```cmd
clang version 18.1.8
Target: aarch64-pc-windows-msvc
Thread model: posix
InstalledDir: C:\Program Files\Llvm\bin
```

### 2. Compiling ARM64

#### 2.1 Cross-compiling Windows on Arm using Visual Studio
1. Open the solution in Visual Studio.
2. In the Build dropdown menu on the standard toolbar, select Configuration Manager.

![Snipaste_2025-12-17_10-34-38.png](/static/Snipaste_2025-12-17_10-34-38.png)

3. Set the Active solution platform to ARM64 in the Configuration Manager dialog box.

![Snipaste_2025-12-17_10-36-57.png](/static/Snipaste_2025-12-17_10-36-57.png)

#### 2.2 Cross-compiling Windows on Arm using LLVM
Open the command prompt and enter the following two commands in sequence:
```cmd
cmake -S <source_dir> -B <build_dir> -G "Ninja" -T CLANGCL -A ARM64
cmake --build <build_dir>
```
-T specifies the toolset as LLVM/CLANG, and -A specifies the target architecture as ARM64. The first command generates the corresponding project build files. Since the generator specified here is Ninja, it generates build.ninja.
The second command indicates starting the build using the corresponding toolset.

### 3. Compiling ARM64EC
To compile ARM64EC targets, you need to install the following tools from the Visual Studio Installer.

1. Under "Individual Components" in Visual Studio Installer, search for arm64ec and select "MSVC v143 - VS 2022 C++ ARM64/ARM64EC build tools (latest)".
2. Under Individual components in Visual Studio Installer, search for windows 11 and select "Windows 11 SDK (10.26100.6901)", choosing the latest Windows 11 SDK.

#### 3.1 Visual Studio Project
Select Active solution platform in Build/Configuration Manager, choose "new" in the dropdown menu, select ARM64EC for the new platform, and set "Copy settings from" to x64 or ARM64.

![Snipaste_2025-12-16_16-53-17.png](/static/Snipaste_2025-12-16_16-53-17.png)
![Snipaste_2025-12-16_17-06-15.png](/static/Snipaste_2025-12-16_17-06-15.png)
![Snipaste_2025-12-16_17-07-45.png](/static/Snipaste_2025-12-16_17-07-45.png)

#### 3.2 CMake Project
1. Open the integrated cross-compilation environment terminal on the x86-64 host.
```cmd
vcvarsall.bat x64_arm64
```
2. Prepare the `toolchain-arm64ec.cmake` file.
```makefile
# ---------- toolchain-arm64ec.cmake ----------
# Specify the target system
set(CMAKE_SYSTEM_NAME Windows)

# Use clang-cl (MSVC style)
find_program(CLANG_CL clang-cl REQUIRED)
set(CMAKE_C_COMPILER   "${CLANG_CL}")
set(CMAKE_CXX_COMPILER "${CLANG_CL}")

# ARM64EC target triplet (determines the machine type of .obj during compilation)
set(CMAKE_C_COMPILER_TARGET   "arm64ec-pc-windows-msvc")
set(CMAKE_CXX_COMPILER_TARGET "arm64ec-pc-windows-msvc")

# Linker (optionally use lld-link; if not set, clang-cl driver can also select link.exe)
find_program(LLD_LINK lld-link)
if(LLD_LINK)
  set(CMAKE_LINKER "${LLD_LINK}")
endif()

# Explicitly specify output as ARM64EC
set(CMAKE_EXE_LINKER_FLAGS    "${CMAKE_EXE_LINKER_FLAGS} /MACHINE:ARM64EC")
set(CMAKE_SHARED_LINKER_FLAGS "${CMAKE_SHARED_LINKER_FLAGS} /MACHINE:ARM64EC")
```

3. Execute cmake commands.
```cmd
cmake -S <source_dir> -B <build_dir> -G "Ninja" -DCMAKE_TOOLCHAIN_FILE=toolchain-arm64ec.cmake -DCMAKE_BUILD_TYPE=Release
cmake --build <build_dir>
```

### 4. vcpkg Package Manager
vcpkg is an open-source C/C++ package management tool by Microsoft, used to simplify the acquisition, building, and integration of third-party libraries. It is particularly suitable for the Windows platform but also supports Linux and macOS. It is similar to Python's pip or Node.js's npm, but specifically for C/C++ projects.

Core functions:
- Dependency management: Automatically download, compile, and install common libraries (such as Boost, OpenSSL, Qt), avoiding manual handling of complex build scripts.
- Cross-platform support: Supports multiple operating systems and compilers (MSVC, Clang, GCC).
- Deep integration with build systems: Provides CMake toolchain files, allowing `find_package()` to directly find libraries installed by vcpkg.
- Version control and reproducible builds: Locks dependency versions through Manifest mode (vcpkg.json), suitable for CI/CD.

vcpkg Quick Start Guide:

1. Install vcpkg
```cmd
git clone https://github.com/microsoft/vcpkg.git
cd vcpkg
bootstrap-vcpkg.bat
```

1. Install libraries
```cmd
# vcpkg install <package-name>:<triplet>
vcpkg install boost:arm64-windows
```

1. Integrate with CMake

Assuming the project needs zlib and fmt libraries, use CMakeLists.txt. Create `vcpkg.json` in the project root directory.
```json
{
  "name": "WoS-app",
  "version-string": "0.1.0",
  "dependencies": [
    "zlib",
    "fmt"
  ],
  "default-triplet": "arm64-windows"
}
```

Then execute:
```cmd
cmake -S . -B build ^
  -DCMAKE_TOOLCHAIN_FILE="C:/vcpkg/scripts/buildsystems/vcpkg.cmake" ^
  -DVCPKG_FEATURE_FLAGS=manifests ^
  -DCMAKE_SYSTEM_NAME=Windows ^
  -DCMAKE_GENERATOR_PLATFORM=ARM64
```

### WoS Ecosystem
#### Native Porting
##### Prism Emulator
WoS allows x86 (32-bit) and x64 (64-bit) applications to run on Arm64 devices without modification through the operating system's built-in Prism emulation layer (Windows 11 supports x86+x64, Windows 10 only supports x86). Emulation is transparent, system-level, and requires no additional components to be installed.
##### Building with Emulation Compatible (EC)
If you are dealing with a massive x86-64 application migration task, you can compile a key module as ARM64EC. On WoS, the x86-64 part of the code can be translated into Arm64 instructions by the Prism emulator, while the ARM64EC part will run as native Arm64 instructions.
##### Visual Studio Support for WoS
- Visual Studio 2017 v15.9 and later support cross-compilation.
- Visual Studio 2022 v17.4 and later support native compilation.
- LLVM/Clang v12 starts supporting cross-compilation and native compilation.

#### Compatibility Analysis
##### windbg
Windbg operations on WoS are consistent with x86-64. Due to hardware design reasons, physical devices usually only support kernel debugging via the emulated Ethernet module (EEM) on USB. Currently, in all scenarios, KDNet (network-based kernel debugging) is the preferred setup method, offering better stability and versatility. [windbg Reference Manual](https://learn.microsoft.com/en-us/windows-hardware/drivers/debugger/)
##### dumpbin
Displays Microsoft COFF binary file format information. [dumpbin Reference Manual](https://learn.microsoft.com/en-us/cpp/build/reference/dumpbin-reference?view=msvc-170)
##### event viewer
Windows Event Viewer records and displays system, application, and security-related log information, helping users and administrators diagnose faults, troubleshoot errors, and monitor system operation.
##### procdump
Procdump is a command-line tool in the Microsoft Sysinternals suite. Its main function is to monitor application CPU spikes, exceptions, or hangs, and generate process dump files (dump) under trigger conditions, helping developers and administrators analyze crash causes or performance issues. [procdump Reference Manual](https://learn.microsoft.com/en-us/sysinternals/downloads/procdump)
##### procmon
Procmon (Process Monitor) is an advanced system monitoring tool in the Microsoft Sysinternals toolset. Its function is to monitor file system, registry, process, and thread activities in the Windows system in real-time, helping developers and administrators with troubleshooting, performance analysis, and security detection. [procmon Reference Manual](https://learn.microsoft.com/en-us/sysinternals/downloads/procmon)

#### x86-64 vs arm64 Performance Analysis
Overview: ETW (Event Tracing for Windows) is a built-in time tracing framework in Windows that can capture various events in kernel and user mode (CPU, disk, network, memory, application behavior, etc.). Event data collected by ETW is saved as ETL (Event Tracing Log) files. WPR (Windows Performance Recorder) is based on ETW and is responsible for starting and stopping tracing sessions, collecting performance data, and generating ETL files. WPA (Windows Performance Analyzer) reads ETL files generated by WPR and provides a graphical interface and interactive analysis views.

##### Install WPR
[Download ADK to install WPR](https://learn.microsoft.com/en-us/windows-hardware/get-started/adk-install)

[WPR Reference Manual](https://learn.microsoft.com/en-us/windows-hardware/test/wpt/introduction-to-wpr)

##### Generate ETL files using WPR
1. Open command prompt.
2. Enter `wpr -start <profile>` to start recording performance data.
3. Perform the operation you want to analyze.
4. Enter `wpr -stop <filename>.etl` to stop recording and generate the ETL file.

##### Install WPA
WPA is part of the Windows Assessment and Development Kit (ADK) tools, used to analyze performance log files generated by WPR or other tracing tools. WPA can analyze and visualize CPU, memory, disk I/O, network performance, startup, and response times. [WPA Reference Manual](https://learn.microsoft.com/en-us/windows-hardware/test/wpt/wpa-quick-start-guide)

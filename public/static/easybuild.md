
# EasyBuild

EasyBuild方便用户在x86-64宿主机器编译构建适用于windows on arm的业务及应用，该方案简单可靠易用，解决用户迁移编译构建环境问题。

-----

<div style="background-color:#F6F5F8;padding: 16px;border-radius: 4px;">

**宿主CPU架构：** x86-64

**目标CPU架构：** aarch64

**适用操作系统：** windows

</div>

------

### 1. 编译环境
你可以选择MSVC工具链或者LLVM工具链。如果选择前者，需要下载visual studio，如果选择后者，需要下载特定版本的LLVM。
#### 1.1 MSVC工具链
推荐使用**Visual Studio v17.10**

从Visual Studio Installer安装一些必需的工具：

1. 在Visual Studio Installer的Workloads中选择Desktop development with C++。这将会为你安装MSVC，Clang，CMake，MSBuild。
2. 在Visual Studio中也可以选择LLVM工具链。你需要在Individual components中选择MSBuild support for LLVM(clang-cl) toolset以及C++ Clang Compiler for Windows。（注意，不同版本的visual studio会安装不同版本的LLVM）。
3. 在Individual components中搜索windows 11 SDK，推荐使用最新的windows 11 SDK (10.26100.6901)。
 

#### 1.2 LLVM工具链
LLVM从v12版本开始支持x86-64交叉编译windows on arm[参考LLVM Release Notes](https://releases.llvm.org/12.0.0/tools/clang/docs/ReleaseNotes.html#windows-support)。

安装完成之后，在command prompt输入
```cmd
clang.exe --version
```
输出如下内容则表示安装成功
```cmd
clang version 18.1.8
Target: aarch64-pc-windows-msvc
Thread model: posix
InstalledDir: C:\Program Files\Llvm\bin
```

### 2. 编译ARM64
#### 2.1 使用Visual Studio交叉编译Windows on Arm
1. 在 Visual Studio 中打开解决方案。
2. 在标准工具栏上Build下拉菜单中，选择 Configuration Manager。

![Snipaste_2025-12-17_10-34-38.png](/static/Snipaste_2025-12-17_10-34-38.png)

3. 在Configuration Manager对话框中将Active solution platform设置为ARM64。


![Snipaste_2025-12-17_10-36-57.png](/static/Snipaste_2025-12-17_10-36-57.png)

#### 2.2 使用LLVM交叉编译Windows on Arm
打开command prompt依次输入以下两条命令：
```cmd
cmake -S <source_dir> -B <build_dir> -G "Ninja" -T CLANGCL -A ARM64
cmake --build <build_dir>
```
-T将指定toolset为LLVM/CLANG，-A将指定目标架构为ARM64。第一行命令将生成对应的项目构建文件，这里指定的生成器是Ninja，所以生成的是build.ninja。
第二条命令表示使用对应的工具集开始构建。

### 3. 编译ARM64EC
为了编译ARM64EC目标，需要从Visual Studio Installer安装以下工具。

1. 在Visual Studio Installer中Individual components下面，搜索arm64ec，选择MSVC v143 -VS 2022 C++ ARM64/ARM64EC build tools(latest)。
2. 在Visual Studio Installer中Individual components下面，搜索windows 11，选择Windows 11 SDK (10.26100.6901)，选择最新的windows 11 SDK。

#### 3.1 Visual Studio项目
在Build/Cofiguration Manager中选择Active solution platform，在下拉菜单中选择new，new platform选择ARM64EC，Copy settings from设置为x64或ARM64。

![Snipaste_2025-12-16_16-53-17.png](/static/Snipaste_2025-12-16_16-53-17.png)
![Snipaste_2025-12-16_17-06-15.png](/static/Snipaste_2025-12-16_17-06-15.png)
![Snipaste_2025-12-16_17-07-45.png](/static/Snipaste_2025-12-16_17-07-45.png)

#### 3.2 CMake项目
1. 在x86-64主机上打开集成的交叉编译环境终端。
```cmd
vcvarsall.bat x64_arm64
```
2. 准备toolchain-arm64ec.cmake文件。
```makefile


# ---------- toolchain-arm64ec.cmake ----------
# 指定目标系统
set(CMAKE_SYSTEM_NAME Windows)

# 使用 clang-cl（MSVC 风格）
find_program(CLANG_CL clang-cl REQUIRED)
set(CMAKE_C_COMPILER   "${CLANG_CL}")
set(CMAKE_CXX_COMPILER "${CLANG_CL}")

# ARM64EC 目标三元组（编译阶段决定 .obj 的机器类型）
set(CMAKE_C_COMPILER_TARGET   "arm64ec-pc-windows-msvc")
set(CMAKE_CXX_COMPILER_TARGET "arm64ec-pc-windows-msvc")

# 链接器（可选使用 lld-link；不设置也可以由 clang-cl 驱动选择 link.exe）
find_program(LLD_LINK lld-link)
if(LLD_LINK)
  set(CMAKE_LINKER "${LLD_LINK}")
endif()

# 显式指定输出为 ARM64EC
set(CMAKE_EXE_LINKER_FLAGS    "${CMAKE_EXE_LINKER_FLAGS} /MACHINE:ARM64EC")
set(CMAKE_SHARED_LINKER_FLAGS "${CMAKE_SHARED_LINKER_FLAGS} /MACHINE:ARM64EC")
```

3. 执行cmake指令。
```cmd
cmake -S <source_dir> -B <build_dir> -G "Ninja" -DCMAKE_TOOLCHAIN_FILE=toolchain-arm64ec.cmake -DCMAKE_BUILD_TYPE=Release
cmake --build <build_dir>
```

### 4. vcpkg包管理工具
vcpkg 是微软开源的 C/C++ 包管理工具，用于简化第三方库的获取、构建和集成，特别适合 Windows 平台，但也支持 Linux 和 macOS。它的定位类似于 Python 的 pip 或 Node.js 的 npm，但专门针对 C/C++ 项目。

核心作用：
- 依赖管理：自动下载、编译并安装常用库（如 Boost、OpenSSL、Qt），避免手动处理复杂的构建脚本。
- 跨平台支持：支持多种操作系统和编译器（MSVC、Clang、GCC）。
- 与构建系统深度集成：提供CMake toolchain文件，使find_package()可以直接找到vcpkg安装的库。
- 版本控制与可复现构建：通过 Manifest模式（vcpkg.json）锁定依赖版本，适合CI/CD。

vcpkg快速入门指南：

1. 安装vcpkg 
```cmd
git clone https://github.com/microsoft/vcpkg.git
cd vcpkg
bootstrap-vcpkg.bat
```

2. 安装库
```cmd
# vcpkg install <package-name>:<triplet>
vcpkg install boost:arm64-windows
```

3. 与CMake集成

假设项目需要zlib和fmt两个库，使用CMakeLists.txt。在项目根目录创建vcpkg.json。
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

然后执行
```cmd
cmake -S . -B build ^
  -DCMAKE_TOOLCHAIN_FILE="C:/vcpkg/scripts/buildsystems/vcpkg.cmake" ^
  -DVCPKG_FEATURE_FLAGS=manifests ^
  -DCMAKE_SYSTEM_NAME=Windows ^
  -DCMAKE_GENERATOR_PLATFORM=ARM64
```

### WoS生态
#### 原生移植
##### Prism Emulator
WoS通过操作系统内置的Prism仿真层，使x86（32 位）与 x64（64 位）应用在Arm64设备上无需修改即可运行（Windows 11 支持 x86+x64，Windows 10 仅支持 x86）。仿真是透明的、系统级，无需额外安装组件。
##### 使用Emulation Compatible (EC)构建
如果你正在处理一个庞大的x86-64应用迁移任务，你可以将某一个关键模块编译为ARM64EC。在WoS上，x86-64部分的代码可以通过Prism模拟器翻译为Arm64的指令，而ARM64EC部分将以Arm64原生指令运行。
##### Visual Studio对于WoS的支持
- Visual Studio 2017 v15.9之后开始支持交叉编译
- Visual Studio 2022 v17.4之后开始支持原生编译
- LLVM/Clang v12开始支持交叉编译和原生编译

#### 兼容性分析
##### windbg
WoS上windbg操作和x86-64一致。由于硬件设计的原因，物理设备通常只支持通过USB上的仿真以太网模块(EEM)来进行内核调试。目前在所有场景下，KDNet（基于网络的内核调试）是首选的设置方式，稳定性和通用性更好。[windbg参考手册](https://learn.microsoft.com/en-us/windows-hardware/drivers/debugger/)
##### dumpbin
显示微软COFF二进制文件格式信息。[dumpbin参考手册](https://learn.microsoft.com/en-us/cpp/build/reference/dumpbin-reference?view=msvc-170)
##### event viewer
Windows的事件查看器(Event Viewer)作用是记录并展示系统、应用程序和安全相关的日志信息，帮助用户和管理员诊断故障、排查错误、监控系统运行情况。
##### procdump
procdump是微软Sysinternals套件中的一个命令行工具，主要作用是监控应用程序的CPU峰值、异常或挂起，并在触发条件下生成进程转储文件(dump)，帮助开发者和管理员分析崩溃原因或性能问题。[procdump参考手册](https://learn.microsoft.com/en-us/sysinternals/downloads/procdump)
##### procmon
Procmon（Process Monitor）是微软Sysinternals工具集中的一款高级系统监控工具，作用是实时监控Windows系统中的文件系统、注册表、进程和线程活动，帮助开发者和管理员进行故障排查、性能分析和安全检测。[procmon参考手册](https://learn.microsoft.com/en-us/sysinternals/downloads/procmon)

#### x86-64 vs arm64 性能分析
概述：ETW（Event Tracing for Windows）是Windows内置的时间追踪框架，它可以捕获内核和用户态的各种事件（CPU、磁盘、网络、内存、应用行为等）。ETW收集到的事件数据会保存为ETL（Event Tracing Log）文件。WPR（Windows Performance Recorder）基于ETW，负责启动和停止跟踪会话，收集性能数据并生成ETL文件。WPA(Windows Performance Analyzer)，读取WPR生成的ETL文件，提供图形化界面和交互式分析视图。

##### 安装WPR
[下载ADK以安装WPR](https://learn.microsoft.com/en-us/windows-hardware/get-started/adk-install)

[WPR参考手册](https://learn.microsoft.com/en-us/windows-hardware/test/wpt/introduction-to-wpr)

##### 使用WPR生成ETL文件
1. 打开command prompt。
2. 输入`wpr -start <profile>`开始记录性能数据。
3. 执行你要分析的操作。
4. 输入`wpr -stop <filename>.etl`停止记录并生成ETL文件。

##### 安装WPA
WPA是Windows Assessment and Development Kit (ADK)中的一部分工具，用于分析由WPR或者其他追踪工具生成的性能日志文件。WPA可以对CPU、内存、磁盘I/O、网络性能、启动和响应时间进行分析并进行可视化展示。[WPA参考手册](https://learn.microsoft.com/en-us/windows-hardware/test/wpt/wpa-quick-start-guide)












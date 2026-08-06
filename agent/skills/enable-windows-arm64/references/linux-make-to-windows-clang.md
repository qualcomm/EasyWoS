# Porting a Linux/make/GCC Project to a Windows-ARM64/clang Build

A large class of x86 open-source libraries have **only** a GNU `Makefile` (or
autotools) targeting Linux + GCC. On a Windows-on-ARM64 host these projects do
**not** build by "adding `-march=armv8-a`" — the Makefile itself does not run,
the compiler driver is different, and the source pulls in GCC/Linux-only headers
and libc functions that do not exist on Windows. The naive Make edit (append a
flag inside `ifeq ($(OS),Windows_NT)`) silently does nothing useful here, because
there is no `make` and no GCC on the target.

This reference is the checklist for that migration. It is grounded in a real,
verified port (intel/soft-crc: a GCC/Linux PCLMULQDQ CRC library built for
Windows ARM64 with the VS-bundled clang, its own test harness passing 1..300).

> **Decision gate — is this the Linux/make path?** If the project has a
> `Makefile`/`configure.ac` (not `CMakeLists.txt`/`.vcxproj`), no MSVC project
> files, uses `#include <x86intrin.h>` / `<cpuid.h>` / `<sched.h>` / `<unistd.h>`,
> and there is no `make`/`gcc` on the Windows host → you are here. Do **not**
> just patch the Makefile; drive the compiler directly (below). Prefer adding a
> `CMakeLists.txt` if the project will accept one upstream; otherwise a small
> build script is the pragmatic path.

---

## 1. Toolchain: clang, not `cl`, not GCC

MSVC `cl.exe` cannot compile GCC-dialect source (it lacks `<x86intrin.h>`,
`__attribute__`, GCC builtins). The **clang shipped inside Visual Studio** is the
right tool: it accepts the GCC dialect **and** targets Windows ARM64.

- Native ARM64 clang: `…\VC\Tools\Llvm\ARM64\bin\clang.exe`
- x64-host clang (for an x86 baseline under emulation): `…\VC\Tools\Llvm\x64\bin\clang.exe`
- Target triple: **`--target=aarch64-pc-windows-msvc`** (ARM64) or
  `x86_64-pc-windows-msvc` (x64 baseline).

Verify the toolchain before trusting any "build failed" signal:
`clang --version` and `clang --print-targets | grep aarch64`.

There is usually **no `make`** on the Windows host. Either add a `CMakeLists.txt`
(reuse the `enable_cmake_arm64.py` preset path), or invoke `clang` directly over
the source list in a small `.bat`/`.ps1`. Do not assume `make <target>` works.

## 2. Compiler / feature flags (verified)

```
clang --target=aarch64-pc-windows-msvc -O2 -march=armv8-a+crypto \
      -gcodeview -Xlinker -debug \
      -D_CRT_SECURE_NO_WARNINGS \
      -Iwinshim -include win_compat.h \
      <sources...> -o app_arm64.exe
```

| flag | why (verified) |
|---|---|
| `--target=aarch64-pc-windows-msvc` | ARM64 code, Windows ABI, MSVC-compatible |
| `-march=armv8-a+crypto` | **PMULL/AES/SHA are gated behind `+crypto`.** `vmull_p64`, `vaesmcq_u8`, etc. fail to compile as `always_inline ... requires target feature 'aes'` without it. PMULL/AES/SHA/CRC are **baseline on Windows ARM64**, so this is a compile-time enable, not a runtime guard. |
| `-gcodeview -Xlinker -debug` | emit a PDB so profilers/debuggers resolve function names (needed for the perf loop; optional otherwise) |
| `-D_CRT_SECURE_NO_WARNINGS` | silences MSVC-CRT deprecations for `strcpy`/`sprintf`/etc. that GCC code uses freely |

Translate GCC flags: `-msse4.2 -mpclmul` (x86) → drop on ARM64; `-march=native`
→ pick an explicit `armv8-a+<features>`; `-fPIC`/`-pthread` → drop (Windows).

## 3. The GCC/Linux headers that do not exist on Windows

clang supplies the **compiler** intrinsic headers, but not Linux **OS** headers.
Two distinct groups — handle them differently:

**(a) Compiler intrinsic headers → clang provides these on ARM64 already**
- `<x86intrin.h>`, `<emmintrin.h>`, `<cpuid.h>` are x86-only. On ARM64 the SIMD
  code needs a NEON path instead (that is the SSE/AVX→NEON port, a separate leaf
  skill). Guard the include:
  ```c
  #if defined(_M_ARM64) || defined(_M_ARM64EC) || defined(__aarch64__) || defined(__ARM_NEON)
  #  include "neon128.h"      /* your NEON mapping / native NEON code */
  #else
  #  include <x86intrin.h>    /* original x86 path, untouched */
  #endif
  ```
- `<cpuid.h>` / `__cpuid`: x86 feature detection has no ARM64 meaning. Since
  PMULL/AES/SHA/CRC are baseline on Windows ARM64, replace the runtime check with
  an unconditional enable on ARM64:
  ```c
  #if defined(_M_ARM64) || defined(__aarch64__)
      have_pclmul = 1;                 /* baseline; no cpuid on ARM64 */
  #else
      __cpuid(1, a,b,c,d); have_pclmul = (c & bit_PCLMUL) != 0;
  #endif
  ```

**(b) Linux OS/libc headers → provide a small Windows compat shim**
Common offenders and their Windows equivalents:

| Linux header / symbol | Windows / clang equivalent |
|---|---|
| `<sched.h>` `sched_setaffinity`, `cpu_set_t`, `CPU_SET` | `SetThreadAffinityMask` (windows.h); emulate the `cpu_set_t` API in the shim |
| `<sys/timeb.h>` `ftime` | `_ftime` (clang-on-Windows ships `<sys/timeb.h>`; just map the name) |
| `<netinet/in.h>` `ntohl/htonl/ntohs/htons` | `_byteswap_ulong` / `_byteswap_ushort` |
| `<unistd.h>` `getopt`, `optarg` | supply a compact `getopt` in the shim |
| `strcasecmp` / `strncasecmp` | `_stricmp` / `_strnicmp` |
| `popen` / `pclose` | `_popen` / `_pclose` |
| `LINE_MAX` | `#define LINE_MAX 2048` |

Two mechanisms, used together, let the source compile **unedited**:

1. **`-include win_compat.h`** — a single force-included header defining the
   symbols above (`#if defined(_WIN32)` guarded). Example skeleton:
   ```c
   #if defined(_WIN32)
   #include <windows.h>
   #include <sys/timeb.h>
   #define ftime(p) _ftime(p)
   #define ntohl(x) _byteswap_ulong((unsigned long)(x))
   #define strcasecmp _stricmp
   #define popen _popen
   #define pclose _pclose
   #ifndef LINE_MAX
   #define LINE_MAX 2048
   #endif
   typedef struct { unsigned long long mask; } cpu_set_t;
   #define CPU_ZERO(s) ((s)->mask = 0ULL)
   #define CPU_SET(c,s) ((s)->mask |= (1ULL << (c)))
   static __inline int sched_setaffinity(int pid, unsigned long sz, const cpu_set_t *set){
       if (set && set->mask) SetThreadAffinityMask(GetCurrentThread(), (DWORD_PTR)set->mask);
       return 0;
   }
   /* + a compact getopt() */
   #endif
   ```
2. **Empty stub headers on an include path** — for the Linux headers the source
   `#include`s that simply do not exist on Windows, create empty files under a
   `winshim/` dir and add `-Iwinshim`, so `#include <sched.h>` resolves to a
   harmless empty file while the real symbols come from `win_compat.h`:
   ```
   winshim/sched.h   winshim/unistd.h   winshim/netinet/in.h   winshim/sys/time.h   (all empty)
   ```
   Do **not** stub headers clang genuinely provides (e.g. `<sys/timeb.h>`) — that
   would shadow the real one.

This "shim header + empty stubs" combo is the key trick: the upstream `.c`/`.h`
stay byte-for-byte unedited (important for upstreamability and for diffing
against the x86 source), and all the Windows adaptation lives in two new files.

## 4. Establish an x86 baseline first (verify the failure path)

Before porting SIMD to NEON, build the **x86** target with the x64 clang + the
same shim and run the project's own tests. This proves the harness passes on the
known-good architecture, so a later ARM64 pass is meaningful (not a false green
from a test that never ran). Only then port the SIMD and re-run the identical
harness on ARM64 — the results must match.

## 5. Order of operations

1. Detect: Makefile/autotools + GCC-only includes + no `make`/`gcc` on host → this path.
2. Toolchain preflight: locate VS clang (ARM64 + x64), confirm `--print-targets`.
3. Build an **x86 baseline** (x64 clang + shim); run the project's tests → GREEN.
4. Add the compat layer: `win_compat.h` + `winshim/` empty stubs; arch-guard the
   x86-intrinsic includes; replace `__cpuid` feature detection on ARM64.
5. Port the SIMD kernels to NEON (hand off to `sse-avx-to-neon` /
   `intrinsics-x64-to-arm64` / `asm-x64-to-arm64`).
6. Build ARM64 with the §2 clang command; run the **same** tests → must match the
   x86 baseline. Prove a deliberate perturbation makes them fail (negative control).
7. Optional: add a `CMakeLists.txt` so the project has a first-class ARM64 build,
   not just a script.

## Pitfalls (each cost real time on soft-crc)

- Appending `-march=armv8-a` to the Makefile does nothing when there is no `make`
  on the host — you must drive `clang` directly (or add CMake).
- Forgetting `+crypto` → `vmull_p64 ... requires target feature 'aes'` compile
  error, even though PMULL is baseline on Windows ARM64.
- Stubbing `<sys/timeb.h>` (which clang *does* ship) shadows the real `struct
  timeb` — only stub the headers that are genuinely absent.
- `main()`/harness code (arg parsing, timing, affinity, `ntohl`) needs the shim
  too, not just the SIMD kernels — a "correct" library still won't link its test
  driver without it.
- The bash/PowerShell shell on a Windows-ARM64 dev box runs under x64 emulation
  and reports `AMD64`; do not gate ARM64 build logic on `PROCESSOR_ARCHITECTURE`.

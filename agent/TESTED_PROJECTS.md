# Tested Open Source Projects

This document lists the open source projects used to validate the easywos-skills
porting pipeline end-to-end — scan YAML (porting_items) → `spec_matcher.js` →
LLM refinement (matched.yaml) → dispatcher-skill → leaf skill (which owns the
Verification gtest project) — plus performance profiling to check for real
regressions or hot spots, rather than concluding from code reading alone.

## SIMD intrinsics ports (SSE/AVX → NEON)

Each project below covers a distinct SIMD intrinsic pattern (mulhi emulation,
movemask emulation, gather/lookup tables, single vs. multi accumulator, etc.),
used to check whether the pipeline produces correct, non-regressing ARM64 ports
across a wide variety of intrinsic classes.

| Local dir | Repository | Notes |
|---|---|---|
| cand_soft-crc | [intel/soft-crc](https://github.com/intel/soft-crc) | CRC; first easywos end-to-end validation run — GCC/Linux source, built via VS clang |
| cand_fpng | [richgel999/fpng](https://github.com/richgel999/fpng) | PNG codec; plain `cmake -A ARM64` build; caught a real PMULL imm8 lane-select bug |
| cand_bc7enc_rdo | [richgel999/bc7enc_rdo](https://github.com/richgel999/bc7enc_rdo) | BC7 decoder (27k LoC); already had a NEON path — NEON measured 1.77x faster than scalar, PSNR byte-identical |
| cand_CRoaring | [RoaringBitmap/CRoaring](https://github.com/RoaringBitmap/CRoaring) | Bitmap library (32k LoC); outer-loop testing caught a real buffer overrun (0xC0000409); MSVC ARM64 lacks `__ARM_NEON` so must use ClangCL; NEON 3.8-5.2x faster |
| cand_meshoptimizer | [zeux/meshoptimizer](https://github.com/zeux/meshoptimizer) | Mesh optimization (14.6k LoC); verified the port with profiling (not scalar A/B): 99.6% self-time in the ported kernel, no perf problem; note the shipped NEON fails to link under ClangCL — must build the whole lib with MSVC cl |
| cand_fastvalidate-utf-8 | [lemire/fastvalidate-utf-8](https://github.com/lemire/fastvalidate-utf-8) | UTF-8 validation (alignr→vextq, testz→vmaxvq); 200k checks passed, profiling verdict: clean, no perf problem |
| cand_base64 | [aklomp/base64](https://github.com/aklomp/base64) | Base64 codec (maddubs/madd/mulhi→vmull emulation); 600k checks passed, profiling clean; one unproven shift-based optimization candidate identified |
| cand_hnswlib | [nmslib/hnswlib](https://github.com/nmslib/hnswlib) | Approximate nearest-neighbor search, L2 distance kernel; found a real perf problem — the library has no ARM path at all and silently falls back to scalar L2Sqr on ARM64 |
| cand_MaskedVByte | [lemire/MaskedVByte](https://github.com/lemire/MaskedVByte) | Variable-byte encoding (native movemask emulation); found the repo's own ARM path is a broken generic sse_to_neon shim (an anti-pattern) |
| cand_FastDifferentialCoding | [lemire/FastDifferentialCoding](https://github.com/lemire/FastDifferentialCoding) | Delta encoding / prefix sum (alignr→vextq, slli_si128→vextq-zero); ported clean and converged; the serial dependency in prefix-sum is inherent, not a defect; no MSVC ARM64 build path |
| cand_despacer | [lemire/despacer](https://github.com/lemire/despacer) | SSSE3 whitespace removal; found a real correctness bug — `_mm_shuffle_epi8` zeroes on index bit7 while `vqtbl1q` zeroes on index ≥16, diverging for indices 16-127; fixed and promoted to a spec lesson |
| cand_sse-popcount | [WojciechMula/sse-popcount](https://github.com/WojciechMula/sse-popcount) | Bit population count; measured native `vcntq_u8` faster than a faithful shuffle-LUT transliteration (later corrected via a real paired A/B to ~12%); promoted to a spec lesson |
| cand_fastapprox | [romeric/fastapprox](https://github.com/romeric/fastapprox) | Fast math approximations (vfastlog2, bit-reinterpret + divide); counterintuitive finding — faithful `vdivq_f32` measured ~1.3x faster than `vrecpeq` + 2 Newton-Raphson iterations |
| cand_SIMDxorshift | [lemire/SIMDxorshift](https://github.com/lemire/SIMDxorshift) | AVX2 xorshift128+ RNG (256-bit → 2x128-bit NEON); 8M checks passed, profiling converged clean |
| cand_fmath | [herumi/fmath](https://github.com/herumi/fmath) | Fast exponential (1024-entry lookup-table gather); the gather is the irreducible NEON floor (vtbl only supports 16-byte tables) |
| cand_SIMDComp | [lemire/SIMDCompressionAndIntersection](https://github.com/lemire/SIMDCompressionAndIntersection) | SIMD bit-packing (pack5/unpack5); 400k round-trip checks passed, no hard intrinsic, clean port |
| cand_nbody_sse | [ArchaeaSoftware/cudahandbook](https://github.com/ArchaeaSoftware/cudahandbook) | N-body gravity simulation (rsqrt kernel); measured estimate + Newton-Raphson ~11% faster than full-precision sqrt+div when rsqrt IS the bottleneck (opposite regime from fastapprox, corroborating the bottleneck-pivot lesson) |
| cand_sse4strstr | [WojciechMula/sse4-strstr](https://github.com/WojciechMula/sse4-strstr) | PCMPESTRM substring search (no NEON equivalent instruction); found a real perf problem — faithful per-instruction emulation is ~2x slower than substituting a different algorithm (first/last-byte SIMD scan) |
| cand_libdivide | [ridiculousfish/libdivide](https://github.com/ridiculousfish/libdivide) | Integer division optimization (SSE2 u64 multiply-high); found a real perf problem — 4×vmull_u32 emulation is ~1.5x slower than ARM64's native UMULH |
| cand_speexdsp | [xiph/speexdsp](https://github.com/xiph/speexdsp) | Speech signal processing (SSE FIR inner product); found a real perf problem — a single-accumulator port is latency-bound, ~1.65-2x slower than 4 independent accumulators + FMA |
| cand_xxHash | [Cyan4973/xxHash](https://github.com/Cyan4973/xxHash) | Fast hashing algorithm; cloned, no completed validation run recorded yet |
| cand_meow_hash | [cmuratori/meow_hash](https://github.com/cmuratori/meow_hash) | AES-NI hash (744-line single header, no ARM path at all — it `#error`s on non-x86). Exposed a real spec gap: the AES round matched **no** spec, because the tree's only AES rule was scoped to assembly mnemonics and meow hides every intrinsic behind a one-line macro. Port is byte-exact vs the x64 AES-NI reference (682/682 cases, MSVC ARM64 + clang-cl); the reference itself was validated against the FIPS-197 known-answer vector under x64 emulation first |
| cand_c-blosc2 | [Blosc/c-blosc2](https://github.com/Blosc/c-blosc2) | AVX2 byte-plane shuffle filter (`shuffle4_avx2`): AVX2 in-lane unpack semantics plus a cross-128-bit-lane repair permute. Measured `vld4q_u8` (ARM64's de-interleaving load) ~1.3-1.8x faster streaming and ~2.0-2.5x faster cache-resident than the spec-literal unpack tree, byte-identical output; also found that the trailing cross-lane permute must be dropped rather than emulated |
| cand_SimSIMD | [ashvardanian/SimSIMD](https://github.com/ashvardanian/SimSIMD) | int4 dot product (`nk_dot_i4_haswell`, PSADBW correction sums). PSADBW was already covered, but the deferred-multiply performance spec turned out to fire as a false positive on data×data dot products; also found that the kernel's whole bias/correction machinery exists only because SSE lacks a signed 8-bit multiply, so ARM64 deletes it (4812/4812 exact vs the scalar definition) |
|  | [zlib-ng/zlib-ng](https://github.com/zlib-ng/zlib-ng) | tested |
|  | [ip7z/7zip](https://github.com/ip7z/7zip) | tested |
|  | [videolan/x265](https://github.com/videolan/x265) | tested |

## Inline-asm → intrinsics ports (wolfSSL / MariaDB, real ARM64 crypto asm)

These target genuine inline/standalone ARM64 assembly (GCC `__asm__` blocks and
GNU-syntax `.S` files), not SSE/AVX intrinsics — driving the pipeline's
`arm64-inlineasm-to-intrinsics` leaf skill instead of the SIMD-intrinsics skills
above.

| Local dir | Repository | Notes |
|---|---|---|
| mariadb-server | [MariaDB/server](https://github.com/MariaDB/server) | Host project for the wolfSSL ARM64 crypto-asm enablement port |
| extra/wolfssl/wolfssl (submodule) | [wolfSSL/wolfssl](https://github.com/wolfSSL/wolfssl) | wolfSSL's ARM64 crypto asm (AES/GCM, SHA-256, SHA-512, Poly1305, ChaCha20) has no MSVC story (only GCC/GAS asm) — ported all reachable kernels to MSVC-compatible NEON C intrinsics through the full pipeline (19 AES/GCM kernels, SHA-256, Poly1305, ChaCha20; SHA-512 verified but left inert due to a missing feature gate). Measured end-to-end: crypto CPU share on a real MariaDB server dropped from 31% to 3.9% (sysbench oltp_read_write A/B), and a byte-bound bulk-blob workload ran 1.36x faster. Found and fixed several real pre-existing bugs along the way (ABI struct-layout mismatch in Poly1305, an undeclared `__rev` intrinsic, ChaCha20 4-block-parallel perf regression) |
| wolfssl-pr (fork clone) | [wolfSSL/wolfssl PR #11035](https://github.com/wolfSSL/wolfssl/pull/11035) | Draft upstream PR adding the MSVC ARM64 NEON-intrinsics crypto path as an opt-in alternative to wolfSSL's existing `armasm64.exe`-driven asm; measured intrinsics to be performance-equivalent (not faster) to the existing asm path — the case for the PR rests on CMake/build-system reachability, not speed |

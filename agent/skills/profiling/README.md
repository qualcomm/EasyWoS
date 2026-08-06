# profiling skills

CPU performance analysis for Windows on Snapdragon (ARM64), from trace capture
to a source-level, NEON-oriented optimization report. Three skills form a
pipeline:

```
etl-generator  →  perf-sampling-parser  →  perf-optimizer
  (capture)         (per-process CPU +        (root-cause + source scan +
                     speedscope export)        HTML report)
```

| Skill | Role |
|-------|------|
| [`etl-generator`](etl-generator/SKILL.md) | Run a target program under PerfView's CPU sampler and produce a merged `.etl` trace. |
| [`perf-sampling-parser`](perf-sampling-parser/SKILL.md) | Parse an `.etl`: rank processes by CPU, then export a SpeedScope flame graph for the chosen process(es). |
| [`perf-optimizer`](perf-optimizer/SKILL.md) | Attribute the flame graph back to the true root-cause module, scan the source for x64-SIMD/ARM64-NEON gaps, and assemble an HTML report. |

`perf-optimizer` will invoke `perf-sampling-parser` automatically when handed an
`.etl` instead of a SpeedScope JSON. `perf-sampling-parser` and `etl-generator`
share the bundled `PerfView.exe` under `perf-sampling-parser/scripts/`.

## Prerequisites

- **Python 3.8+** for the analysis scripts.
- **Administrator shell** for `etl-generator` only — kernel CPU sampling uses the
  NT Kernel Logger, which requires elevation. The parsing/analysis skills do not.
- **Node.js** to serve the interactive speedscope flame graph in the
  `perf-optimizer` HTML report.
- Windows ARM64 (or x64) host. The bundled PerfView ships both `amd64/` and
  `arm64/` native helper DLLs.

## ARM64 focus

`perf-optimizer` is built around the Windows-on-ARM porting workflow: it flags
source files that have x64 SIMD (SSE/AVX) but no ARM64 NEON, detects compile
guards that gate NEON out under MSVC (`#ifdef __GNUC__`, `#ifndef __ARM_NEON`,
`#ifdef _MSC_VER`), and frames optimization suggestions in terms of NEON
intrinsics — dovetailing with the SSE/AVX → NEON and intrinsics-porting skills
elsewhere in this repository.

## Bundled tooling

These skills vendor a prebuilt PerfView + TraceEvent toolset and a speedscope web
bundle. See [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md) for licenses and
attribution. Debug symbols (`*.pdb`) and captured traces (`*.etl`, `temp/`) are
intentionally excluded from version control.

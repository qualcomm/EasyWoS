---
name: etl-generator
description: Run a target program under a CPU-sampling profiler and produce an ETL trace file for later performance analysis. Keywords - collect ETL, profile a program, generate etl, capture CPU trace, record ETL.
author: chengya
---

> ⚠️ Kernel CPU sampling requires an **elevated (Administrator) shell**. Run
> this skill from an Administrator terminal, or collection will fail with a
> privilege error.
>
> ⚠️ Do NOT use xperf / WPR / WPA to collect. Use the bundled PerfView `run`
> flow below — it produces a merged, self-contained `.etl` that the
> `perf-sampling-parser` skill can parse directly.

# ETL Generator

Launch a program under PerfView's CPU sampler, wait for it to exit, and write a
merged `.etl` trace. This is the **capture** step that feeds the analysis
skills:

```
etl-generator  →  perf-sampling-parser  →  perf-optimizer
 (this skill)      (per-process CPU +      (root-cause +
                    speedscope export)      source optimization)
```

## Path Conventions

- `<skill_dir>`: directory containing this SKILL.md, derived from the path used
  to read this file.
- Collection script: `<skill_dir>/scripts/collect_etl.py`.
- PerfView is **not shipped here**: the script reuses the copy inside the
  sibling `perf-sampling-parser/scripts/PerfView.exe`. If that sibling is
  absent, pass `--perfview <path>` explicitly.

## Inputs

- **Required**: path to the program (`.exe`) to run and profile.
- **Optional**: arguments to pass to the program (`--args`).
- **Optional**: output `.etl` path (`--out`, default `<program_dir>/<stem>.etl`).
- **Optional**: working directory for the program (`--cwd`).

## Output

- A merged `.etl` file (default next to the program). This is a self-contained
  trace ready for `perf-sampling-parser`.

## Preconditions (check before running)

1. **Elevated shell.** The script aborts with a clear error if not
   Administrator. If the user is not elevated, tell them to reopen the terminal
   as Administrator — do not attempt a workaround.
2. **Program exits on its own.** PerfView `run` stops collecting when the target
   process exits. For a long-running / server program, either give it a
   workload that terminates, or warn the user that `--timeout-sec` will force a
   stop (which may leave the program killed).

## Steps

### Step 1: Collect the ETL

```bash
python "<skill_dir>/scripts/collect_etl.py" "<program.exe>" --args "<program args>" --out "<etl_path>"
```

- Blocks until the target program exits (or `--timeout-sec`, default 600s).
- Success marker: stdout contains `DONE ... OK` and ends with
  `[collect_etl] DONE — ETL written to: <path>`.
- On failure, the script prints the first 50 lines of
  `<etl_dir>/temp/pfv_collect_log.txt`; relay them to the user.

### Step 2: Hand off to analysis

Report the absolute `.etl` path. The natural next step is the
`perf-sampling-parser` skill (or `perf-optimizer`, which will invoke
`perf-sampling-parser` for you when given an `.etl`).

## Notes

- **Merged ETL**: the script passes `/Merge:true` so module and symbol-index
  information is folded into the single `.etl`. This makes the trace portable
  and lets the parser resolve modules without the original machine state.
- **No zip**: `/Zip:false` keeps a raw `.etl` (the parser expects `.etl`/`.etlx`,
  not `.etl.zip`).
- **Buffer size**: `/BufferSizeMB:256` reduces the chance of dropped CPU samples
  on busy machines; raise it for very hot, many-core workloads.
- **What is captured**: CPU stacks (the kernel `PROFILE` sampled-profile events)
  plus image/process/thread events — enough for per-process CPU attribution and
  call-stack flame graphs. It does not enable heap or context-switch tracing.

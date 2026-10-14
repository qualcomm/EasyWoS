---
name: perf-sampling-parser
description: Analyze per-process CPU usage from ETL log files and export SpeedScope flame graphs. Keywords - ETL, flame graph, CPU usage, speedscope.
author: chengya
---

> ⚠️ Do NOT use xperf / WPA / Windows Performance Toolkit to parse ETL files. Follow the steps below for ETL parsing.

# Performance Analysis

Analyze per-process CPU usage from an ETL log; after the user selects target processes, export SpeedScope flame graphs.

## Path Conventions

- `<skill_dir>`: directory containing this SKILL.md, derived from the path used to read this file
- Analysis scripts: `<skill_dir>/scripts/` (tool paths are hard-coded inside the scripts; no external paths need to be passed in)

## Inputs

- **Required**: path to the ETL file
- **Optional**: target process name. When the ETL was just collected for a known
  target executable, select that exact process automatically instead of asking
  the user to choose it again.
- **Optional**: additional local PDB directories (semicolon-separated, NT symbol
  path format).

The default symbol policy is **local-only**: search the ETL directory and known
target/build directories, ignore inherited `_NT_SYMBOL_PATH` symbol servers, and
do not contact Microsoft or any other symbol server. Network/UNC symbol paths and
symbol servers require explicit user opt-in.

## Outputs
- **Required**: the output directory is fixed to the directory containing the ETL file.


## Steps

### Step 1: Analyze the process tree

```bash
python "<skill_dir>/scripts/process_tree.py" "<etl_path>"
```

This command is local-symbol-only by default. Pass `--allow-symbol-servers` only
after the user explicitly opts in to symbol-server access.

Success marker: stdout contains `DONE ... OK`. On failure, read the first 50 lines of `<etl_dir>/temp/pfv_log.txt` and report them to the user.


Then read the generated JSON file (path comes from the `ProcessTree written to ...` line in stdout, typically `<etl_dir>/<etl_basename_no_ext>.processtree.json`).

### Step 1.5: Parse the process tree JSON (using parse_processtree.py)

Use `parse_processtree.py` to parse the `.processtree.json` produced in Step 1 and present per-process CPU usage statistics:

```bash
python "<skill_dir>/scripts/parse_processtree.py" "<json_path>" --top 15
```

**Sample output**:
```
Total CPU time: 49630 ms

Process CPU Usage (Top 15):
16.18%  i4Tools  (pid=25344, 8030ms, parent=25188)
  7.63%  QtWebEngineProcess  (pid=19588, 3785ms, parent=25344)
11.71%  svchost  (pid=2516, 5812ms, parent=2036)
9.93%  Taskmgr  (pid=23840, 4927ms, parent=10268)
...

Total 442 processes with CPU samples

Process names for selection: i4Tools, QtWebEngineProcess, svchost, Taskmgr, ...
```

**Optional arguments**:
- `--top N`: show the top N processes (default 15)
- `--min-cpu PCT`: only show processes with CPU% >= PCT (default 0)
- `--json-output`: emit JSON for programmatic consumption

If no process has `cpuPct > 0`, tell the user "no CPU sampling data was captured" and list all processes for reference.

### Step 2: Select the target process

If the ETL was collected for a known target executable in the current workflow,
select its process name (without `.exe`) automatically. Otherwise, show the Step
1.5 list and ask the user to choose 2-3 process names.

### Step 3: Resolve local symbols by default

Use local symbols without another confirmation when the target and its build/PDB
directory are already known. Build the local symbol path from:

- the ETL directory;
- the target executable's directory and build directory, when known;
- any additional local PDB directories explicitly supplied by the user.

Do not append `_NT_SYMBOL_PATH`, UNC paths, `SRV*` entries, or HTTP(S) symbol
servers in this mode. The export script enforces this policy even when the host
environment has a corporate or public symbol server configured.

Only when the user explicitly requests symbol-server access, append the requested
server path and pass `--allow-symbol-servers`. Microsoft public symbols remain an
opt-in example: `SRV*C:\Temp\Symbols*https://msdl.microsoft.com/download/symbols`.

### Step 4: Export the SpeedScope JSON

Local-only, using the ETL directory:
```bash
python "<skill_dir>/scripts/etl_to_speedscope.py" "<etl_path>" "<comma-separated process names>" "<etl_dir>"
```

Local-only, with target/build PDB directories:
```bash
python "<skill_dir>/scripts/etl_to_speedscope.py" "<etl_path>" "<comma-separated process names>" "<etl_dir>" "<local_pdb_path>"
```

Explicit symbol-server opt-in:
```bash
python "<skill_dir>/scripts/etl_to_speedscope.py" "<etl_path>" "<comma-separated process names>" "<etl_dir>" "<symbol_path>" --allow-symbol-servers
```

Success marker: stdout contains `DONE ... OK`. On failure, read the first 50 lines of `<etl_dir>/temp/pfv_log2.txt` and report them to the user.

### Step 5: Report the results

```
SpeedScope files generated (in the same directory as the ETL):
  \\server\share\log.processtree.json           (8030 ms CPU)
  \\server\share\QtWebEngineProcess_19588.speedscope.json (3785 ms CPU)

How to open: drag the file into https://speedscope.app (processed locally, not uploaded)
```

Symbol resolution failures (system DLLs or third-party modules without PDBs) are normal and do not affect application-level call stacks.

---

> For details on PerfView command arguments and output format, read `references/PerfViewCommands.md`.

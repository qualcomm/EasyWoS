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
- **Required**: confirm the PDB path with the user (semicolon-separated, NT symbol path format). If not provided, the script will automatically search the ETL's directory and `_NT_SYMBOL_PATH`.

## Outputs
- **Required**: the output directory is fixed to the directory containing the ETL file.


## Steps

### Step 1: Analyze the process tree

```bash
python "<skill_dir>/scripts/process_tree.py" "<etl_path>"
```

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

### Step 2: Show the process list and let the user choose

Based on the Step 1.5 output, ask the user to choose 2-3 process names (without the `.exe` suffix) for analysis.

### Step 3: Confirm the symbol path

After the user picks the processes, you **must** confirm the following two points with the user before proceeding:

1. **Custom PDB path**: ask whether there are extra PDB directories to add (local path or UNC, semicolon-separated). Leave empty if none.
2. **Microsoft public symbol server**: ask whether to include the MSFT public PDBs (`SRV*C:\Temp\Symbols*https://msdl.microsoft.com/download/symbols`). Adding it lets system DLL symbols resolve, but the first download is slow.

Example prompt:
```
Selected process: i4Tools

Please confirm the symbol configuration:
1. Any custom PDB path? (press Enter to skip)
2. Include the Microsoft public symbol server? (y/n — enables system DLL symbols but is slow on first run)
```

**Assemble the final symbol path** (NT symbol path format, semicolon-separated):
- Base: the ETL's directory (the script includes it automatically)
- Append the user's custom path (if any)
- If the user agrees, append `SRV*C:\Temp\Symbols*https://msdl.microsoft.com/download/symbols`

Example final `<pdb_path>`:
```
D:\myapp\pdbs;SRV*C:\Temp\Symbols*https://msdl.microsoft.com/download/symbols
```

### Step 4: Export the SpeedScope JSON

Without PDBs (the user provided neither):
```bash
python "<skill_dir>/scripts/etl_to_speedscope.py" "<etl_path>" "<comma-separated process names>" "<etl_dir>"
```

With PDBs (the user supplied a custom path or opted into the MSFT public symbols):
```bash
python "<skill_dir>/scripts/etl_to_speedscope.py" "<etl_path>" "<comma-separated process names>" "<etl_dir>" "<pdb_path>"
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

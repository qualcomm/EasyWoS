# PerfView Extension Commands Reference

Commands provided by `PerfViewExtensions/Global.dll`.  
Invoked via: `PerfView.exe /AcceptEULA /NoGui UserCommand <CommandName> <args...>`

---

## ProcessTree

### Purpose

Parse an ETL trace and export every process's CPU time and parent-child relationship
to a JSON file. Use this as the first step to identify which processes consume the
most CPU before drilling down with `EtlToSpeedScope`.

### Signature

```
ProcessTree  <etlFileName>  [outputJson]
```

| Parameter | Required | Description |
|-----------|----------|-------------|
| `etlFileName` | Yes | Path to the `.etl` or `.etlx` file |
| `outputJson` | No | Output path. Defaults to `<etlFileName>.processtree.json` |

### Examples

```bash
# Minimal – output written next to the ETL file
PerfView.exe /AcceptEULA /NoGui UserCommand ProcessTree "C:\traces\app.etl"

# Explicit output path
PerfView.exe /AcceptEULA /NoGui UserCommand ProcessTree "C:\traces\app.etl" "C:\out\tree.json"

# UNC path
PerfView.exe /AcceptEULA /NoGui UserCommand ProcessTree "\\server\share\trace.etl"
```

### Output Format

```json
{
  "totalCpuMSec": 45321.000,
  "processes": [
    {
      "pid": 1234,
      "name": "chrome",
      "cpuMSec": 12480.000,
      "cpuPct": 27.53,
      "parentPid": 892,
      "cmdLine": "chrome.exe --type=renderer"
    },
    {
      "pid": 892,
      "name": "chrome",
      "cpuMSec": 8760.000,
      "cpuPct": 19.33,
      "parentPid": 0,
      "cmdLine": "chrome.exe"
    }
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `totalCpuMSec` | float | Sum of CPU time across all processes in the trace (ms) |
| `pid` | int | OS process ID (may be reused across the trace lifetime) |
| `name` | string | Image name without path or `.exe` suffix |
| `cpuMSec` | float | CPU time consumed by this process (ms) |
| `cpuPct` | float | `cpuMSec / totalCpuMSec × 100` |
| `parentPid` | int | Parent process OS ID (`0` if unknown or root) |
| `cmdLine` | string | Full command line string (empty if not captured) |

**Sort order:** descending by `cpuMSec`.

### Notes

- On the **first run** the ETL file is converted to `.etlx` format (cached alongside the
  original). This can take tens of seconds for large traces. Subsequent runs reuse the
  cache and are fast.
- `pid` is **not unique** across the trace; the same PID can be reused after a process
  exits. The list may therefore contain multiple entries with the same `name` and `pid`.
  Use `cpuMSec` and `cmdLine` to disambiguate.
- Processes with `cpuMSec = 0` are included (kernel/idle processes, short-lived
  processes that produced no CPU samples).

---

## EtlToSpeedScope

### Purpose

Export CPU call stacks for one or more processes from an ETL trace to
[SpeedScope](https://speedscope.app) JSON files. Each process produces one
`<name>_<pid>.speedscope.json` file that can be opened directly in the browser.

Typically called **after** `ProcessTree` once the heavy processes are identified.

### Signature

```
EtlToSpeedScope  <etlFileName>  <processNames>  [outputDir]  [symbolPath]
```

| Parameter | Required | Description |
|-----------|----------|-------------|
| `etlFileName` | Yes | Path to the `.etl` or `.etlx` file |
| `processNames` | Yes | Comma-separated process names **without** `.exe` suffix |
| `outputDir` | No | Output directory. Defaults to the ETL file's directory |
| `symbolPath` | No | Extra PDB search path (NT symbol path format, see below) |

### Examples

```bash
# Single process, output next to ETL
PerfView.exe /AcceptEULA /NoGui UserCommand EtlToSpeedScope "C:\traces\app.etl" "chrome"

# Multiple processes
PerfView.exe /AcceptEULA /NoGui UserCommand EtlToSpeedScope "C:\traces\app.etl" "chrome,msedge,renderer"

# Explicit output directory (pass "" to use default)
PerfView.exe /AcceptEULA /NoGui UserCommand EtlToSpeedScope "C:\traces\app.etl" "chrome" "C:\out"

# Local PDB directory
PerfView.exe /AcceptEULA /NoGui UserCommand EtlToSpeedScope "C:\traces\app.etl" "chrome" "" "C:\mypdbs"

# Multiple PDB paths (semicolon-separated)
PerfView.exe /AcceptEULA /NoGui UserCommand EtlToSpeedScope "C:\traces\app.etl" "chrome" "" "C:\pdbs\app;C:\pdbs\framework;C:\pdbs\thirdparty"

# PDB paths + Microsoft symbol server
PerfView.exe /AcceptEULA /NoGui UserCommand EtlToSpeedScope "C:\traces\app.etl" "chrome" "" "C:\pdbs\app;SRV*C:\symcache*https://msdl.microsoft.com/download/symbols"

# UNC trace with UNC PDB share
PerfView.exe /AcceptEULA /NoGui UserCommand EtlToSpeedScope "\\server\share\trace.etl" "myapp" "C:\out" "\\pdbs-server\symbols"
```

### Symbol Path Format

`symbolPath` follows the standard `_NT_SYMBOL_PATH` syntax:

| Pattern | Meaning |
|---------|---------|
| `C:\mypdbs` | Local directory |
| `\\server\share` | UNC share |
| `SRV*C:\cache*https://...` | Symbol server with local cache |
| `A;B;C` | Semicolon-separated list, searched left to right |

**Full resolution order (highest priority first):**

1. `symbolPath` parameter (prepended at runtime)
2. Directory of the ETL file — e.g. `\\server\share\`
3. `<etl_dir>\symbols\` subdirectory (if it exists)
4. `<etl>.NGENPDB\` directory (WPR capture convention)
5. `_NT_SYMBOL_PATH` environment variable

Setting `_NT_SYMBOL_PATH` before invoking PerfView is the recommended approach
when the same symbol path is reused across many calls:

```bash
set _NT_SYMBOL_PATH=C:\pdbs\app;C:\pdbs\framework;SRV*C:\symcache*https://msdl.microsoft.com/download/symbols
PerfView.exe /AcceptEULA /NoGui UserCommand EtlToSpeedScope "C:\traces\app.etl" "chrome,msedge"
```

### Output

One `.speedscope.json` file per process, named `<processName>_<pid>.speedscope.json`:

```
chrome_1234.speedscope.json
msedge_5678.speedscope.json
```

Log output per process (visible in stdout with `/NoGui`):

```
[chrome (pid=1234, CPU=12480ms) -> C:\out\chrome_1234.speedscope.json]
```

Open the output file at **https://speedscope.app** (drag-and-drop, no upload required —
the site processes files locally in the browser).

### Notes

- Symbols are resolved via `LookupWarmSymbols(1)` before export — only modules that
  appear at least once in the **selected process's stacks** have their PDBs loaded.
  Using `minCount=0` would load PDBs for every module in the entire trace (including
  other processes) because `0 >= 0` is always true. Without valid PDB paths frames
  will appear as hex addresses (e.g. `0x7ffb3a21dead`).
- If a process name appears multiple times in the trace (same name, different PID),
  the **last instance** (by start time) is exported. To target a specific instance,
  adjust the name lookup in the source or use `ProcessTree` output to identify the PID.
- The `.etlx` cache from a prior `ProcessTree` run is reused automatically.

---

## Typical Skill Workflow

```
Step 1 – Identify hot processes
  PerfView.exe /AcceptEULA /NoGui UserCommand ProcessTree "<etl>"
  → parse <etl>.processtree.json
  → present top-N processes sorted by cpuPct
  → user selects 2-3 process names

Step 2 – Export flame graphs
  PerfView.exe /AcceptEULA /NoGui UserCommand EtlToSpeedScope "<etl>" "proc1,proc2" [outDir] [symPath]
  → open proc1_<pid>.speedscope.json at https://speedscope.app
```

### Exit codes

| Code | Meaning |
|------|---------|
| `0` | Success |
| Non-zero | Error — check stdout/stderr for the message |

Success marker in stdout: `DONE HH:MM:SS OK`  
Failure marker in stdout: `DONE HH:MM:SS FAIL: <message>`

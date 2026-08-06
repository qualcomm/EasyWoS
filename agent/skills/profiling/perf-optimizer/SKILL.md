---
name: perf-optimizer
description: |
  Performance bottleneck root-cause analysis tool. Parses SpeedScope JSON flame
  graphs, traces back the call chain to the true root-cause module (not just
  the most expensive leaf), then combines that with user-provided source paths
  to pinpoint hotspots, and lets the model produce targeted optimization
  suggestions based on context.

  Two input modes are supported:
  1. **SpeedScope JSON** (proceeds straight to Phase 1)
  2. **ETL file** (automatically calls the `perf-sampling-parser` skill via the
     Skill tool to first analyze per-process CPU usage; the user picks the
     target process and exports a SpeedScope JSON, then proceeds to Phase 1)

  **The target process is NOT specified up front by the user**: when the input
  is an ETL, do NOT ask the user "which process do you want to analyze" before
  invoking perf-sampling-parser. The target process must be chosen by the user
  based on real data — the process tree and Top-N CPU breakdown produced by
  perf-sampling-parser.

  Triggers:
  - The user asks to analyze a speedscope.json / ETL / flame graph
  - The user provides source paths for a DLL/EXE and wants to find concrete
    optimization opportunities
  - Keywords: perf-optimizer, flame graph root cause, performance analysis,
    scalar fallback, find an optimization plan,
    performance analysis with source, find perf issues in source, analyze etl
author: chengya
---

# Perf Optimizer — SpeedScope Root-Cause Analysis & Source Optimization

Four-phase workflow:
1. **Phase 0 (optional) ETL → SpeedScope JSON** — when the input is an `.etl`,
   **invoke the `perf-sampling-parser` skill via the Skill tool** to do the
   parsing; the target process is selected by the user inside that skill after
   the CPU usage breakdown is shown — do not ask in advance from the outside.
2. **Phase 1 `analyze_speedscope.py`** — parse the flame graph, attribute back
   to the true root-cause module, emit raw timing data
3. **Phase 2 `search_source.py`** — locate hot functions in the source tree,
   scan for optimization opportunities
4. **Phase 3 `generate_report.py`** — package the previous results into a
   visual HTML report (with the real speedscope flame graph embedded)

---

## Path Conventions

- `<skill_dir>`: directory containing this SKILL.md, derived from the path
  used to read the file
- Analysis scripts: `<skill_dir>/scripts/`
- Report template and speedscope bundle: `<skill_dir>/assets/` (located by
  the scripts via relative paths — no external value to pass in)

## Execution Environment

**The shell is bash, not PowerShell.** Python scripts are invoked using:

```bash
python "<skill_dir>/scripts/analyze_speedscope.py" "<speedscope.json>" [--top-n 20] [--out report.json]
python "<skill_dir>/scripts/search_source.py" "<report.json>" --sources "mod=path;mod2=path2"
python "<skill_dir>/scripts/generate_report.py" --speedscope <speedscope.json> --perf-report <report.json> --out-dir <dir>
```

**UNC paths**: Python on Windows handles UNC paths (`\\server\share\...`)
natively — no special handling required.

---

## Required Inputs

**Phase 0 (only when the input is an ETL):**
- ETL file path (local or UNC)
- After Phase 0 you have a SpeedScope JSON and a processtree JSON; proceed to
  Phase 1

**Phase 1 (required):**
- SpeedScope JSON path (local or UNC, e.g.
  `\\server\share\i4Tools_25344.speedscope.json`)

**Phase 2 (provided by the user after Phase 1):**
- Module → source-path mapping, semicolon-separated:
  `qt6webenginecore=C:\src\qt;i4tools=\\server\src\app`
- Some modules may have no source (closed-source / third-party); just skip
  them — the script will warn you

---

## Workflow

### Step 0: Detect the input type (ETL vs JSON branching)

Decide which path to take based on the file extension:

| User input | Path |
|---|---|
| `*.speedscope.json` or `*.json` | **Skip Step 0**, go directly to Step 1 |
| `*.etl` or `*.etl.zip` | **Must run Step 0a first**: invoke `perf-sampling-parser` via the Skill tool to convert the ETL to a SpeedScope JSON |

**Step 0a — Invoke perf-sampling-parser to handle the ETL (only when the input is an ETL)**

Do not try to parse the ETL yourself or run xperf / WPA. **The only correct
approach is to invoke** `perf-sampling-parser` **via the Skill tool**, passing
the user-provided ETL path as `args`:

```
Skill tool call:
  skill = perf-sampling-parser
  args  = "<ETL path supplied by the user>"
```

**About the "target process":**

- Before entering perf-sampling-parser, do **NOT** ask the user "which process
  do you want to analyze".
- The target process must be produced by perf-sampling-parser via the
  following flow:
  1. `process_tree.py` parses the ETL and produces
     `<etl_basename>.processtree.json`
  2. `parse_processtree.py` shows the Top-N processes by CPU usage (with PID,
     ms, name)
  3. The user picks 1–3 process names (without `.exe`) **based on the real
     CPU usage list**.
- Only when the user has already named the target process explicitly in the
  conversation history may you skip the process-selection step inside
  perf-sampling-parser and pass the name through directly.

`perf-sampling-parser` runs through its own flow:
1. Generates `<etl_dir>/<etl_basename>.processtree.json`
2. Shows the per-process CPU breakdown and **lets the user pick a target
   process based on real data**
3. **Lets the user confirm the PDB / Microsoft symbol-server configuration**
4. Produces `<ProcessName>_<PID>.speedscope.json` next to the ETL

**After Step 0a, record the absolute paths of the two artifacts and proceed
to Step 1:**
- `<SPEEDSCOPE_PATH>` = `<etl_dir>/<ProcessName>_<PID>.speedscope.json`
- `<PROCESSTREE_PATH>` = `<etl_dir>/<etl_basename>.processtree.json`
  (passed via `--processtree` when generating the report in Step 5)

If the user picked multiple processes in Step 0a and produced multiple
speedscope JSONs, analyze them one at a time, or first confirm with the user
which one to analyze.

---

### Step 1: Run the Phase 1 analysis

```bash
python "<skill_dir>/scripts/analyze_speedscope.py" "<SPEEDSCOPE_PATH>" --top-n 20
```

Script outputs:
- **stdout**: human-readable summary (present this directly to the user)
- **`<name>.perf_report.json`**: structured JSON (used by Phase 2)

Success marker: stdout ends with `[Report saved to: ...]`

---

### Step 2: Interpret Phase 1 results and form optimization hypotheses

The script only delivers raw timing facts. You make the call based on project
background, platform, the nature of the modules, etc.

#### 2a. Three dimensions to read

**① Thread heat** (`top_threads`)
- Which thread consumes the most? Is it the UI thread (responsiveness issue)
  or a background thread (throughput issue)?

**② Module self time** (`module_self_time`)
- High self time = the module's own code is executing — it is not waiting
  for callees
- High self time but low inclusive time → the module is a leaf and is the
  place actually doing work

**③ Hot functions + call chains** (`hot_functions`)
- `self_pct`: the function's exclusive share of CPU
- `suspect_caller_module`: the first non-system module in the call chain —
  the module that should actually be optimized
- `top_call_chains`: who calls this function and the weight of each path

#### 2b. Root-cause attribution logic

- Hot frame is in a **system module** (ucrtbase, ntdll, kernel32, …) → look at
  `suspect_caller_module`; that is the module to fix
- Hot frame is in an **application module** → that module is the optimization
  target itself
- Sample chain: `ntdll → kernel32 → qt6webenginecore → ucrtbase!fminf`
  → root cause is `qt6webenginecore`; ucrtbase is just the callee

#### 2c. Forming optimization hypotheses

Based on function names and call relations, combined with your understanding
of the project's tech stack:

| Observed phenomenon | Possible cause (verify with context) |
|---|---|
| System math functions (fminf, sqrtf, …) consume large CPU | Hot loop is not vectorized; or the platform's SIMD path is gated out by a compile switch |
| Memory functions (memcpy, memset) consume large CPU | Heavy data copying; bad buffer design; or the platform-optimized variant is not being used |
| Heap allocators (malloc, HeapAlloc) consume large CPU | High-frequency small-object allocation; missing object pool / arena |
| Wait/lock functions (NtWaitForSingleObject, …) consume large CPU | Lock granularity too coarse; thread contention; or unnecessary synchronization |
| App module has high self time but no obvious system calls | Inefficient algorithm; wrong data structure; cache misses |

**Don't pre-commit to a conclusion**: the same symptom can have totally
different causes in different projects. Describe the observation, then state
a hypothesis, then propose how to verify it.

#### 2d. Present the analysis to the user

```
## Performance Analysis Findings

### Primary bottleneck

**[module name]  X% CPU  (Yms)**
- Observation: [describe the functions and call chains]
- Call path: A → B → C!func
- Hypothesis: [inference based on project context]
- Verification: [how to confirm the hypothesis, or what could be confirmed
  once source is provided]

### Secondary bottlenecks
...
```

#### 2e. List modules that need source

Pull from `modules_needing_source` and ask the user:

```
The following modules have optimization potential — please provide their
source paths:
  • [module1]
  • [module2]

Format: module=source_path, multiple separated by semicolons
Example: qt6webenginecore=C:\src\qt6\qtwebengine;i4tools=\\server\src\i4tools

Modules without source can be skipped (closed-source / third-party).
```

---

### Step 3: Run the Phase 2 source analysis

After the user provides source paths:

```bash
REPORT_PATH="<path_from_phase1>.perf_report.json"
python "<skill_dir>/scripts/search_source.py" "$REPORT_PATH" \
    --sources "qt6webenginecore=C:\src\qt;i4tools=\\server\src"
```

Script outputs:
- **stdout**: source analysis report
- **`<name>.source_analysis.json`**: structured results

What it scans for (ARM64 viewpoint):
1. **x64/ARM64 asymmetric files** (`files_x64_only`): files with SSE/AVX but
   no NEON — highest-priority targets, since x64 has already proven the
   speedup; ARM64 just hasn't been done yet
2. **Compile-time guards that block the path** (`blocking_findings`):
   `#ifdef _MSC_VER`, `#ifndef __ARM_NEON`, `#ifdef __GNUC__`, etc. —
   conditions that may gate out NEON code paths under Windows ARM64 MSVC
3. **Hot-function locations** (`function_findings`): the concrete `file:line`
   of hot functions in source; together with `caller_frames` you can land
   directly on the call site

---

### Step 4: ARM64 optimization brainstorm

Combine both phases and brainstorm against **Windows ARM64** as the target
platform, using this framework:

#### 4a. x64 has SIMD, ARM64 does not → direct port opportunity

If `files_x64_only` is non-empty, this is the highest-confidence opportunity:

```
## [HIGH] x64 SIMD present, ARM64 NEON missing

File: src/renderer/paint.cpp
What x64 does: uses _mm256_max_ps / _mm256_min_ps for batched pixel processing
ARM64 equivalent: vmaxq_f32 / vminq_f32 (NEON, 4 floats per instruction)

Reference: src/renderer/blend.cpp in the same module already has an ARM64
           NEON implementation — its #ifdef __ARM_NEON layout can be reused
```

#### 4b. Compile guard blocking → quick fix

If `blocking_findings` shows `#ifdef __GNUC__` or `#ifndef _MSC_VER` wrapping
NEON code:

```
## [HIGH] NEON code exists but is gated out by a compile guard

File: src/platform/simd.h:42
Issue: #ifdef __GNUC__ wraps the NEON path; MSVC skips it at compile time
Fix:   change to #if defined(__ARM_NEON) || defined(_M_ARM64)
       under MSVC ARM64 _M_ARM64 is defined, so the NEON branch is taken
```

#### 4c. `portable::` / scalar fallback → needs a new NEON path

If hot function names contain namespaces like `portable::`, `generic::`,
`scalar::`, or call directly into CRT math functions:

```
## [MEDIUM] Scalar fallback path, no ARM64 specialization yet

Functions: portable::clamp_01, portable::gather_8888
Symptom:   call chain → ucrtbase!fminf/fmaxf, 50% CPU
Direction: Skia's `portable::` is the SIMD-less fallback. Check whether
           there is a corresponding `neon::` / `arm::` implementation file —
           if so, why isn't it being chosen (compile condition? link path?);
           if not, write a platform-specific layer.
```

#### 4d. Output format

```
## Windows ARM64 Optimization Brainstorm (by priority)

### [HIGH] x64 SIMD port — module!func  X% CPU

Root cause: [call chain explanation]
x64 implementation: [file:line, which SSE/AVX intrinsics]
ARM64 direction: [matching NEON intrinsics, or location of an existing
                 reference implementation]
Estimated gain: [estimate based on current self%]

### [HIGH] NEON guard fix — file:line
...

### [MEDIUM] Add NEON specialization — module!func
...
```

**Note**: be honest about confidence in the brainstorm. `files_x64_only` is
high confidence (x64 has set the precedent); `blocking_findings` is
medium-high (the code exists but may be gated out); pure scalar is low
confidence (you need to read the code to decide whether it is worth
vectorizing).

---

### Step 5: Generate the visual report (Phase 3, optional)

If the user wants the analysis results materialized as an HTML report (with
the real speedscope flame graph, Top Processes, hotspot tables, Root Cause
Diagnosis, and Final Summary), use `generate_report.py`:

```bash
OUT_DIR="<somewhere-writable>/perf_report"

python "<skill_dir>/scripts/generate_report.py" \
  --speedscope        "<SPEEDSCOPE_PATH>" \
  --perf-report       "<perf_report.json from Phase 1>" \
  --source-analysis   "<source_analysis.json from Phase 2>"  `# optional` \
  --processtree       "<processtree.json>"                    `# optional, enables Top Processes card` \
  --root-cause-json   "<root_cause.json>"                     `# optional, but strongly recommended: the Step 4 diagnosis` \
  --summary-json      "<summary.json>"                        `# optional: overrides the default Final Summary` \
  --title             "i4Tools Windows ARM64 Performance Analysis" `# optional` \
  --out-dir           "$OUT_DIR"
```

**Important: write the Step 2 / Step 4 conclusions to a file and pass it in**

By default `generate_report.py` produces a **workload-agnostic** Final Summary
from the objective timing data only (no guesses about the specific tech
stack). You must structure the Step 2 root-cause attribution and the Step 4
brainstorm into JSON and pass them via `--root-cause-json`, otherwise the
report has no real diagnosis.

**Root Cause JSON schema** (`--root-cause-json` file content):

```json
{
  "title": "One-line root cause (e.g.: Skia falls back to portable:: scalar path on Windows ARM64)",
  "confidence": "HIGH | MEDIUM | LOW",
  "lead": "2-3 sentences summarizing the symptom and the causal chain",
  "impactPct": 50.2,
  "impactMs": 4033,
  "evidence": [
    {
      "step": 1,
      "title": "Title for this evidence item",
      "file": "src/path/to/file.h",
      "lines": "20-46",
      "code": "actual source snippet (preserve indent and newlines)",
      "observation": "what this snippet shows and why it is a problem"
    }
  ],
  "fixes": [
    {
      "priority": "HIGH ★★★ | MEDIUM ★★ | LOW ★",
      "title": "Fix title",
      "estGain": "30-50% of process total CPU",
      "body": "Detailed steps, commands, configuration examples (multi-line OK; rendered with white-space:pre-wrap)",
      "verify": "How to verify this fix works (omit or set to \"—\" if N/A)"
    }
  ],
  "scopeNote": "Scope and limitations of this analysis (optional)"
}
```

**Summary JSON schema** (`--summary-json` file content, optional, overrides
the default Final Summary):

```json
{
  "findings": [
    {"label": "Short title", "text": "Description"}
  ],
  "actions": [
    "Recommended action 1 (prefix with [HIGH]/[MEDIUM]/[LOW] priority)",
    "Recommended action 2"
  ]
}
```

**Typical workflow: run Step 2 / Step 4, write the conclusions to temp JSON,
then call generate_report.py:**

```bash
# 1. Write the root-cause diagnosis to a JSON file
cat > /tmp/root_cause.json <<'EOF'
{"title": "...", "confidence": "HIGH", "evidence": [...], "fixes": [...]}
EOF

# 2. Write the Final Summary to a JSON file
cat > /tmp/summary.json <<'EOF'
{"findings": [...], "actions": [...]}
EOF

# 3. Generate the report
python "<skill_dir>/scripts/generate_report.py" \
  --speedscope ... --perf-report ... \
  --root-cause-json /tmp/root_cause.json \
  --summary-json /tmp/summary.json \
  --out-dir ...
```

The script writes into `--out-dir`:
- `report.html` — dashboard (dark theme, multi-card layout, includes Root
  Cause Diagnosis)
- `report_data.js` — `window.REPORT_DATA = {...}`, contains Top Processes /
  module self-time / hot functions / Root Cause / Final Summary
- `speedscope/` — the embedded speedscope app (from `assets/speedscope/`)
  plus a copy of the speedscope JSON

**The user then needs to:**
1. Start the speedscope server (the script prints the command):
   ```bash
   node "<OUT_DIR>/speedscope/server.js" "<profile.speedscope.json>"
   ```
   (`server.js` only serves files from its own directory, which is why the
   script copies the speedscope JSON in)
2. Open `<OUT_DIR>/report.html` in a browser

The flame-graph card uses an iframe to load
`http://localhost:8888/index-auto.html?file=<profile>.speedscope.json` — so
Time Order / Left Heavy / Sandwich / zoom / search work out of the box.

**Why an iframe instead of fully embedding speedscope into the page**:
speedscope ships a 487 KB JS bundle + WASM + fonts; reimplementing those
views is both a lot of work and likely to drift from speedscope's semantics.
Reusing the speedscope app itself means Time Order / Left Heavy / Sandwich
behavior is always identical to speedscope.app.

---

## Notes

- **`??` modules**: if `unresolved_pct > 5%`, warn the user that PDB coverage
  is insufficient and the credibility of the analysis is reduced
- **Closed-source modules**: with no source, you can still give directional
  advice based on the call chain (e.g.: file feedback with the vendor; look
  for an ARM64-optimized alternative version)
- **Thread detail**: `top_threads` shows the 3 hottest threads — useful for
  deciding whether it's UI-thread stalls (responsiveness) or background-thread
  CPU saturation (throughput)
- **Inclusive time over 100%**: normal — the same module is counted multiple
  times across threads / call paths
- **Large source trees**: `search_source.py` automatically skips
  `build/out/obj/.git` etc., but a very large source tree may still take
  several minutes — tell the user the scan is running
- **`_M_ARM64` vs `__ARM_NEON`**: under MSVC Windows ARM64, `_M_ARM64` is
  defined but `__ARM_NEON` is not necessarily defined. NEON intrinsics
  require `#include <arm_neon.h>` and a guard using `_M_ARM64` or
  `__ARM_NEON`

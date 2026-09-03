#!/usr/bin/env python3
"""Collect a CPU-sampling ETL trace while running a target program (PerfView `run`).

Launches the given program under PerfView's kernel CPU-sampling collector,
waits for it to exit, and produces a merged, self-contained .etl file that the
`perf-sampling-parser` skill can parse.

REQUIRES AN ELEVATED (Administrator) SHELL: kernel CPU sampling uses the NT
Kernel Logger ETW session, which is Administrator-only. Without elevation
PerfView reports "Error: Not enough privilege ... must be Administrator".

Usage:
    python collect_etl.py "<program>" [--args "<program args>"]
                          [--out <etl_path>] [--cwd <dir>]
                          [--perfview <PerfView.exe>] [--timeout-sec N]

Exit codes:
    0  success — <out>.etl written (merged)
    1  failure — details on stderr and in <out_dir>/temp/pfv_collect_log.txt
    2  usage / environment error (e.g. not elevated, PerfView not found)
"""

import argparse
import ctypes
import os
import pathlib
import subprocess
import sys


def find_perfview(explicit: str | None) -> pathlib.Path | None:
    """Locate PerfView.exe: explicit arg > sibling perf-sampling-parser > PATH."""
    if explicit:
        p = pathlib.Path(explicit)
        return p if p.exists() else None

    here = pathlib.Path(__file__).resolve()
    # Reuse the PerfView shipped with the sibling perf-sampling-parser skill,
    # avoiding a second 24 MB copy.
    sibling = (here.parent.parent.parent
               / "perf-sampling-parser" / "scripts" / "PerfView.exe")
    if sibling.exists():
        return sibling

    from shutil import which
    found = which("PerfView.exe") or which("PerfView")
    return pathlib.Path(found) if found else None


def is_elevated() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Collect a CPU-sampling ETL while running a target program.")
    parser.add_argument("program", help="Path to the program (.exe) to run and profile")
    parser.add_argument("--args", default="", help="Arguments to pass to the program")
    parser.add_argument("--out", default="",
                        help="Output .etl path (default: <program_dir>/<program_stem>.etl)")
    parser.add_argument("--cwd", default="", help="Working directory for the program")
    parser.add_argument("--perfview", default="", help="Explicit path to PerfView.exe")
    parser.add_argument("--timeout-sec", type=int, default=600,
                        help="Kill collection if the program runs longer than this (default 600)")
    args = parser.parse_args()

    program = pathlib.Path(args.program)
    if not program.exists():
        print(f"ERROR: program not found: {program}", file=sys.stderr)
        return 2

    if not is_elevated():
        print("ERROR: not running as Administrator. Kernel CPU sampling requires an "
              "elevated shell. Restart your agent harness (Codex, Claude Code, "
              "or the current terminal) from an Administrator terminal, then "
              "resume from profiling with the same program/workload arguments.",
              file=sys.stderr)
        return 2

    perfview = find_perfview(args.perfview or None)
    if perfview is None:
        print("ERROR: PerfView.exe not found (looked at --perfview, sibling "
              "perf-sampling-parser/scripts/, and PATH).", file=sys.stderr)
        return 2

    out_etl = pathlib.Path(args.out) if args.out else program.with_suffix(".etl")
    out_dir = out_etl.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    # Drop a leftover ETL from a previous run, so the out_etl.exists() success
    # test cannot pass on a stale file after a failed collection.
    try:
        out_etl.unlink()
    except OSError:
        pass

    temp_dir = out_dir / "temp"
    temp_dir.mkdir(exist_ok=True)
    log_file = temp_dir / "pfv_collect_log.txt"
    # PerfView APPENDS to /LogFile:. A stale "DONE ... SUCCESS" from a previous
    # run would otherwise be read as this run's success marker, so start clean.
    try:
        log_file.unlink()
    except OSError:
        pass

    # Build PerfView's command line. IMPORTANT: pass the program and each of its
    # arguments as SEPARATE argv elements — do NOT pre-quote or pre-join them.
    # If we hand subprocess a single element like '"prog.exe" 2000000 60', Python
    # sees the spaces + embedded quotes and re-escapes them ("\"prog.exe\" ..."),
    # which PerfView then mis-parses (the stray leading \ becomes the "command").
    # Separate elements let subprocess.list2cmdline quote only what truly needs it.
    import shlex
    cmd = [
        str(perfview),
        "/AcceptEULA",
        "/NoGui",
        f"/LogFile:{log_file}",
        f"/DataFile:{out_etl}",
        "/Merge:true",        # produce a self-contained ETL (folds in module/symbol info)
        "/Zip:false",         # keep a raw .etl (parser expects .etl/.etlx, not .etl.zip)
        "/BufferSizeMB:256",  # headroom so CPU samples are not dropped
        "run",
        str(program),
    ]
    if args.args:
        cmd.extend(shlex.split(args.args, posix=False))
    launch = subprocess.list2cmdline([str(program)] +
                                     (shlex.split(args.args, posix=False) if args.args else []))

    print(f"[collect_etl] PerfView : {perfview}")
    print(f"[collect_etl] Program  : {launch}")
    print(f"[collect_etl] Output   : {out_etl}")
    print(f"[collect_etl] Log      : {log_file}")
    print(f"[collect_etl] Running (this blocks until the program exits) ...", flush=True)

    run_cwd = args.cwd or None
    try:
        result = subprocess.run(cmd, capture_output=True, text=True,
                                encoding="utf-8", errors="replace",
                                cwd=run_cwd, timeout=args.timeout_sec)
    except subprocess.TimeoutExpired:
        print(f"ERROR: collection exceeded {args.timeout_sec}s and was killed.",
              file=sys.stderr)
        return 1

    output = (result.stdout or "") + (result.stderr or "")
    print(output)

    # PerfView's `run` verb ends its log with "DONE <time> SUCCESS: ..." (the
    # UserCommand verb used by the sibling skills ends with "DONE ... OK"). Accept
    # either, and require the merged ETL to actually exist on disk.
    #
    # IMPORTANT: with /LogFile: PerfView writes its log to that FILE, and stdout
    # gets a truncated copy that may not contain the final DONE line at all. So
    # look for the marker in the log file as well, not just in stdout -- checking
    # stdout alone reports a false FAILURE on a collection that actually worked.
    def has_done_marker(text: str) -> bool:
        return ("DONE" in text and ("SUCCESS" in text or " OK" in text)
                and "FAIL:" not in text)

    log_text = ""
    try:
        with open(log_file, encoding="utf-8", errors="replace") as f:
            log_text = f.read()
    except OSError:
        pass

    done_ok = has_done_marker(output) or has_done_marker(log_text)
    success = done_ok and out_etl.exists()
    if not success:
        print(f"\n[FAILED] Check log: {log_file}", file=sys.stderr)
        try:
            with open(log_file, encoding="utf-8", errors="replace") as f:
                print("".join(f.readlines()[:50]), file=sys.stderr)
        except OSError:
            pass
        return 1

    print(f"\n[collect_etl] DONE — ETL written to: {out_etl}")
    print(f"[collect_etl] Next: feed this .etl to the perf-sampling-parser skill.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

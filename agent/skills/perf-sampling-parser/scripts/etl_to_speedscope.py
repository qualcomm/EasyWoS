#!/usr/bin/env python3
"""Export CPU flame graphs from an ETL file using PerfView EtlToSpeedScope.

Locates PerfView relative to this script's directory (../tool/PerfView.exe),
so it works on any machine regardless of install location.

Usage:
    python etl_to_speedscope.py <etl_path> <process_names> [output_dir] [symbol_path]

Arguments:
    etl_path       Path to .etl or .etlx file (local or UNC)
    process_names  Comma-separated process names without .exe (e.g. "chrome,msedge")
    output_dir     Directory for .speedscope.json output (default: etl file directory)
    symbol_path    Extra PDB search path in NT symbol path format (optional)

Exit codes:
    0  success — <name>_<pid>.speedscope.json files written to output_dir
    1  failure — error details in <etl_dir>/temp/pfv_log2.txt
"""

import os
import sys
import subprocess
import pathlib

PERFVIEW = pathlib.Path(__file__).resolve().parent / "PerfView.exe"


def main():
    if len(sys.argv) < 3:
        print("Usage: etl_to_speedscope.py <etl_path> <process_names> [output_dir] [symbol_path]",
              file=sys.stderr)
        sys.exit(1)

    etl_path = sys.argv[1]
    process_names = sys.argv[2]
    output_dir = sys.argv[3] if len(sys.argv) >= 4 else ""
    symbol_path = sys.argv[4] if len(sys.argv) >= 5 else ""

    etl_dir = os.path.dirname(etl_path) or "."
    if not output_dir:
        output_dir = etl_dir

    temp_dir = os.path.join(etl_dir, "temp")
    os.makedirs(temp_dir, exist_ok=True)

    log_file = os.path.join(temp_dir, "pfv_log2.txt")
    out_file = os.path.join(temp_dir, "pfv_speedscope_out.txt")
    # PerfView APPENDS to /LogFile:, so a stale "DONE ... SUCCESS" from an earlier
    # run would be misread as this run's success marker. Start from a clean log.
    try:
        os.remove(log_file)
    except OSError:
        pass

    cmd = [
        str(PERFVIEW),
        "/AcceptEULA",
        "/NoGui",
        f"/LogFile:{log_file}",
        "UserCommand",
        "EtlToSpeedScope",
        etl_path,
        process_names,
        output_dir,
    ]
    if symbol_path:
        cmd.append(symbol_path)

    result = subprocess.run(cmd, capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    output = (result.stdout or "") + (result.stderr or "")

    with open(out_file, "w", encoding="utf-8") as f:
        f.write(output)
    print(output)

    # PerfView ends its log with "DONE <time> SUCCESS: ..." on success and
    # "DONE <time> FAIL: ..." on failure (older/UserCommand paths may print " OK").
    #
    # With /LogFile: that final DONE line goes to the LOG FILE; stdout only gets a
    # truncated copy that often lacks it entirely. Checking stdout alone therefore
    # reports a false FAILURE on a run that actually succeeded, so check both.
    def has_done_marker(text):
        return ("DONE" in text and ("SUCCESS" in text or " OK" in text)
                and "FAIL:" not in text)

    log_text = ""
    try:
        with open(log_file, encoding="utf-8", errors="replace") as f:
            log_text = f.read()
    except OSError:
        pass

    success = has_done_marker(output) or has_done_marker(log_text)
    if not success:
        print(f"\n[FAILED] Check log: {log_file}", file=sys.stderr)
        try:
            with open(log_file, encoding="utf-8", errors="replace") as f:
                print("".join(f.readlines()[:50]), file=sys.stderr)
        except OSError:
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Run PerfView ProcessTree on an ETL file.

Locates PerfView relative to this script's directory (../tool/PerfView.exe),
so it works on any machine regardless of install location.

Usage:
    python process_tree.py <etl_path> [output_json]

Exit codes:
    0  success — <etl>.processtree.json written
    1  failure — error details in <etl_dir>/temp/pfv_log.txt
"""

import os
import sys
import subprocess
import pathlib

PERFVIEW = pathlib.Path(__file__).resolve().parent / "PerfView.exe"


def main():
    if len(sys.argv) < 2:
        print("Usage: process_tree.py <etl_path> [output_json]", file=sys.stderr)
        sys.exit(1)

    etl_path = sys.argv[1]
    # Fix UNC paths: ensure they start with \\ (not single \)
    if etl_path.startswith("\\") and not etl_path.startswith("\\\\"):
        etl_path = "\\" + etl_path

    etl_dir = os.path.dirname(etl_path) or "."
    temp_dir = os.path.join(etl_dir, "temp")
    os.makedirs(temp_dir, exist_ok=True)

    log_file = os.path.join(temp_dir, "pfv_log.txt")
    out_file = os.path.join(temp_dir, "pfv_proctree_out.txt")
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
        "ProcessTree",
        etl_path,
    ]
    if len(sys.argv) >= 3:
        cmd.append(sys.argv[2])

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

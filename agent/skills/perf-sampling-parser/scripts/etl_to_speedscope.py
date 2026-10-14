#!/usr/bin/env python3
"""Export CPU flame graphs from an ETL file using PerfView EtlToSpeedScope.

Locates PerfView relative to this script's directory (../tool/PerfView.exe),
so it works on any machine regardless of install location.

Usage:
    python etl_to_speedscope.py <etl_path> <process_names> [output_dir] [symbol_path] [--allow-symbol-servers]

Arguments:
    etl_path       Path to .etl or .etlx file (local or UNC)
    process_names  Comma-separated process names without .exe (e.g. "chrome,msedge")
    output_dir     Directory for .speedscope.json output (default: etl file directory)
    symbol_path    Extra local PDB search path in NT symbol path format (optional)
    --allow-symbol-servers
                   Opt in to inherited or explicitly supplied symbol servers.
                   Without this flag, symbol resolution is local-only.

Exit codes:
    0  success — <name>_<pid>.speedscope.json files written to output_dir
    1  failure — error details in <etl_dir>/temp/pfv_log2.txt
"""

import os
import sys
import subprocess
import pathlib
from contextlib import contextmanager
from xml.sax.saxutils import escape

PERFVIEW = pathlib.Path(__file__).resolve().parent / "PerfView.exe"


@contextmanager
def local_only_perfview_config(symbol_path):
    """Temporarily hide PerfView's persisted symbol servers, then restore them."""
    config = pathlib.Path(os.environ["APPDATA"]) / "PerfView" / "UserConfig.xml"
    original = config.read_bytes() if config.exists() else None
    config.parent.mkdir(parents=True, exist_ok=True)
    temporary = config.with_name(f"UserConfig.easywos-{os.getpid()}.tmp")
    temporary.write_text(
        "<?xml version=\"1.0\" encoding=\"utf-8\"?>\n"
        "<ConfigData>\n"
        f"  <_NT_SYMBOL_PATH>{escape(symbol_path)}</_NT_SYMBOL_PATH>\n"
        "  <EULA_Accepted>1</EULA_Accepted>\n"
        "</ConfigData>\n",
        encoding="utf-8",
    )
    os.replace(temporary, config)
    try:
        yield
    finally:
        if original is None:
            config.unlink(missing_ok=True)
        else:
            temporary.write_bytes(original)
            os.replace(temporary, config)


def main():
    raw_args = sys.argv[1:]
    allow_symbol_servers = "--allow-symbol-servers" in raw_args
    raw_args = [arg for arg in raw_args if arg != "--allow-symbol-servers"]

    if len(raw_args) < 2:
        print("Usage: etl_to_speedscope.py <etl_path> <process_names> [output_dir] [symbol_path] [--allow-symbol-servers]",
              file=sys.stderr)
        sys.exit(1)

    etl_path = raw_args[0]
    process_names = raw_args[1]
    output_dir = raw_args[2] if len(raw_args) >= 3 else ""
    symbol_path = raw_args[3] if len(raw_args) >= 4 else ""

    etl_dir = os.path.dirname(etl_path) or "."
    if not output_dir:
        output_dir = etl_dir

    run_env = os.environ.copy()
    if not allow_symbol_servers:
        local_paths = [etl_dir]
        if symbol_path:
            local_paths.extend(part.strip() for part in symbol_path.split(";") if part.strip())
        for entry in local_paths:
            lowered = entry.lower()
            if (entry.startswith("\\\\") or lowered.startswith("srv*")
                    or lowered.startswith("symsrv*") or "http://" in lowered
                    or "https://" in lowered):
                print(f"Local-only mode rejects network symbol path: {entry}", file=sys.stderr)
                sys.exit(1)
        symbol_path = ";".join(dict.fromkeys(local_paths))
        run_env["_NT_SYMBOL_PATH"] = symbol_path
        run_env.pop("_NT_ALT_SYMBOL_PATH", None)

    temp_dir = os.path.join(etl_dir, "temp")
    os.makedirs(temp_dir, exist_ok=True)
    if not allow_symbol_servers:
        isolated_root = os.path.join(temp_dir, "perfview-local-only")
        isolated_temp = os.path.join(isolated_root, "temp")
        os.makedirs(isolated_temp, exist_ok=True)
        run_env.update({
            "APPDATA": isolated_root,
            "LOCALAPPDATA": isolated_root,
            "TEMP": isolated_temp,
            "TMP": isolated_temp,
        })

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

    if allow_symbol_servers:
        result = subprocess.run(cmd, capture_output=True, text=True, env=run_env,
                                encoding="utf-8", errors="replace")
    else:
        with local_only_perfview_config(symbol_path):
            result = subprocess.run(cmd, capture_output=True, text=True, env=run_env,
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

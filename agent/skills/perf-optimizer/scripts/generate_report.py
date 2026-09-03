#!/usr/bin/env python3
"""Phase 3 of the perf-optimizer workflow: build a self-contained HTML report.

Inputs (typically produced by Phase 1 / Phase 2 of this skill):
  - speedscope JSON  (the original profile, used by the embedded speedscope iframe)
  - perf_report.json (output of analyze_speedscope.py)
  - source_analysis.json (optional, output of search_source.py)
  - processtree.json (optional, top-process-by-CPU panel)

Outputs (under --out-dir):
  - report.html        : the dashboard (loads report_data.js + iframes speedscope)
  - report_data.js     : window.REPORT_DATA = {...} with the perf metadata
  - speedscope/        : bundled speedscope app (copy of assets/speedscope)
  - <profile>.speedscope.json : the original profile, copied here so the speedscope
                               server (which serves only files inside its own dir)
                               can find it.

The user then runs:
    node speedscope/server.js <profile>.speedscope.json
    open report.html

The server starts on localhost:8888 and the iframe inside report.html points at it.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

SKILL_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = SKILL_DIR / "assets"
TEMPLATE_PATH = ASSETS_DIR / "report_template.html"
SPEEDSCOPE_BUNDLE = ASSETS_DIR / "speedscope"


def load_json(path: Path | None) -> Any:
    if path is None or not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        # strict=False: the processtree JSON (from Global.dll) can contain raw
        # control chars (e.g. a literal TAB inside a process cmdLine), which the
        # strict parser rejects. Tolerate them so report generation still works.
        return json.load(f, strict=False)


def build_top_processes(proctree: dict | None) -> dict:
    if not proctree:
        return {"totalCpuMs": 0, "processes": []}
    procs = proctree.get("processes", []) or []
    procs = [p for p in procs if (p.get("cpuMSec") or 0) > 0]
    procs.sort(key=lambda p: p.get("cpuMSec", 0), reverse=True)
    procs = procs[:20]
    return {
        "totalCpuMs": proctree.get("totalCpuMSec", 0),
        "processes": [
            {
                "pid": p.get("pid"),
                "name": p.get("name"),
                "cpuMSec": p.get("cpuMSec"),
                "cpuPct": p.get("cpuPct"),
                "cmdLine": p.get("cmdLine") or "",
            }
            for p in procs
        ],
    }


def build_summary(perf: dict, source_analysis: dict | None) -> dict:
    """Synthesise findings + recommended actions from perf + source analysis.

    The report's Final Summary card needs short paragraphs; we derive them from
    objective signals in the perf and source analysis files. The model running
    this skill should override this with --summary-json and --root-cause-json
    once it has done the actual analysis. This default keeps the report useful
    out of the box but is intentionally workload-agnostic — no hardcoded
    "NEON/SSE 内联汇编" or codec-specific guesses.
    """
    findings: list[dict] = []
    actions: list[str] = []

    module_self = (perf or {}).get("module_self_time", []) or []
    hot_fns = (perf or {}).get("hot_functions", []) or []
    unresolved_pct = (perf or {}).get("unresolved_pct", 0) or 0
    fn_findings = ((source_analysis or {}).get("function_findings", []) or [])

    if module_self:
        m = module_self[0]
        findings.append({
            "label": f"主瓶颈模块: {m.get('module')}",
            "text": (
                f"该模块占据 {m.get('self_pct', 0):.2f}% "
                f"({m.get('self_ms', 0):.0f} ms) 的独占 CPU 时间，是首要优化目标。"
            ),
        })

    if hot_fns:
        f = hot_fns[0]
        fn_name = f.get("function") or f.get("frame") or "n/a"
        findings.append({
            "label": f"最热单点函数: {fn_name}",
            "text": (
                f"占 {f.get('self_pct', 0):.2f}% 自耗时（{f.get('self_ms', 0):.0f} ms），"
                f"可疑调用者位于 {f.get('suspect_caller_module') or '未知'} 模块。"
            ),
        })

    with_source = [f for f in fn_findings if f.get("source_available")][:3]
    if with_source:
        joined = "；".join(
            f"{f.get('module')}!{f.get('function')} "
            f"({(f.get('self_pct') or 0):.1f}% self) – 源码根目录 {f.get('source_root')}"
            for f in with_source
        )
        findings.append({
            "label": "已定位源码的热点函数",
            "text": joined + "。",
        })

    if unresolved_pct > 0:
        findings.append({
            "label": "符号未解析占比",
            "text": (
                f"约 {unresolved_pct:.2f}% 的样本未解析到符号，"
                "建议补齐对应模块的 PDB 以提高定位精度。"
            ),
        })

    findings.append({
        "label": "根因待补充",
        "text": (
            "本卡片由 generate_report.py 自动生成，仅基于客观计时数据。"
            "运行 perf-optimizer skill 的模型应当结合源码扫描得出真正的根因，"
            "并通过 --root-cause-json / --summary-json 传入完整诊断结论。"
        ),
    })

    if module_self:
        actions.append(
            f"检查 {module_self[0].get('module')} 的内层热点：自耗时高通常意味着该模块"
            f"自身代码在执行，结合源码扫描确认是算法、数据结构还是缺失的 SIMD 路径。"
        )
    if hot_fns:
        fn_name = hot_fns[0].get("function") or hot_fns[0].get("frame")
        actions.append(
            f"对 {fn_name} 做调用链审计，确认是否存在重复调用、可缓存的中间值或可向量化的循环。"
        )
    actions.append(
        "结合 speedscope Sandwich 视图查看高自耗时函数的调用入口，从顶层模块倒推真正的工作来源。"
    )
    actions.append(
        "运行 search_source.py 后将分析结论结构化，再用 --root-cause-json / --summary-json "
        "重新生成报告，以获得带证据链的 Root Cause Diagnosis 卡片。"
    )

    return {"findings": findings, "actions": actions}


def write_report_data(out_path: Path, data: dict) -> None:
    body = "window.REPORT_DATA = " + json.dumps(data, ensure_ascii=False) + ";\n"
    out_path.write_text(body, encoding="utf-8")


def copy_speedscope_bundle(out_dir: Path, force: bool) -> Path:
    dest = out_dir / "speedscope"
    if dest.exists() and force:
        shutil.rmtree(dest)
    if not dest.exists():
        shutil.copytree(SPEEDSCOPE_BUNDLE, dest)
    return dest


def stage_profile(profile_src: Path, speedscope_dir: Path) -> str:
    """Copy the speedscope JSON into the speedscope dir so server.js can serve it.

    Returns the basename used in the iframe URL.
    """
    dst = speedscope_dir / profile_src.name
    if dst.resolve() != profile_src.resolve():
        shutil.copyfile(profile_src, dst)
    return profile_src.name


def write_embedded_html(speedscope_dir: Path, profile_basename: str) -> str:
    """Generate index-embedded.html with the profile JSON inlined.

    Lets the report iframe show the flame graph straight from a file:// open,
    no node server, no drag-drop. The hashed speedscope-*.js bundle is loaded
    relatively, so the file works as long as it sits next to the bundle.

    Returns the basename of the generated file.
    """
    profile_path = speedscope_dir / profile_basename
    json_text = profile_path.read_text(encoding="utf-8")
    # Prevent </script> inside the JSON from prematurely closing the data tag.
    # JSON allows \/ as an alternative for /, so this round-trips through JSON.parse.
    json_text = json_text.replace("</", "<\\/")

    js_bundle = next(
        (p.name for p in speedscope_dir.glob("speedscope-*.js")),
        "speedscope.js",
    )
    css_bundle = next(
        (p.name for p in speedscope_dir.glob("speedscope-*.css")),
        "speedscope.css",
    )

    html = (
        "<!DOCTYPE html>\n"
        "<html><head><meta charset=\"UTF-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">"
        "<title>speedscope (embedded)</title>"
        f"<link rel=\"stylesheet\" href=\"{css_bundle}\">"
        "</head><body>"
        f"<script src=\"{js_bundle}\"></script>"
        "<script id=\"profileData\" type=\"application/json\">"
        f"{json_text}"
        "</script>"
        "<script>"
        "(function(){"
        f"var profileName={json.dumps(profile_basename)};"
        "var raw=document.getElementById('profileData').textContent;"
        "var iv=setInterval(function(){"
        "if(window.speedscope&&window.speedscope.openFile){"
        "clearInterval(iv);"
        "var blob=new Blob([raw],{type:'application/json'});"
        "var file=new File([blob],profileName,{type:'application/json'});"
        "window.speedscope.openFile(file);"
        "}},80);"
        "setTimeout(function(){clearInterval(iv);},10000);"
        "})();"
        "</script>"
        "</body></html>"
    )
    out_name = "index-embedded.html"
    (speedscope_dir / out_name).write_text(html, encoding="utf-8")
    return out_name


def main() -> int:
    p = argparse.ArgumentParser(description="Generate the perf-optimizer HTML report.")
    p.add_argument("--speedscope", required=True, type=Path,
                   help="Path to the original speedscope JSON (the profile data).")
    p.add_argument("--perf-report", required=True, type=Path,
                   help="Path to <name>.perf_report.json (output of analyze_speedscope.py).")
    p.add_argument("--source-analysis", type=Path, default=None,
                   help="Optional path to <name>.source_analysis.json (output of search_source.py).")
    p.add_argument("--processtree", type=Path, default=None,
                   help="Optional path to a process-tree JSON (e.g., trace.processtree.json).")
    p.add_argument("--root-cause-json", type=Path, default=None,
                   help="Optional JSON file with the model's root-cause diagnosis. "
                        "When provided, renders the 'Root Cause Diagnosis' card with "
                        "evidence chain + ranked fixes. Schema: see SKILL.md Phase 3.")
    p.add_argument("--summary-json", type=Path, default=None,
                   help="Optional JSON file with {findings:[...], actions:[...]} to "
                        "override the auto-generated Final Summary. Use this to put "
                        "the model's actual analysis into the report instead of the "
                        "templated default.")
    p.add_argument("--title", type=str, default=None,
                   help="Optional report title. Defaults to '<speedscope-stem> · CPU 性能根因分析报告'.")
    p.add_argument("--out-dir", required=True, type=Path,
                   help="Destination directory for the assembled report.")
    p.add_argument("--server-port", type=int, default=8888,
                   help="Port the speedscope server listens on (default 8888).")
    p.add_argument("--force", action="store_true",
                   help="Overwrite existing files in --out-dir.")
    args = p.parse_args()

    for label, path in [("speedscope", args.speedscope), ("perf-report", args.perf_report)]:
        if not path.exists():
            print(f"ERROR: --{label} not found: {path}", file=sys.stderr)
            return 2

    if not TEMPLATE_PATH.exists():
        print(f"ERROR: report template missing: {TEMPLATE_PATH}", file=sys.stderr)
        return 2
    if not SPEEDSCOPE_BUNDLE.exists():
        print(f"ERROR: speedscope bundle missing: {SPEEDSCOPE_BUNDLE}", file=sys.stderr)
        return 2

    args.out_dir.mkdir(parents=True, exist_ok=True)

    perf = load_json(args.perf_report) or {}
    source_analysis = load_json(args.source_analysis)
    proctree = load_json(args.processtree)
    root_cause = load_json(args.root_cause_json)
    summary_override = load_json(args.summary_json)

    top_processes = build_top_processes(proctree)
    summary = summary_override if summary_override else build_summary(perf, source_analysis)

    speedscope_dir = copy_speedscope_bundle(args.out_dir, force=args.force)
    profile_basename = stage_profile(args.speedscope, speedscope_dir)
    embedded_html = write_embedded_html(speedscope_dir, profile_basename)

    sources = ["perf_report"]
    if proctree is not None:
        sources.insert(0, "processtree")
    if source_analysis is not None:
        sources.append("source_analysis")
    if root_cause is not None:
        sources.append("root_cause")
    if summary_override is not None:
        sources.append("summary_override")

    meta: dict[str, Any] = {
        "generatedFrom": sources,
        "speedscope": args.speedscope.name,
    }
    if args.title:
        meta["title"] = args.title

    data = {
        "meta": meta,
        "topProcesses": top_processes,
        "perf": perf,
        "summary": summary,
        "speedscopeEmbed": {
            "serverUrl": f"http://localhost:{args.server_port}",
            "autoHtml": "index-auto.html",
            "embeddedHtml": embedded_html,
            "profileFile": profile_basename,
            "profilePath": str(args.speedscope.resolve()),
        },
    }
    if root_cause is not None:
        data["rootCause"] = root_cause

    write_report_data(args.out_dir / "report_data.js", data)
    shutil.copyfile(TEMPLATE_PATH, args.out_dir / "report.html")

    # Final user-facing instructions.
    print(f"[OK] Report generated in: {args.out_dir}")
    print(f"     - report.html")
    print(f"     - report_data.js  ({(args.out_dir / 'report_data.js').stat().st_size // 1024} KB)")
    print(f"     - speedscope/     (bundled app, including {profile_basename})")
    print()
    print("Next steps:")
    print(f"  1. Start the speedscope server (the profile is already staged in speedscope/):")
    print(f"        cd \"{speedscope_dir}\"")
    print(f"        node server.js")
    print(f"  2. Open: {args.out_dir / 'report.html'}")
    print()
    print("The flame-graph card in the report iframes")
    print(f"  http://localhost:{args.server_port}/index-auto.html?file={profile_basename}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

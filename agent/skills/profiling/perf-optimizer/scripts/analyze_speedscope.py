#!/usr/bin/env python3
"""
analyze_speedscope.py - Analyze a SpeedScope JSON file for performance bottlenecks.

Finds the true root cause of hot functions by tracing call chains:
  e.g.  ucrtbase!fminf is the hot leaf, but qt6webenginecore is the real culprit
        because it calls scalar math instead of NEON SIMD.

Output:
  - stdout: human-readable summary
  - <input>.perf_report.json: structured JSON for downstream analysis

Usage:
    python analyze_speedscope.py <speedscope.json> [--top-n 20] [--out report.json]
"""

import json
import sys
import argparse
import re
from collections import defaultdict
from pathlib import Path


# ── Module name extraction ────────────────────────────────────────────────────

def get_module(frame_name: str) -> str:
    if '!' in frame_name:
        return frame_name.split('!')[0].lower()
    if frame_name.strip() in ('?', '??', '', 'UNKNOWN'):
        return '??'
    return frame_name.lower()


def get_function(frame_name: str) -> str:
    if '!' in frame_name:
        func = frame_name.split('!', 1)[1]
        return func.lstrip('#')   # strip PerfView symbol decorators like #fmaxf
    return frame_name


def is_meta_frame(frame_name: str) -> bool:
    """Return True for PerfView synthetic frames (Process64, Thread containers)."""
    low = frame_name.lower()
    return (low.startswith('process64 ') or
            low.startswith('process32 ') or
            low.startswith('thread (') or
            low.startswith('process ('))


def dedup_modules(chain: list) -> list:
    """Remove consecutive duplicate modules (inlined frames within same module)."""
    result = []
    prev = None
    for m in chain:
        if m != prev:
            result.append(m)
            prev = m
    return result


# ── Optimization classification ───────────────────────────────────────────────

SYSTEM_MODULES = {
    'ntdll', 'kernelbase', 'kernel32', 'ucrtbase', 'ucrtbased',
    'vcruntime140', 'vcruntime140d', 'msvcrt', 'msvcp140', 'msvcp_win',
    'user32', 'gdi32', 'win32u', 'advapi32', 'sechost', 'rpcrt4',
    'combase', 'ole32', 'oleaut32', 'shell32', 'shlwapi', 'ws2_32',
    'clr', 'coreclr', 'mscorlib', 'system', '??',
}


# ── Core analysis ─────────────────────────────────────────────────────────────

def find_suspect_module(chain: list) -> str | None:
    """
    Walk the call chain backwards (excluding leaf module) to find
    the first non-system module — the real culprit that chose to call
    the expensive leaf function.
    """
    if len(chain) < 2:
        return None
    for m in reversed(chain[:-1]):  # skip leaf module itself
        if m not in SYSTEM_MODULES:
            return m
    # All are system modules — return immediate caller
    return chain[-2] if len(chain) >= 2 else None


def _process_evented_profile(profile, frames,
                              frame_self, frame_incl,
                              module_incl, module_self,
                              call_graph, leaf_chains,
                              leaf_direct_callers):
    """Process a SpeedScope 'evented' profile (O/C events with timestamps)."""
    thread_name = profile.get('name', 'unknown')
    events = profile.get('events', [])

    # stack entries: (frame_idx, open_time, child_time_accumulated)
    stack = []
    # parallel stack of module-chain tuples captured at open time
    chain_stack = []

    thread_self_local = defaultdict(float)
    thread_total = 0.0

    for event in events:
        etype = event.get('type')
        fi    = event.get('frame', 0)
        at    = event.get('at', 0.0)

        if etype == 'O':
            # Build module chain including this new frame
            parent_chain = chain_stack[-1] if chain_stack else ()
            new_mod = get_module(frames[fi]['name'])
            # Append to deduped chain
            if parent_chain and parent_chain[-1] == new_mod:
                new_chain = parent_chain
            else:
                new_chain = parent_chain + (new_mod,)
            # Keep last 6 modules
            new_chain = new_chain[-6:]

            stack.append((fi, at, 0.0))
            chain_stack.append(new_chain)

        elif etype == 'C' and stack:
            frame_idx, open_time, child_time = stack.pop()
            chain_key = chain_stack.pop()

            duration = max(0.0, at - open_time)
            self_ms  = max(0.0, duration - child_time)

            thread_total           += self_ms
            frame_self[frame_idx]  += self_ms
            thread_self_local[frame_idx] += self_ms
            frame_incl[frame_idx]  += duration

            mod = get_module(frames[frame_idx]['name'])
            fname = frames[frame_idx]['name']
            is_meta = is_meta_frame(fname)

            if not is_meta:
                module_self[mod]   += self_ms
                module_incl[mod]   += duration

            # Call graph edge: parent module -> this module (skip meta frames)
            if stack:
                parent_fname = frames[stack[-1][0]]['name']
                parent_mod = get_module(parent_fname)
                if not is_meta and not is_meta_frame(parent_fname) and parent_mod != mod:
                    call_graph[(parent_mod, mod)] += duration
                # Accumulate into parent's child_time always (so self_ms is accurate)
                pi, pt, pc = stack[-1]
                stack[-1] = (pi, pt, pc + duration)

            # Call chain for leaf attribution (self_ms > 0 = leaf-like)
            if self_ms > 0:
                leaf_chains[frame_idx][chain_key] += self_ms
                # Record immediate non-meta caller at frame level
                for j in range(len(stack) - 1, -1, -1):
                    caller_fname = frames[stack[j][0]]['name']
                    if not is_meta_frame(caller_fname):
                        leaf_direct_callers[frame_idx][caller_fname] += self_ms
                        break

    return thread_name, thread_total, thread_self_local


def _process_sampled_profile(profile, frames,
                              frame_self, frame_incl,
                              module_incl, module_self,
                              call_graph, leaf_chains,
                              leaf_direct_callers):
    """Process a SpeedScope 'sampled' profile (sample arrays + weights)."""
    thread_name = profile.get('name', 'unknown')
    samples  = profile.get('samples', [])
    weights  = profile.get('weights', [])
    thread_total = sum(weights)

    thread_self_local = defaultdict(float)

    for sample, weight in zip(samples, weights):
        if not sample:
            continue

        leaf_idx = sample[-1]

        frame_self[leaf_idx]           += weight
        thread_self_local[leaf_idx]    += weight

        seen = set()
        for fi in sample:
            if fi not in seen:
                frame_incl[fi] += weight
                seen.add(fi)

        mod_chain = [get_module(frames[fi]['name']) for fi in sample]
        seen_mods = set()
        for m in mod_chain:
            if m not in seen_mods:
                module_incl[m] += weight
                seen_mods.add(m)

        module_self[get_module(frames[leaf_idx]['name'])] += weight

        deduped = dedup_modules(mod_chain)
        for i in range(len(deduped) - 1):
            call_graph[(deduped[i], deduped[i + 1])] += weight

        chain_key = tuple(deduped[-6:])
        leaf_chains[leaf_idx][chain_key] += weight

        # Record immediate non-meta caller at frame level
        for i in range(len(sample) - 2, -1, -1):
            caller_fname = frames[sample[i]]['name']
            if not is_meta_frame(caller_fname):
                leaf_direct_callers[leaf_idx][caller_fname] += weight
                break

    return thread_name, thread_total, thread_self_local


def analyze(speedscope_path: str, top_n: int = 20) -> dict:
    with open(speedscope_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    frames   = data['shared']['frames']
    profiles = data.get('profiles', [])

    total_cpu_ms = 0.0
    thread_stats = []

    # Global accumulators (all threads)
    frame_self  = defaultdict(float)
    frame_incl  = defaultdict(float)
    module_incl = defaultdict(float)
    module_self = defaultdict(float)
    call_graph  = defaultdict(float)
    leaf_chains = defaultdict(lambda: defaultdict(float))
    leaf_direct_callers = defaultdict(lambda: defaultdict(float))

    for profile in profiles:
        ptype = profile.get('type', '')
        if ptype == 'evented':
            name, thread_total, local = _process_evented_profile(
                profile, frames,
                frame_self, frame_incl, module_incl, module_self,
                call_graph, leaf_chains, leaf_direct_callers)
        elif ptype == 'sampled':
            name, thread_total, local = _process_sampled_profile(
                profile, frames,
                frame_self, frame_incl, module_incl, module_self,
                call_graph, leaf_chains, leaf_direct_callers)
        else:
            continue

        total_cpu_ms += thread_total
        thread_stats.append({
            'name':       name,
            'total_ms':   thread_total,
            'pct':        0.0,  # filled after total is known
            'top_self': sorted(
                [{'frame': frames[i]['name'], 'self_ms': v} for i, v in local.items()],
                key=lambda x: -x['self_ms']
            )[:8],
        })

    # Fill pct now that total is known
    for t in thread_stats:
        t['pct'] = t['total_ms'] / total_cpu_ms * 100 if total_cpu_ms else 0

    thread_stats.sort(key=lambda t: -t['total_ms'])

    # Unresolved symbol coverage
    unresolved_ms = module_self.get('??', 0.0)
    unresolved_pct = unresolved_ms / total_cpu_ms * 100 if total_cpu_ms else 0

    # Top modules (filter meta/process/thread frames)
    top_mod_incl = sorted(
        [{'module': m, 'inclusive_ms': v,
          'inclusive_pct': v / total_cpu_ms * 100 if total_cpu_ms else 0}
         for m, v in module_incl.items() if not is_meta_frame(m)],
        key=lambda x: -x['inclusive_ms']
    )[:top_n]

    top_mod_self = sorted(
        [{'module': m, 'self_ms': v,
          'self_pct': v / total_cpu_ms * 100 if total_cpu_ms else 0}
         for m, v in module_self.items() if not is_meta_frame(m)],
        key=lambda x: -x['self_ms']
    )[:top_n]

    # Hot functions with call chains (skip meta/process/thread container frames)
    hot_functions = []
    for fi, self_ms in sorted(frame_self.items(), key=lambda x: -x[1])[:top_n * 2]:
        fname   = frames[fi]['name']
        if is_meta_frame(fname):
            continue
        func    = get_function(fname)
        module  = get_module(fname)
        incl_ms = frame_incl.get(fi, self_ms)

        chains     = leaf_chains[fi]
        top_chains = sorted(chains.items(), key=lambda x: -x[1])[:5]

        # Find the real culprit module
        suspect = None
        if top_chains:
            best_chain, _ = top_chains[0]
            # Filter meta modules out of the chain before finding suspect
            real_chain = [m for m in best_chain if not is_meta_frame(m)]
            suspect = find_suspect_module(real_chain)

        # Top direct caller frames (frame-level, not module-level)
        callers = leaf_direct_callers[fi]
        top_callers = sorted(callers.items(), key=lambda x: -x[1])[:5]

        hot_functions.append({
            'frame':                 fname,
            'module':                module,
            'function':              func,
            'self_ms':               self_ms,
            'self_pct':              self_ms / total_cpu_ms * 100 if total_cpu_ms else 0,
            'inclusive_ms':          incl_ms,
            'suspect_caller_module': suspect,
            'top_caller_frames': [
                {'frame':      f,
                 'weight_ms':  w,
                 'weight_pct': w / total_cpu_ms * 100 if total_cpu_ms else 0}
                for f, w in top_callers
                if not is_meta_frame(f)
            ],
            'top_call_chains': [
                {'chain':      [m for m in c if not is_meta_frame(m)],
                 'weight_ms':  w,
                 'weight_pct': w / total_cpu_ms * 100 if total_cpu_ms else 0}
                for c, w in top_chains
            ],
        })
        if len(hot_functions) >= top_n:
            break

    # Call graph top edges (filter meta modules)
    top_edges = sorted(
        [{'caller': k[0], 'callee': k[1], 'weight_ms': v,
          'weight_pct': v / total_cpu_ms * 100 if total_cpu_ms else 0}
         for k, v in call_graph.items()
         if not is_meta_frame(k[0]) and not is_meta_frame(k[1])],
        key=lambda x: -x['weight_ms']
    )[:top_n]

    # Non-system modules appearing in top hot functions (for user to provide source)
    suspect_modules = sorted(
        {f['suspect_caller_module'] for f in hot_functions[:10]
         if f.get('suspect_caller_module') and f['suspect_caller_module'] not in SYSTEM_MODULES}
        | {f['module'] for f in hot_functions[:10]
           if f['module'] not in SYSTEM_MODULES and f['module'] != '??'}
    )

    return {
        'source_file':           str(speedscope_path),
        'total_cpu_ms':          total_cpu_ms,
        'thread_count':          len(thread_stats),
        'unresolved_pct':        unresolved_pct,
        'top_threads':           thread_stats[:3],
        'module_inclusive_time': top_mod_incl,
        'module_self_time':      top_mod_self,
        'hot_functions':         hot_functions,
        'module_call_graph_top': top_edges,
        'modules_needing_source': suspect_modules,
    }


# ── Human-readable report ─────────────────────────────────────────────────────

def format_report(report: dict) -> str:
    W = 72
    lines = []

    def sep(ch='─'): lines.append(ch * W)
    def h(title): sep(); lines.append(f"  {title}"); sep()

    h("SpeedScope Performance Analysis")
    lines.append(f"  File  : {report['source_file']}")
    lines.append(f"  CPU   : {report['total_cpu_ms']:.0f} ms total  |  "
                 f"Threads: {report['thread_count']}")
    if report['unresolved_pct'] > 5:
        lines.append(f"  ⚠  {report['unresolved_pct']:.1f}% CPU in unresolved frames "
                     f"— PDB coverage may be incomplete")
    sep()

    lines.append("\n▸ Top Threads by CPU")
    for t in report['top_threads']:
        lines.append(f"   {t['pct']:5.1f}%  {t['total_ms']:7.0f} ms  {t['name']}")

    lines.append("\n▸ Module Inclusive Time (Top 15)")
    for m in report['module_inclusive_time'][:15]:
        lines.append(f"   {m['inclusive_pct']:5.1f}%  {m['inclusive_ms']:7.0f} ms  {m['module']}")

    lines.append("\n▸ Module Self Time (Top 10)")
    for m in report['module_self_time'][:10]:
        lines.append(f"   {m['self_pct']:5.1f}%  {m['self_ms']:7.0f} ms  {m['module']}")

    lines.append("\n▸ Top Functions by Self Time (Flat List)")
    for func in report['hot_functions']:
        lines.append(f"   {func['self_pct']:5.1f}%  {func['self_ms']:7.0f} ms  {func['frame']}")

    lines.append("\n▸ Hot Functions with Call Chain Attribution (Top 20)")
    lines.append("  (self% = exclusive CPU;  chain = module path;  callers = direct caller functions)")
    for func in report['hot_functions'][:20]:
        suspect_tag = (f"  ← ROOT CAUSE: {func['suspect_caller_module']}"
                       if func['suspect_caller_module']
                          and func['suspect_caller_module'] != func['module']
                       else "")
        lines.append(f"\n  {func['self_pct']:5.1f}% self  {func['self_ms']:6.0f}ms  "
                     f"{func['frame']}{suspect_tag}")
        for ci in func['top_call_chains'][:3]:
            chain_str = ' → '.join(ci['chain'])
            lines.append(f"      {ci['weight_pct']:4.1f}%  {chain_str}")
        if func.get('top_caller_frames'):
            callers_str = ',  '.join(
                f"{c['frame']} ({c['weight_pct']:.1f}%)"
                for c in func['top_caller_frames'][:3]
            )
            lines.append(f"    callers: {callers_str}")

    lines.append("\n▸ Module Call Graph — Top 15 Edges")
    for e in report['module_call_graph_top'][:15]:
        lines.append(f"   {e['weight_pct']:5.1f}%  {e['weight_ms']:6.0f}ms  "
                     f"{e['caller']}  →  {e['callee']}")

    if report['modules_needing_source']:
        lines.append("\n▸ Modules to Investigate (provide source paths for Phase 2)")
        for m in report['modules_needing_source']:
            lines.append(f"   • {m}")
        lines.append("\n  Usage:  python search_source.py <report.json> "
                     "--sources \"module1=C:\\src\\mod1;module2=\\\\server\\share\\mod2\"")

    sep()
    return '\n'.join(lines)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    # Force UTF-8 output on Windows console
    import sys
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    parser = argparse.ArgumentParser(
        description='Analyze SpeedScope JSON for performance bottlenecks with call-chain attribution')
    parser.add_argument('speedscope', help='Path to speedscope.json')
    parser.add_argument('--top-n', type=int, default=20,
                        help='Top N results per section (default: 20)')
    parser.add_argument('--out', help='Output JSON report path (default: <input>.perf_report.json)')
    args = parser.parse_args()

    report  = analyze(args.speedscope, args.top_n)
    print(format_report(report))

    # foo.speedscope.json -> foo.perf_report.json
    out_path = args.out or re.sub(r'\.speedscope\.json$', '.perf_report.json', str(args.speedscope))
    if out_path == str(args.speedscope):  # no substitution happened
        out_path = str(Path(args.speedscope).with_suffix('').with_suffix('.perf_report.json'))

    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n[Report saved to: {out_path}]")


if __name__ == '__main__':
    main()

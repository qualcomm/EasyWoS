#!/usr/bin/env python3
"""
search_source.py - Search source code for hot functions and detect ARM64 optimization gaps.

Given a perf_report.json (from analyze_speedscope.py) and user-provided source path mappings,
this script:
  1. Searches for hot function names in source files
  2. Detects files where x64 SIMD (SSE/AVX) exists but ARM64 NEON is absent
  3. Detects NEON-blocking compile guards (MSVC / platform ifdefs)
  4. Outputs raw findings — model interprets and brainstorms optimizations

Usage:
    python search_source.py <report.json> --sources "module1=C:\\src;module2=\\\\server\\share\\src2"
"""

import json
import sys
import argparse
import re
import os
from pathlib import Path
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor


# ── Constants ─────────────────────────────────────────────────────────────────

SOURCE_EXTENSIONS = {'.c', '.cpp', '.cc', '.cxx', '.h', '.hpp', '.hxx', '.inl', '.inc', '.mm',
                     '.s', '.asm', '.nasm'}

SKIP_DIRS = {'build', '.git', 'obj', 'out', '__pycache__', '.vs', 'Debug', 'Release',
             'x64', 'arm64', 'CMakeFiles', 'node_modules', '.cache'}

# ARM64 NEON presence indicators
NEON_PRESENT_PATTERNS = [
    r'\b__ARM_NEON\b',
    r'\b_M_ARM64\b',
    r'\b__aarch64__\b',
    r'#\s*include\s+[<"]arm_neon\.h[>"]',
    r'#\s*include\s+[<"]arm64_neon\.h[>"]',
    r'\bfloat32x[248]_t\b',
    r'\bint32x[248]_t\b',
    r'\buint32x[248]_t\b',
    r'\bvmaxq_f32\b|\bvminq_f32\b|\bvmulq_f32\b|\bvaddq_f32\b',
    r'\bvld1q_f32\b|\bvst1q_f32\b|\bvsqrtq_f32\b',
    r'\bvdupq_n_f32\b|\bvcvtq_f32_s32\b',
]

# x64 SIMD presence indicators (SSE / AVX)
X64_SIMD_PATTERNS = [
    r'\b__SSE2__\b', r'\b__SSE4_1__\b', r'\b__AVX2__\b', r'\b__AVX__\b',
    r'\b_M_AMD64\b', r'\b_M_X64\b', r'\b__x86_64__\b',
    r'\b_mm256_\w+\s*\(',
    r'\b_mm_\w+\s*\(',
    r'\b__m256[di]?\b', r'\b__m128[di]?\b',
    r'#\s*include\s+[<"]immintrin\.h[>"]',
    r'#\s*include\s+[<"]emmintrin\.h[>"]',
    r'#\s*include\s+[<"]smmintrin\.h[>"]',
    r'#\s*include\s+[<"]avxintrin\.h[>"]',
]

# Patterns that may BLOCK NEON even when code exists
NEON_BLOCK_PATTERNS = [
    (r'#\s*ifdef\s+_MSC_VER',                    'MSVC-only block may skip NEON path'),
    (r'#\s*ifndef\s+__ARM_NEON',                 'Block guarded by missing __ARM_NEON'),
    (r'#\s*if\s+!defined\(__ARM_NEON\)',          'Explicit NEON disable guard'),
    (r'#\s*if\s+defined\(_WIN32\)\s*&&\s*!defined\(__ARM',
                                                  'Win32 guard without ARM exception'),
    (r'#\s*if\s+defined\(__GNUC__\)',             'GCC-only block may exclude MSVC ARM64'),
    (r'#\s*ifndef\s+_MSC_VER',                   'Non-MSVC block may exclude MSVC ARM64'),
    (r'//\s*(TODO|FIXME|HACK).*(?:neon|simd|arm)',
                                                  'TODO/FIXME comment about NEON/SIMD'),
    (r'//\s*(?:neon|simd).{0,40}(?:not|no|without|disabled|skip)',
                                                  'Comment suggesting NEON is disabled'),
]

# Scalar math functions that could benefit from NEON vectorization
SCALAR_MATH_RE = re.compile(
    r'\b(fminf|fmaxf|sqrtf|sinf|cosf|fabsf|floorf|ceilf|roundf|truncf|'
    r'powf|expf|logf|log2f|atan2f|hypotf|copysignf)\s*\('
)

NEON_COMPILED_RE  = re.compile('|'.join(NEON_PRESENT_PATTERNS))
X64_SIMD_COMPILED_RE = re.compile('|'.join(X64_SIMD_PATTERNS))

# ── Assembly-specific patterns (case-insensitive; GAS lowercase + MASM uppercase) ──

# ARM64 NEON assembly: vector register notation, reduction ops, load/store, directives
NEON_ASM_PATTERNS = [
    r'\bv\d{1,2}\.(8b|16b|4h|8h|2s|4s|1d|2d)\b',  # vector registers: v0.4s, v1.2d
    r'\b(fmaxv|fminv|addv|smaxv|umaxv|sminv|uminv)\b',  # NEON horizontal reductions
    r'\bld[1234]\s+\{',             # vector load: ld1 {v0.4s, ...}
    r'\bst[1234]\s+\{',             # vector store: st1 {v0.4s, ...}
    r'\.arch\s+\S*\+simd',          # .arch armv8-a+simd
    r'\.fpu\s+neon',                # .fpu neon
    r'\bfmla\b|\bfmls\b|\bfmul\b.*\bv\d',  # NEON FMA / fmul with vector dst
]

# x64 SIMD assembly: register names, SSE/AVX instructions, Intel-syntax directive
X64_SIMD_ASM_PATTERNS = [
    r'\b[xy]mm\d{1,2}\b',          # xmm0-xmm15, ymm0-ymm15 registers
    r'\bzmm\d{1,2}\b',             # zmm (AVX-512)
    r'\bv?(movdqu|movdqa|movaps|movups)\b',
    r'\bv?(maxps|minps|addps|mulps|subps|sqrtps)\b',
    r'\bv?(maxpd|minpd|addpd|mulpd|subpd|sqrtpd)\b',
    r'\bv?(paddd|paddw|pmaxsd|pminsd|pmaxud|pminud)\b',
    r'\bvpbroadcast[bdwq]\b',      # AVX2 broadcast
    r'\.intel_syntax\b',           # GAS Intel-syntax switch
]

NEON_ASM_RE     = re.compile('|'.join(NEON_ASM_PATTERNS),     re.IGNORECASE)
X64_SIMD_ASM_RE = re.compile('|'.join(X64_SIMD_ASM_PATTERNS), re.IGNORECASE)

ASM_EXTENSIONS = {'.s', '.asm', '.nasm'}


# ── Source scanning utilities ─────────────────────────────────────────────────

def iter_source_files(src_root: str):
    """Walk source tree, yield absolute file paths."""
    for root_dir, dirs, files in os.walk(src_root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fname in files:
            if Path(fname).suffix.lower() in SOURCE_EXTENSIONS:
                yield os.path.join(root_dir, fname)


def read_file_safe(path: str) -> str | None:
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()
    except Exception:
        return None


def build_file_cache(src_root: str, max_workers: int = 16) -> dict[str, str]:
    """Read all source files in parallel; returns path → content mapping."""
    paths = list(iter_source_files(src_root))
    print(f"[Caching {len(paths)} files from {src_root} ...]", flush=True)

    def _read(p: str) -> tuple[str, str | None]:
        return p, read_file_safe(p)

    with ThreadPoolExecutor(max_workers=max_workers) as exe:
        pairs = exe.map(_read, paths)
    return {p: c for p, c in pairs if c is not None}


def extract_search_terms(func_name: str) -> list[str]:
    """
    Extract searchable identifiers from a C++ function name.
    e.g. 'QWebEngineProfile::download' → ['QWebEngineProfile::download', 'download']
         'anonymous namespace::foo'     → ['foo']
    """
    terms = []

    # Strip template args: Foo<Bar> → Foo
    clean = re.sub(r'<[^>]*>', '', func_name).strip()

    # Candidates: full name, last component after ::
    candidates = [func_name, clean]
    if '::' in clean:
        last = clean.split('::')[-1].strip()
        if last and last not in ('anonymous namespace', ''):
            candidates.append(last)

    # Remove operator/destructor noise
    seen = set()
    for c in candidates:
        c = c.strip()
        if len(c) > 2 and c not in seen:
            seen.add(c)
            terms.append(c)

    return terms


def search_function(src_root: str, func_name: str, max_results: int = 15,
                    file_cache: dict[str, str] | None = None) -> list[dict]:
    """Search for function occurrences in source tree."""
    terms = extract_search_terms(func_name)
    results = []
    seen_locations = set()

    for term in terms:
        if len(term) < 3:
            continue
        pattern = re.compile(re.escape(term))
        # file_cache.items() is a re-iterable dict view; fallback reads fresh each term
        items = (file_cache.items() if file_cache is not None
                 else ((fpath, read_file_safe(fpath)) for fpath in iter_source_files(src_root)))
        for fpath, content in items:
            if not content or term not in content:
                continue
            for lineno, line in enumerate(content.splitlines(), 1):
                if pattern.search(line):
                    key = (fpath, lineno)
                    if key not in seen_locations:
                        seen_locations.add(key)
                        results.append({
                            'file': fpath,
                            'line': lineno,
                            'content': line.strip()[:120],
                            'term': term,
                        })
                        if len(results) >= max_results:
                            return results
    return results


def scan_arm64_gaps(src_root: str, file_cache: dict[str, str] | None = None) -> dict:
    """
    ARM64 gap scan: find files where x64 SIMD exists but ARM64 NEON is absent.

    Returns:
      - files_x64_only:    have x64 SIMD (SSE/AVX) but NO ARM64 NEON  ← priority targets
      - files_neon_only:   have ARM64 NEON but no x64 SIMD
      - files_both:        have both x64 SIMD and ARM64 NEON (well-ported)
      - files_scalar_only: no SIMD at all, but use scalar math functions
      - blocking_findings: guards that may prevent NEON on MSVC/Windows ARM64
    """
    files_x64_only    = []
    files_neon_only   = []
    files_both        = []
    files_scalar_only = []
    blocking_findings = []
    file_count        = 0

    block_patterns_compiled = [
        (re.compile(pat, re.IGNORECASE), desc)
        for pat, desc in NEON_BLOCK_PATTERNS
    ]

    for fpath, content in (file_cache.items() if file_cache is not None
                           else ((p, read_file_safe(p)) for p in iter_source_files(src_root))):
        if content is None:
            continue
        file_count += 1

        has_neon      = bool(NEON_COMPILED_RE.search(content))
        has_x64_simd  = bool(X64_SIMD_COMPILED_RE.search(content))
        scalar_matches = SCALAR_MATH_RE.findall(content)
        has_scalar    = len(scalar_matches) > 0

        # Assembly files use different syntax — augment with asm-specific patterns
        if Path(fpath).suffix.lower() in ASM_EXTENSIONS:
            has_neon     = has_neon     or bool(NEON_ASM_RE.search(content))
            has_x64_simd = has_x64_simd or bool(X64_SIMD_ASM_RE.search(content))

        if has_x64_simd and has_neon:
            files_both.append(fpath)
        elif has_x64_simd and not has_neon:
            files_x64_only.append({
                'file': fpath,
                'scalar_calls': list(set(scalar_matches))[:8],
            })
        elif has_neon and not has_x64_simd:
            files_neon_only.append(fpath)
        elif has_scalar:
            files_scalar_only.append({
                'file': fpath,
                'scalar_calls': list(set(scalar_matches))[:8],
            })

        # Check for blocking patterns regardless of SIMD state
        for pattern, desc in block_patterns_compiled:
            for lineno, line in enumerate(content.splitlines(), 1):
                if pattern.search(line):
                    blocking_findings.append({
                        'file':        fpath,
                        'line':        lineno,
                        'content':     line.strip()[:100],
                        'description': desc,
                    })
                    break  # one finding per file per pattern

    return {
        'file_count':         file_count,
        'files_x64_only':     files_x64_only[:20],      # x64 SIMD, no ARM64 NEON → gaps
        'files_neon_only':    files_neon_only[:10],      # ARM64 NEON, no x64 SIMD
        'files_both':         files_both[:10],           # both → well-ported reference
        'files_scalar_only':  files_scalar_only[:20],   # no SIMD at all
        'blocking_findings':  blocking_findings[:30],
        'summary': {
            'x64_only_count':   len(files_x64_only),
            'neon_only_count':  len(files_neon_only),
            'both_count':       len(files_both),
            'scalar_only_count': len(files_scalar_only),
            'blocking_count':   len(blocking_findings),
        },
    }


# ── Main analysis ─────────────────────────────────────────────────────────────

def analyze_with_sources(report_path: str, source_map: dict) -> dict:
    with open(report_path, 'r', encoding='utf-8') as f:
        report = json.load(f)

    function_findings = []
    arm64_gap_scans   = {}

    # ── Build file caches once per source root (parallel reads) ──────────────
    file_caches: dict[str, dict[str, str]] = {}
    for mod_name, src_path in source_map.items():
        if os.path.exists(src_path):
            file_caches[src_path] = build_file_cache(src_path)
        else:
            file_caches[src_path] = {}

    # ── Per-module ARM64 gap scan ─────────────────────────────────────────────
    for mod_name, src_path in source_map.items():
        if not os.path.exists(src_path):
            arm64_gap_scans[mod_name] = {'error': f'Path not found: {src_path}'}
            continue
        print(f"[Scanning ARM64 gaps: {mod_name} @ {src_path}]", flush=True)
        arm64_gap_scans[mod_name] = scan_arm64_gaps(src_path, file_caches.get(src_path))

    # ── Per-function source search ────────────────────────────────────────────
    for func in report['hot_functions'][:30]:
        module    = func['module'].lower()
        func_name = func['function']

        src_root = None
        for src_mod, src_path in source_map.items():
            if src_mod.lower() in module or module in src_mod.lower():
                src_root = src_path
                break

        if not src_root or not os.path.exists(src_root):
            function_findings.append({
                'module':           module,
                'function':         func_name,
                'self_ms':          func['self_ms'],
                'self_pct':         func['self_pct'],
                'source_available': False,
                'call_chains':      func['top_call_chains'][:2],
                'caller_frames':    func.get('top_caller_frames', [])[:3],
            })
            continue

        print(f"[Searching: {func_name} in {src_root}]", flush=True)
        occurrences = search_function(src_root, func_name,
                                      file_cache=file_caches.get(src_root))

        function_findings.append({
            'module':           module,
            'function':         func_name,
            'self_ms':          func['self_ms'],
            'self_pct':         func['self_pct'],
            'source_available': True,
            'source_root':      src_root,
            'occurrences':      occurrences,
            'call_chains':      func['top_call_chains'][:3],
            'caller_frames':    func.get('top_caller_frames', [])[:3],
        })

    return {
        'function_findings': function_findings,
        'arm64_gap_scans':   arm64_gap_scans,
    }


# ── Human-readable output ─────────────────────────────────────────────────────

def format_source_report(result: dict) -> str:
    W = 72
    lines = []

    def sep(): lines.append('─' * W)

    sep()
    lines.append("  Source Code Analysis — Windows ARM64 Optimization Gaps")
    sep()

    # ARM64 gap scan summary
    if result['arm64_gap_scans']:
        lines.append("\n▸ ARM64 Gap Scan (x64 SIMD vs ARM64 NEON)")
        for mod, scan in result['arm64_gap_scans'].items():
            if 'error' in scan:
                lines.append(f"   {mod}: ERROR — {scan['error']}")
                continue
            s = scan['summary']
            lines.append(f"\n   Module : {mod}  ({scan['file_count']} source files scanned)")
            lines.append(f"   x64 SIMD only (no ARM64 NEON)  : {s['x64_only_count']:3d}  ← ARM64 gaps")
            lines.append(f"   Both x64 SIMD + ARM64 NEON     : {s['both_count']:3d}  (well-ported)")
            lines.append(f"   ARM64 NEON only (no x64 SIMD)  : {s['neon_only_count']:3d}")
            lines.append(f"   Scalar only (no SIMD at all)   : {s['scalar_only_count']:3d}")
            lines.append(f"   Blocking guard patterns        : {s['blocking_count']:3d}")

            if scan['files_x64_only']:
                lines.append("\n   [GAP] Files with x64 SIMD but missing ARM64 NEON:")
                for e in scan['files_x64_only'][:6]:
                    lines.append(f"     {e['file']}")
                    if e['scalar_calls']:
                        lines.append(f"       scalar calls: {', '.join(e['scalar_calls'])}")

            if scan['blocking_findings']:
                lines.append("\n   [GUARD] Patterns that may block NEON on MSVC/Windows ARM64:")
                for b in scan['blocking_findings'][:6]:
                    lines.append(f"     {b['file']}:{b['line']}  [{b['description']}]")
                    lines.append(f"       {b['content']}")

            if scan['files_both']:
                lines.append("\n   [REF] Well-ported files (both x64 + ARM64, use as reference):")
                for f in scan['files_both'][:4]:
                    lines.append(f"     {f}")

    # Function search results
    found = [f for f in result['function_findings']
             if f.get('source_available') and f.get('occurrences')]
    if found:
        lines.append("\n▸ Hot Function Locations in Source")
        for ff in found[:15]:
            lines.append(f"\n  {ff['self_pct']:.1f}%  {ff['module']}!{ff['function']}")
            if ff.get('caller_frames'):
                callers = ',  '.join(
                    f"{c['frame']} ({c['weight_pct']:.1f}%)"
                    for c in ff['caller_frames'][:3]
                )
                lines.append(f"    called by: {callers}")
            for occ in ff['occurrences'][:4]:
                lines.append(f"    {occ['file']}:{occ['line']}")
                lines.append(f"      {occ['content']}")

    sep()
    return '\n'.join(lines)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='Search source code for hot functions and NEON optimization gaps')
    parser.add_argument('report',    help='Path to .perf_report.json')
    parser.add_argument('--sources', required=True,
                        help='Semicolon-separated module=path pairs: '
                             '"qt6webenginecore=C:\\src\\qt;i4tools=\\\\server\\src"')
    parser.add_argument('--out', help='Output JSON path (default: <report>.source_analysis.json)')
    args = parser.parse_args()

    source_map = {}
    for entry in args.sources.split(';'):
        entry = entry.strip()
        if '=' in entry:
            module, path = entry.split('=', 1)
            source_map[module.strip().lower()] = path.strip()

    if not source_map:
        print("ERROR: --sources must contain at least one module=path pair", file=sys.stderr)
        sys.exit(1)

    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    result = analyze_with_sources(args.report, source_map)

    # Save JSON first so data is never lost even if stdout encoding fails
    out_path = args.out or re.sub(r'\.perf_report\.json$', '.source_analysis.json', args.report)
    if out_path == args.report:
        out_path = args.report + '.source_analysis.json'
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(format_source_report(result))
    print(f"\n[Source analysis saved to: {out_path}]")


if __name__ == '__main__':
    main()

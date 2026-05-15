"""
SPDX-License-Identifier: Apache-2.0

Copyright (c) 2026 Qualcomm Technologies, Inc.
All Rights Reserved.
"""

from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import DoubleQuotedScalarString as DQ
from ruamel.yaml.scalarstring import LiteralScalarString as LS

from .report import Report
from .report_item import ReportItem
from .scanner import Scanner

# Map internal issue_type keys to user-facing category strings.
_CATEGORY_MAP = {
    'InlineAsmIssue':              'x64_inline_asm_incompatible',
    'NoEquivalentInlineAsmIssue':  'x64_inline_asm_incompatible',
    'IntrinsicIssue':              'x64_intrinsics_incompatible',
    'NoEquivalentIntrinsicIssue':  'x64_intrinsics_incompatible',
    'Avx256IntrinsicIssue':        'x64_intrinsics_incompatible',
    'Avx512IntrinsicIssue':        'x64_intrinsics_incompatible',
    'AsmSourceIssue':              'asm_source_incompatible',
    'IncompatibleHeaderFileIssue': 'incompatible_header',
    'DefineOtherArchIssue':        'arch_detection_code',
    'ArchConfigMissIssue':         'missing_arch_config',
}

_NO_SHOW = {
    'NoIssuesFoundRemark',
    'summary',
    'NoEquivalentInlineAsmIssue',
    'NoEquivalentIntrinsicIssue',
    'NoEquivalentIssue',
}


class YamlReport(Report):
    """Generates a YAML-format compatibility report."""

    def write_items(self, output_file, items):
        yaml = YAML()
        yaml.default_flow_style = False
        yaml.width = 120

        # ── summary counters ─────────────────────────────────────────────────
        issue_count = 0
        category_counts: dict[str, int] = {}

        visible = []
        for item in items:
            t = item.issue_type.get('type')
            if t in _NO_SHOW:
                continue
            issue_count += 1
            cat = _CATEGORY_MAP.get(t, t)
            category_counts[cat] = category_counts.get(cat, 0) + 1
            visible.append(item)

        # ── build document ────────────────────────────────────────────────────
        doc = {
            'meta': {
                'root_directory': DQ(str(self.root_directory)),
                'arch':           DQ(str(self.arch or 'aarch64')),
                'total_issues':   issue_count,
                'issue_summary':  {DQ(k): v for k, v in sorted(category_counts.items())},
            },
            'issues': [],
        }

        for idx, item in enumerate(visible, start=1):
            t = item.issue_type.get('type')
            cat = _CATEGORY_MAP.get(t, t)

            entry = {
                'id':          DQ(f'ISSUE-{idx:04d}'),
                'file':        DQ(str(item.filename or '')),
                'line':        item.lineno if item.lineno is not None else 0,
                'category':    DQ(cat),
                'description': DQ(str(item.description or '')),
            }
            func_end = getattr(item, 'func_end_lineno', None)
            if func_end is not None:
                entry['line_end'] = func_end
            if item.checkpoint and str(item.checkpoint).strip():
                entry['matched_code'] = DQ(str(item.checkpoint).strip())
            func_code = getattr(item, 'func_code', None)
            if func_code:
                entry['code'] = LS(func_code)

            doc['issues'].append(entry)

        yaml.dump(doc, output_file)

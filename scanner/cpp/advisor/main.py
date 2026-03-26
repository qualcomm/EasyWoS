"""
Copyright 2017-2018,2020 Arm Ltd.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

SPDX-License-Identifier: Apache-2.0
"""

"""
Copyright (c) 2026 Qualcomm Technologies, Inc.
All Rights Reserved.
Qualcomm Technologies, Inc. Confidential and Proprietary.
Not a Contribution. Notifications and licenses are retained for attribution purposes only.
"""
import argparse
import os
import sys
import textwrap

from . import __project__
from . import __target__
from . import __summary__
from . import __version__
from .arch_strings import *
from .arm64_scanners import Arm64Scanners
from .cmake_internal_target_scanner import CmakeInternalTargetScanner
from .auto_scanner import AutoScanner
from .issue_type_config import IssueTypeConfig
from .issue_types import ISSUE_TYPES
from .localization import _
from .os_strings import *
from .progress import create_progress_for_scanner
from .report_factory import ReportFactory
from .report_factory import ReportOutputFormat


def main():
    epilog = _('Target ISA Type:') + '\n' + \
             textwrap.fill(_('%s' % (','.join(AARCH64_ARCHS))),
                           initial_indent='  ',
                           subsequent_indent='  ') + '\n\n' + \
             _('Use:') + '\n' + \
             textwrap.fill(_('--issue-types=+CompilerSpecific to enable reporting of use of compiler-specific macros.'),
                           initial_indent='  ',
                           subsequent_indent='    ') + '\n' + \
             textwrap.fill(_('--issue-types=+CrossCompile to enable reporting of cross-compile specific issues.'),
                           initial_indent='  ',
                           subsequent_indent='    ') + '\n' + \
             textwrap.fill(
                 _('--issue-types=+NoEquivalent to enable reporting of aarch64 ported code that does not use intrinsics inline assembly versus other architectures.'),
                 initial_indent='  ',
                 subsequent_indent='    ') + '\n\n' + \
             _('Available issue types:') + '\n' + \
             textwrap.fill(', '.join(sorted(ISSUE_TYPES.keys())),
                           initial_indent='  ',
                           subsequent_indent='  ')

    parser = argparse.ArgumentParser(
        prog=__project__,
        description=__summary__,
        epilog=epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter)

    parser.add_argument('root',
                        metavar='DIRECTORY',
                        help=_('root directory of source tree to scan (default: .).'),
                        default='.')

    parser.add_argument('--git-repo',
                        help=_('git repository address to scan, when present, repo will be cloned to local.'),
                        metavar='REPO',
                        default=None)

    parser.add_argument('--branch',
                        help=_('git repository branch (default: master).'),
                        default=None)

    parser.add_argument('--commit',
                        help=_('git repository code commit id (default: HEAD).'),
                        default=None)

    parser.add_argument('--arch',
                        help=_('target instruction set architecture (default: %s).' % DEFAULT_ARCH),
                        default=DEFAULT_ARCH)

    parser.add_argument('--march',
                        help=_('target microarchitecture name, required when arch is x86 (default: None).'),
                        default=None)

    parser.add_argument('--target-os',
                        help=_(
                            'target operating system (default: %s), supported OS (%s).' % (DEFAULT_OS, SUPPORTED_OS)),
                        metavar='OS',
                        default=DEFAULT_OS)

    parser.add_argument('--target-compiler',
                        help=_(
                            'target compiler(default: %s), supported OS (%s).'
                            % (DEFAULT_COMPILER, SUPPORTED_COMPILERS)),
                        metavar='COMPILER',
                        default=DEFAULT_COMPILER)

    parser.add_argument('--build-tool',
                        help=_('build tool make or msbuild (default: make).'),
                        default='make')

    parser.add_argument('--warning-level',
                        help=_(
                            'warning level (default: %s), supported level (%s).'
                            'indicate the certainty when report a warning,'
                            'L1 ---- only report a warning with great certainty,'
                            'L2 ---- report a warning with less certainty'
                            % ('L1', ['L1', 'L2'])),
                        metavar='LEVEL',
                        default='L1')

    parser.add_argument('--output',
                        help=_('report file name.'),
                        default=None)

    parser.add_argument('--locale',
                        help=_('locale for the report (default: en-US).'),
                        default='en-US')

    parser.add_argument('--output-format',
                        help=_('output format: %s (default: %s).') %
                             (','.join(str(output_format.value) for output_format in ReportOutputFormat),
                              ReportOutputFormat.DEFAULT.value),
                        metavar='FORMAT',
                        default=ReportOutputFormat.DEFAULT.value)

    parser.add_argument('--issue-types',
                        metavar='TYPES',
                        help=_('types of issue that are reported (default: "%s").') % IssueTypeConfig.DEFAULT_FILTER)

    parser.add_argument('--no-progress',
                        action='store_false',
                        help=_('when set, there will be no progress bar.'),
                        dest='progress')

    parser.add_argument('--quiet',
                        action='store_true',
                        help=_('suppress file errors.'),
                        default=False)

    parser.add_argument('--version',
                        action='version',
                        version='%(prog)s ' + __version__)

    args = parser.parse_args()

    if not args.arch in AARCH64_ARCHS:
        print(_('unknown/unsupported arch: %s') % args.arch,
              file=sys.stderr)
        sys.exit(1)

    if args.target_os not in SUPPORTED_OS:
        print(_('OS "%s" is not supported.\nSupported OS: %s' % (args.target_os, SUPPORTED_OS)),
              file=sys.stderr)
        sys.exit(1)

    if not os.path.exists(args.root):
        print(_('%s: directory not found.') % args.root,
              file=sys.stderr)
        sys.exit(1)

    if not os.path.isdir(args.root):
        print(_('%s: not a directory.') % args.root,
              file=sys.stderr)
        sys.exit(1)

    try:
        report_factory = ReportFactory()
        args.output_format = ReportOutputFormat(args.output_format)

        if args.output_format == ReportOutputFormat.AUTO:
            if not args.output:
                args.output_format = ReportOutputFormat.TEXT
            else:
                # Take the output format from the output file extension.
                # for example, "report.json" -> JSON
                args.output_format = report_factory.output_format_for_extension(os.path.splitext(args.output)[1][1:])

                if not args.output_format:
                    raise ValueError

    except ValueError:
        print(_('%s: invalid output format') % args.output_format, file=sys.stderr)
        sys.exit(1)

    report = report_factory.createReport(args.root,
                                         arch=args.arch,
                                         march=args.march,
                                         target_os=args.target_os,
                                         output=args.output,
                                         output_format=args.output_format,
                                         issue_type_config=args.issue_types,
                                         git_repo=args.git_repo,
                                         branch=args.branch,
                                         commit=args.commit,
                                         quiet=args.quiet,
                                         progress=args.progress,
                                         locale=args.locale)

    issue_type_config_instance = IssueTypeConfig(args.issue_types)

    external_targets = set()
    if args.build_tool == 'make':
        try:
             # Pre-scan for internal targets using CmakeInternalTargetScanner
             target_scanner = CmakeInternalTargetScanner()
             # Use a temporary report for the pre-scan (or reuse report but clear it? safe to reuse usually just adds)
             # Wait, scan_tree adds issues to report. We don't want issues from this pass if they are duplicates or if we only want targets.
             # But CmakeInternalTargetScanner inherits MakefileScanner which scans for targets but DOES NOT produce issues itself (it inherits Scanner but overrides scan_file_object which populates internal_targets).
             # It does NOT inherit Arm64MakefileScanner, so it won't produce architecture issues.
             # So it is safe to run.
             # We can make a dummy report just in case.
             dummy_report = report_factory.createReport(args.root, output_format=ReportOutputFormat.TEXT, quiet=True) 
             
             pre_scanner = AutoScanner([target_scanner])
             pre_scanner.scan_tree(args.root, dummy_report, progress_callback=None)
             
             external_targets = target_scanner.get_internal_targets()
             if not args.quiet:
                 print(f"Info: Pre-scan found {len(external_targets)} internal targets.")
        except Exception as e:
            if not args.quiet:
                print(f"Warning: Pre-scan for targets failed: {e}")
    print(f"Debug: External targets to ignore: {external_targets}")
    if args.arch in AARCH64_ARCHS:
        scanners = Arm64Scanners(issue_type_config_instance,
                                 output_format=args.output_format,
                                 arch=args.arch,
                                 march=args.march,
                                 compiler=args.target_compiler,
                                 warning_level=args.warning_level,
                                 locale=args.locale,
                                 build_tool=args.build_tool,
                                 external_targets=external_targets
                                 )
    else:
        raise RuntimeError('no scanner available for arch %s.' % args.arch)

    scanners.initialize_report(report)
    scanner = AutoScanner(scanners)
    scanner.scan_tree(args.root,
                      report,
                      progress_callback=create_progress_for_scanner(__target__) if args.progress else None)

    scanners.finalize_report(report)

    if args.output:
        with open(args.output, 'w') as f:
            report.write(f, report_errors=not args.quiet)
    else:
        report.write(sys.stdout, report_errors=not args.quiet)

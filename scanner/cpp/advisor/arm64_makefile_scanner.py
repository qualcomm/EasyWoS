"""
Copyright 2017-2018 Arm Ltd.

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
import os
import re

from .arch_specific_library_issue import ArchSpecificLibraryIssue
from .arch_specific_libs import ARM64_ARCH_SPECIFIC_LIBS
from .arch_strings import AARCH64_ARCHS, NON_AARCH64_ARCHS
from .build_command_issue import BuildCommandIssue
from .continuation_parser import ContinuationParser
from .define_other_arch_issue import DefineOtherArchIssue
from .host_cpu_detection_issue import HostCpuDetectionIssue
from .old_crt_issue import OldCrtIssue
from .makefile_scanner import MakefileScanner
from .report_factory import ReportOutputFormat
from .checkpoints import AARCH64_COMPILER_OPTION_CHECKPOINTS


class Arm64MakefileScanner(MakefileScanner):

    """
    Scanner that scans Makefiles.
    """
    ARCH_SPECIFIC_LIBS_RE = re.compile(r'(%s)' % '|'.join([(r'%s\b' % x) for x in ARM64_ARCH_SPECIFIC_LIBS]))

    #  ('!IF "$(CPU)" == "otherarch"')
    #  ('!IF "$(VSCMD_ARG_TGT_ARCH)" == "aarch64"')
    AARCH64_CPU_LINE_RE = re.compile(r'\$\(VSCMD_ARG_TGT_ARCH\).*(%s)' % '|'.join(AARCH64_ARCHS))

    OTHER_ARCH_CPU_LINE_RE = re.compile(r'\$\((?:CPU|PROCESSOR_ARCHITECTURE)\).*(%s)' % '|'.join(NON_AARCH64_ARCHS))

    D_AARCH64_RE = re.compile(r'[-/]D(%s)' %
                              '|'.join(AARCH64_ARCHS +
                                       [x.upper() for x in AARCH64_ARCHS] +
                                       [('_%s_' % x) for x in AARCH64_ARCHS] +
                                       [('_%s_' % x.upper()) for x in AARCH64_ARCHS] +
                                       [('__%s__' % x) for x in AARCH64_ARCHS] +
                                       [('__%s__' % x.upper()) for x in AARCH64_ARCHS]))

    D_OTHER_ARCH_RE = re.compile(r'[-/]D(%s)' %
                                 '|'.join(NON_AARCH64_ARCHS +
                                          [x.upper() for x in NON_AARCH64_ARCHS] +
                                          [('_%s_' % x) for x in NON_AARCH64_ARCHS] +
                                          [('_%s_' % x.upper()) for x in NON_AARCH64_ARCHS] +
                                          [('__%s__' % x) for x in NON_AARCH64_ARCHS] +
                                          [('__%s__' % x.upper()) for x in NON_AARCH64_ARCHS]))
    
    # match gcc/clang style third party libs, e.g., -lmylib, -l mylib
    MAKEFILE_THIRD_LIB_RE = re.compile(r'(?:^|\s)-l([a-zA-Z0-9_\-]+)')
    CMAKE_TARGET_LINK_LIB_RE = re.compile(
        r'(?i)target_link_libraries\s*\(([^)]+)\)',
        re.DOTALL
    )
    CMAKE_FIND_PACKAGE_RE = re.compile(
        r'find_package\s*\(\s*([A-Za-z0-9_.\-]+)',
        re.IGNORECASE
    )
    # match Intel IPP (Intel Integrated Performance Primitives) libs
    IPP_RE = re.compile(r'\b((?:ipp(?:core|cp|vm|cc|s|i|cv|ch|dc|e|r|sc|sr|tf)|tbb|dnnl)[a-z0-9]*(?:\.lib)?)\b', re.IGNORECASE)
    
    # match Intel oneAPI libs
    ONEAPI_RE = re.compile(r'\b((?:mkl|mkldnn|daal|onedal|svml|sycl|dpcpp|vpl|ccl|openvino|impi)[a-z0-9_]*(?:\.lib)?)\b', re.IGNORECASE)

    # system libs to exclude from third party libs check
    SYSTEM_LIBS = {'m', 'pthread', 'rt', 'dl', 'atomic', 'z'}

    # Load Windows ARM64 supported ports from file
    WOS_SUPPORTED_LIBS = {}
    _ports_file = os.path.join(os.path.dirname(__file__), 'windows_arm64_ports.txt')
    if os.path.exists(_ports_file):
        with open(_ports_file, 'r') as f:
            for line in f:
                l = line.strip()
                if l:
                    WOS_SUPPORTED_LIBS[l] = True

    def __init__(self, output_format, arch, march, locale='en-US', external_targets=None):
        self.output_format = output_format
        self.arch = arch
        self.march = march
        self.locale = locale
        self.highlight_code_snippet = bool(self.output_format == ReportOutputFormat.HTML or self.output_format == ReportOutputFormat.JSON)
        self.external_targets = external_targets if external_targets is not None else set()

    # check the third_lib is internal or not
    def _check_internal_libs(self, third_lib):
        is_internal = False
        if third_lib in self.external_targets:
            is_internal = True
        else:
            candidates = [
                'lib%s.a' % third_lib,
                '%s.lib' % third_lib,
                'lib%s.so' % third_lib,
                '%s.dll' % third_lib,
                '%s.exe' % third_lib
            ]
            for c in candidates:
                if c in self.external_targets:
                    is_internal = True
        return is_internal

    def scan_file_object(self, filename, file_obj, report):

        _lines = file_obj.readlines()
        self.FILE_SUMMARY[self.MAKEFILE]['count'] += 1
        self.FILE_SUMMARY[self.MAKEFILE]['loc'] += len(_lines)

        continuation_parser = ContinuationParser()
        logical_lines = []
        lines = {}
        
        # Pre-scan to build logical lines and map map for snippets
        for lineno, line in enumerate(_lines, 1):
            lines[lineno] = line
            line = continuation_parser.parse_line(line)
            if not line:
                continue
            if line.startswith('#'):
                continue
            logical_lines.append((lineno, line))

        # Pass 2: Detect issues using full project context
        targets = set()
        commands = set()
        assignments = dict()
        issues = []
        
        for lineno, line in logical_lines:

            # check cmake build tool
            # check third-party libs in Makefile e.g., -lmylib
            for match in self.__class__.MAKEFILE_THIRD_LIB_RE.finditer(line):
                third_lib_name = match.group(1)
                self._check_third_party_libs(filename, lineno, third_lib_name, issues)

            # check third-party libs in CMakeLists.txt style
            # check target_link_libraries
            for match in self.__class__.CMAKE_TARGET_LINK_LIB_RE.finditer(line):
                content = match.group(1)
                args = content.split()
                if len(args) > 1:
                    libs = args[1:] 
                    for lib in libs:
                        # filter out CMake keywords
                        if lib in {'PRIVATE', 'PUBLIC', 'INTERFACE', 'debug', 'optimized', 'general'}:
                            continue
                        third_lib_name = lib
                        self._check_third_party_libs(filename, lineno, third_lib_name, issues)
            
            # check find_package
            for match in self.__class__.CMAKE_FIND_PACKAGE_RE.finditer(line):
                third_lib_name = match.group(1)
                self._check_third_party_libs(filename, lineno, third_lib_name, issues)
            #  check of old C Runtime libs, if universal CRT found
            #  then it will not be seen as an issue, be note that
            #  such check performs only once per file.
            match = self.__class__.OLD_CRT_RE.search(line)
            if match:
                old_crt_lib_name = match.group(0)
                if old_crt_lib_name:
                    issues.append(OldCrtIssue(filename,
                                              lineno,
                                              old_crt_lib_name))

            #  check of other CPU archs related lines
            match = self.__class__.OTHER_ARCH_CPU_LINE_RE.search(line)
            if match:
                issues.append(HostCpuDetectionIssue(filename,
                                                    lineno,
                                                    line))

            #  check of arch specific macros
            match = self.__class__.D_OTHER_ARCH_RE.search(line)
            if match:
                d_other_arch = match.group(0)
                if d_other_arch:
                    issues.append(DefineOtherArchIssue(filename,
                                                       lineno,
                                                       d_other_arch))

            #  check of makefile assignment
            match = self.__class__.ASSIGNMENT_RE.search(line)
            if match:
                assignments['$(%s)' % match.group(1)] = match.group(2)

            #  check of makefile target
            match = self.__class__.TARGET_RE.search(line)
            if match:
                target = match.group(1)
                if target.startswith('./') or target.startswith('.\\'):
                    target = target[2:]
                targets.add(target)

                build_commands = targets.intersection(commands)

                if target in build_commands:
                    if target in assignments:
                        target = assignments[target]

                    issues.append(BuildCommandIssue(filename,
                                                    lineno,
                                                    target=target))
            #  check of makefile command
            match = self.__class__.COMMAND_RE.search(line)
            if match:
                command = match.group(1)
                if not command:
                    command = match.group(2)
                if command.startswith('./') or command.startswith('.\\'):
                    command = command[2:]
                commands.add(command)

                build_commands = targets.intersection(commands)

                if command in build_commands:
                    if command in assignments:
                        command = assignments[command]

                    issues.append(BuildCommandIssue(filename,
                                                    lineno,
                                                    target=command))

            #  other check points
            for c in AARCH64_COMPILER_OPTION_CHECKPOINTS:

                match = c.pattern_compiled.search(line)

                if match:
                    if self.locale.startswith('zh'):
                        issues.append(BuildCommandIssue(filename,
                                                    lineno,
                                                    checkpoint=c.pattern,
                                                    description='' if not c.help_zh else '\\n' + c.help_zh))
                        break
                    if self.locale.startswith('en'):
                        issues.append(BuildCommandIssue(filename,
                                                        lineno,
                                                        checkpoint=c.pattern,
                                                        description='' if not c.help else '\\n' + c.help))
                        break

        for issue in issues:
            issue.set_code_snippet(issue.get_code_snippets(lines, with_highlights=self.highlight_code_snippet))
            report.add_issue(issue)

    def _check_third_party_libs(self, filename, lineno, thirdlibname, issues):
        """
        return and you can skip further processing if the thirdlibname is internal or system lib
        """
        if thirdlibname in self.__class__.SYSTEM_LIBS:
            return
        
        if self._check_internal_libs(thirdlibname):
            return
        
        # issue detected, intel IPP/oneAPI or unsupported lib
        if self.__class__.IPP_RE.match(thirdlibname) or self.__class__.ONEAPI_RE.match(thirdlibname):
            issues.append(ArchSpecificLibraryIssue(filename,
                                                   lineno,
                                                   lib_name=thirdlibname,
                                                   arch=self.arch,
                                                   locale=self.locale))
                
        # issue detected, unsupported lib on WOS
        if thirdlibname not in self.WOS_SUPPORTED_LIBS:
            issues.append(ArchSpecificLibraryIssue(filename,
                                                   lineno,
                                                   lib_name=thirdlibname,
                                                   arch=self.arch,
                                                   locale=self.locale))
            

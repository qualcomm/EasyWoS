"""
Copyright (c) 2026 Qualcomm Technologies, Inc.
All Rights Reserved.
Qualcomm Technologies, Inc. Confidential and Proprietary.
Not a Contribution. Notifications and licenses are retained for attribution purposes only.
"""
"""
Copyright 2017 Arm Ltd.

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


import os
import re
from .asm_source_issue import AsmSourceIssue
from .report_factory import ReportOutputFormat
from .scanner import Scanner


class AsmSourceScanner(Scanner):

    """
    Scanner that looks for assembly source files.
    """

    ASM_SOURCE_EXTENSIONS = ['.s', '.S', '.asm']

    #  Some assembly source files don't actually contain any architecture
    #  specific instructions. This is designed to match common instruction
    #  syntaxes.
    INSTRUCTION_RE = re.compile(r'(?i)(%|\b)(e[a-d]x|[er][sb]p|[er][sd]i|r[a-d]x|r[8-9][dwb]?|r1[0-5][dwb]?|[xyz]mm\d+)\b')

    def __init__(self, output_format, arch, march, locale='en-US'):
        self.output_format = output_format
        self.arch = arch
        self.march = march
        self.locale = locale

        self.highlight_code_snippet = bool(self.output_format == ReportOutputFormat.HTML or self.output_format == ReportOutputFormat.JSON)

    def accepts_file(self, filename):
        _, ext = os.path.splitext(filename)
        return ext.lower() in self.__class__.ASM_SOURCE_EXTENSIONS

    def scan_file_object(self, filename, file_obj, report):

        _lines = file_obj.readlines()
        self.FILE_SUMMARY[self.ASSEMBLY]['count'] += 1
        self.FILE_SUMMARY[self.ASSEMBLY]['loc'] += len(_lines)

        issues = []
        lines = {}

        lineno: int
        line: str
        for lineno, line in enumerate(_lines, 1):
            lines[lineno] = line

            if line.strip().startswith('*') or line.strip().startswith('//') or line.strip().startswith('/*'):
                continue

            if self.__class__.INSTRUCTION_RE.search(line):
                if self.locale.startswith('zh'):
                    issues.append(AsmSourceIssue(description="x86 架构汇编源文件",
                                             filename=filename,
                                             lineno=lineno,
                                             checkpoint=line))
                if self.locale.startswith('en'):
                    issues.append(AsmSourceIssue(description="x86 architecture assembly source file",
                                                filename=filename,
                                                lineno=lineno,
                                                checkpoint=line))
                break

        for issue in issues:
            issue.set_code_snippet(issue.get_code_snippets(lines, with_highlights=self.highlight_code_snippet))
            report.add_issue(issue)

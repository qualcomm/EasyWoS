"""
SPDX-License-Identifier: Apache-2.0

Copyright (c) 2026 Qualcomm Technologies, Inc.
All Rights Reserved.
"""

import os
import re

from .scanner import Scanner
from .arch_specific_library_issue import ArchSpecificLibraryIssue
from .issue import Issue
from .report_factory import ReportOutputFormat
from .localization import _
from .arch_config_miss_issue import ArchConfigMissIssue

class Arm64VcxprojScanner(Scanner):
    """
    Scanner that scans .vcxproj files for Windows on Arm64 compatibility.
    """

    # Common Windows system libraries to ignore
    SYSTEM_LIBS = {
        'kernel32', 'user32', 'gdi32', 'winspool', 'comdlg32', 'advapi32', 'shell32', 'ole32', 'oleaut32', 'uuid', 'odbc32', 'odbccp32',
        'ws2_32', 'rpcrt4', 'iphlpapi', 'version', 'shlwapi', 'netapi32', 'winmm', 'mpr', 'winhttp', 'setupapi', 'crypt32', 'secur32',
        'bcrypt', 'ncrypt', 'imagehlp', 'dbghelp', 'normaliz', 'urlmon', 'wininet'
    }

    # Load Windows ARM64 supported ports from file
    WOS_SUPPORTED_LIBS = {}
    _ports_file = os.path.join(os.path.dirname(__file__), 'windows_arm64_ports.txt')
    if os.path.exists(_ports_file):
        with open(_ports_file, 'r') as f:
            for line in f:
                l = line.strip().lower()
                if l:
                    WOS_SUPPORTED_LIBS[l] = True

    # Regex to find .lib files
    # Matches filenames ending in .lib, allowing alphanumeric, underscore, hyphen, and dot.
    # This handles semicolon-separated lists in <AdditionalDependencies> as well.
    LIB_FILE_RE = re.compile(r'([a-zA-Z0-9_\-\.]+\.lib)', re.IGNORECASE)

    # match Intel IPP (Intel Integrated Performance Primitives) libs
    IPP_RE = re.compile(r'\b((?:ipp(?:core|cp|vm|cc|s|i|cv|ch|dc|e|r|sc|sr|tf)|tbb|dnnl)[a-z0-9]*(?:\.lib)?)\b', re.IGNORECASE)

    # match Intel OneAPI libs
    ONEAPI_RE = re.compile(r'\b((?:mkl|mkldnn|daal|onedal|svml|sycl|dpcpp|vpl|ccl|openvino|impi)[a-z0-9_]*(?:\.lib)?)\b', re.IGNORECASE)
    
    # Regex to find ARM64 configuration
    ARM64_CONFIG_RE = re.compile(r'<ProjectConfiguration\s+Include="[^"]*\|ARM64"', re.IGNORECASE)

    def __init__(self, output_format, arch, march, locale='en-US'):
        self.output_format = output_format
        self.arch = arch
        self.march = march
        self.locale = locale
        self.highlight_code_snippet = bool(self.output_format == ReportOutputFormat.HTML or self.output_format == ReportOutputFormat.JSON)

    def accepts_file(self, filename):
        return filename.lower().endswith('.vcxproj')

    def scan_file_object(self, filename, file_obj, report):
        # Count lines        
        _lines = file_obj.readlines()
        self.FILE_SUMMARY[self.VCXPROJ]['count'] += 1
        self.FILE_SUMMARY[self.VCXPROJ]['loc'] += len(_lines)

        has_arm64_config = False
        issues = []
        lines = {}

        for lineno, line in enumerate(_lines, 1):
            lines[lineno] = line
            
            # Check for ARM64 configuration
            if self.ARM64_CONFIG_RE.search(line):
                has_arm64_config = True

            # Check for third-party libraries
            for match in self.LIB_FILE_RE.finditer(line):
                lib_full = match.group(1)
                lib_name = lib_full[:-4].lower() # remove .lib and lowercase

                # Skip system libraries
                if lib_name in self.SYSTEM_LIBS:
                    continue
                
                # Check for Intel IPP or OneAPI libs
                if self.IPP_RE.match(lib_full) or self.ONEAPI_RE.match(lib_full):
                    issues.append(ArchSpecificLibraryIssue(filename=filename,
                                                           lineno=lineno,
                                                           lib_name=lib_full,
                                                           arch=self.arch,
                                                           locale=self.locale))
                    continue

                # Check if supported
                if lib_name not in self.WOS_SUPPORTED_LIBS:
                    issues.append(ArchSpecificLibraryIssue(filename=filename,
                                                           lineno=lineno,
                                                           lib_name=lib_name,
                                                           arch=self.arch,
                                                           locale=self.locale))

        if not has_arm64_config:
             issues.append(ArchConfigMissIssue(
                    filename=filename,
                    lineno=lineno,
                    arch=self.arch,
                    locale=self.locale
                ))

        for issue in issues:
            issue.set_code_snippet(issue.get_code_snippets(lines, with_highlights=self.highlight_code_snippet))
            report.add_issue(issue)


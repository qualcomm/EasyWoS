"""
SPDX-License-Identifier: Apache-2.0

Copyright (c) 2026 Qualcomm Technologies, Inc.
All Rights Reserved.
"""
"""
SPDX-License-Identifier: BSD-3-Clause
Copyright (c) 2023 Qualcomm Innovation Center, Inc.
All rights reserved.
"""

import os
import re

from .makefile_scanner import MakefileScanner
from .continuation_parser import ContinuationParser

class CmakeInternalTargetScanner(MakefileScanner):
    """
    Scanner to identify internal targets defined in CMakeLists.txt and Makefiles.
    This helps in filtering out internal libraries from being flagged as missing external dependencies.
    """

    # Makefile Regexes
    TARGET_RE = re.compile(r'^([a-zA-Z()$_0-9./\\]+)\s*:', re.IGNORECASE)
    ASSIGNMENT_RE = re.compile(r'^([a-zA-Z()$_0-9]+)\s*=\s*(.*)$', re.IGNORECASE)
    
    # CMake Regexes
    # Matches: add_library(target_name ...)
    CMAKE_ADD_LIBRARY_RE = re.compile(r'add_library\s*\(\s*([A-Za-z0-9_:.+\-]+)', re.IGNORECASE)
    # Matches: add_executable(target_name ...)
    CMAKE_ADD_EXECUTABLE_RE = re.compile(r'add_executable\s*\(\s*([A-Za-z0-9_:.+\-]+)', re.IGNORECASE)
    # Matches: project(project_name ...) - sometimes used as target base
    CMAKE_PROJECT_RE = re.compile(r'project\s*\(\s*([A-Za-z0-9_:.+\-]+)', re.IGNORECASE)

    def __init__(self):
        super().__init__()
        self.internal_targets = set()

    def scan_file_object(self, filename, file_obj, report=None):
        """
        Scans the file object for target definitions.
        report parameter is kept for compatibility with Scanner interface but not used for reporting issues.
        """
        _lines = file_obj.readlines()
        continuation_parser = ContinuationParser()
        logical_lines = []
        
        # Pre-scan to handle line continuations
        for lineno, line in enumerate(_lines, 1):
            line = continuation_parser.parse_line(line)
            if not line:
                continue
            if line.startswith('#'):
                continue
            logical_lines.append(line)

        basename = os.path.basename(filename)
        
        if basename in self.__class__.CMAKE_NAMES or basename.split('.')[-1] in self.__class__.CMAKE_NAMES:
            self._scan_cmake(logical_lines)
        if basename in self.__class__.MAKEFILE_NAMES or \
            basename.lower() in self.__class__.MAKEFILE_NAMES_CASE_INSENSITIVE:
            self._scan_makefile(logical_lines) 


    def _scan_cmake(self, lines):
        for line in lines:
            # Check add_library
            match = self.CMAKE_ADD_LIBRARY_RE.search(line)
            if match:
                self.internal_targets.add(match.group(1))
            
            # Check add_executable
            match = self.CMAKE_ADD_EXECUTABLE_RE.search(line)
            if match:
                self.internal_targets.add(match.group(1))

    def _scan_makefile(self, lines):
        assignments = dict()
        local_targets = set()

        for line in lines:
            # Check Assignments
            match = self.ASSIGNMENT_RE.search(line)
            if match:
                assignments['$(%s)' % match.group(1)] = match.group(2)

            # Check Targets
            match = self.TARGET_RE.search(line)
            if match:
                target = match.group(1)
                if target.startswith('./') or target.startswith('.\\'):
                    target = target[2:]
                
                local_targets.add(target)
                if target in assignments:
                    local_targets.add(assignments[target])
        
        self.internal_targets.update(local_targets)

    def get_internal_targets(self):
        return self.internal_targets

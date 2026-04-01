"""
SPDX-License-Identifier: Apache-2.0

Copyright (c) 2026 Qualcomm Technologies, Inc.
All Rights Reserved.
"""
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

import os
import sys
import traceback
import re

from .error import Error
from .cpp_lib_version_issue import CPPLibVersionIssue
from .cpp_lib_recommend_issue import CPPLibRecommendIssue


class Scanner:

    #  List of (hidden) subdirectories used by version control systems.
    VCS_SUBDIRECTORIES = ['.git', '.hg', '.svn', 'CVS']

    CPP_LIB_CHECK_VERSION_LIST = ['boost']
    CPP_LIB_VERSION_DICT = {'boost': '106000'}

    CPP_LIB_WHITE_LIST = ['folly', 'asio', 'msgpack']

    CPP_LIB_RECOMMEND_LIST = ['zstd']

    NON_EMPTY_LINE_RE = re.compile(r'\S')

    C = 'c'
    CPP = 'cpp'
    ASSEMBLY = 'asm'
    MAKEFILE = 'makefile'
    AUTOCONF = 'config.guess'
    VCXPROJ = 'vcxproj'

    FILE_SUMMARY = {
        C: {
            "fileName": "C file",
            "loc": 0,
            "count": 0
        },
        CPP: {
            "fileName": "CPP file",
            "loc": 0,
            "count": 0
        },
        MAKEFILE: {
            "fileName": "Makefile file",
            "loc": 0,
            "count": 0
        },
        AUTOCONF: {
            "fileName": "Autoconf file",
            "loc": 0,
            "count": 0
        },
        ASSEMBLY: {
            "fileName": "Assembly file",
            "loc": 0,
            "count": 0
        },
        VCXPROJ: {
            "fileName": "Vcxproj file",
            "loc": 0,
            "count": 0
        }
    }

    def accepts_file(self, filename):
        """
        Overriden by subclasses to decide whether or not to accept a
        file.

        Args:
            filename (str): Filename under consideration.

        Returns:
            bool: True if the file with the given name is accepted by this
            scanner, else False.
        """
        return False

    def finalize_report(self, report):
        """
        Finalizes the report for this scanner.

        Args:
            report (Report): Report to finalize_report.
        """
        pass

    def has_scan_file_object(self):
        return hasattr(self, 'scan_file_object')

    def initialize_report(self, report):
        """
        Initialises the report for this scanner, which may include
        initializing scanner-specific fields in the Report.

        Args:
            report (Report): Report to initialize_report.
        """
        pass

    def scan_file(self, filename, report):
        """
        Scans the file with the given name for potential porting issues.

        Args:
            filename (str): Name of the file to scan.
            report (Report): Report to add issues to.
        """
        try:
            report.add_source_file(filename)
            self.scan_filename(filename, report)

            if self.has_scan_file_object():

                #  there could be bad soft links so we have to
                #  check before opening it.
                if os.path.exists(filename):

                    with open(filename, errors='ignore') as f:
                        try:
                            self.scan_file_object(filename, f, report)

                        except KeyboardInterrupt:
                            raise

                        except BaseException:
                            report.add_error(Error(description=str(traceback.format_exc()),
                                                   filename=filename))

        except KeyboardInterrupt:
            raise

        except BaseException:
            report.add_error(Error(description=str(traceback.format_exc()),
                                   filename=filename))

    def scan_filename(self, filename, report):
        """
        Overridden by subclasses to scan for potential porting issues based
        on the name of the file.

        Args:
            filename (str): Name of the file to scan.
            report (Report): Report to add issues to.
        """
        pass

    def check_version(self, root, libname, report):

        version_filename = 'version.hpp'
        for dirName, _, fileList in os.walk(root):
            if version_filename not in fileList:
                continue

            path = os.path.join(dirName, version_filename)
            with open(path, 'r') as file:
                for lineno, line in enumerate(file.readlines()):
                    lineno = lineno + 1
                    if line.find('define') > 0 and line.find('_VERSION ') > 0:
                        ver_str = line[line.find('_VERSION ') + 9:line.find(' //')].strip()
                        if ver_str > Scanner.CPP_LIB_VERSION_DICT[libname]:
                            return True
                        else:
                            desc = f'{libname} version should be higher than {Scanner.CPP_LIB_VERSION_DICT[libname]}'
                            report.add_issue(CPPLibVersionIssue(path, lineno, desc))
                            return False
        else:
            return False

    def check_recommend(self, root, libname, report):

        version_filename = 'zstd.h'
        for dirName, _, fileList in os.walk(root):
            if version_filename not in fileList:
                continue

            path = os.path.join(dirName, version_filename)
            desc = 'ptg-zstd 是平头哥数据中心解决方案团队基于开源 zstd 进行深度优化开发的版本，在倚天平台上具有显著优势。\n试用联系方式: xubinbin.xbb@alibaba-inc.com\n'
            report.add_issue(CPPLibRecommendIssue(path, 0, desc))
            return True
        else:
            return False

    def scan_tree(self, root, report, progress_callback=None):
        """
        Scans the filesysem tree starting at root for potential porting issues.

        Args:
            root (str): The root of the filesystem tree to scan.
            report (Report): Report to add issues to.
            progress_callback (function): Optional callback called with file names.
        """
        for filename in os.listdir(root):
            if filename in Scanner.CPP_LIB_WHITE_LIST:
                return
            elif filename in Scanner.CPP_LIB_CHECK_VERSION_LIST and \
                    self.check_version(root, filename, report):
                return
            elif filename in Scanner.CPP_LIB_RECOMMEND_LIST \
                    and self.check_recommend(root, filename, report):
                return

        for dirName, _, fileList in os.walk(root):

            fileList.sort()

            for fname in fileList:

                path = os.path.join(dirName, fname)
                if not Scanner._is_vcs_directory(path) and self.accepts_file(path):

                    if progress_callback:
                        progress_callback(path)

                    self.scan_file(path, report)

    @staticmethod
    def _is_vcs_directory(path):
        """
        Returns:
            bool: True if the path contains a version control directory (e.g. .git), else False.
        """
        return any([('/%s/' % x) in path for x in Scanner.VCS_SUBDIRECTORIES])

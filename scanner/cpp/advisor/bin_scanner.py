"""
SPDX-License-Identifier: Apache-2.0

Copyright (c) 2026 Qualcomm Technologies, Inc.
All Rights Reserved.
"""
import os
from .makefile_scanner import MakefileScanner

from .scanner import Scanner


class BinaryScanner(Scanner):

    """
    Scanner that scans binaries.
    """

    def accepts_file(self, filename):

        basename = os.path.basename(filename)

        return basename in MakefileScanner.MAKEFILE_NAMES or \
            basename.lower() in MakefileScanner.MAKEFILE_NAMES_CASE_INSENSITIVE or \
            basename in MakefileScanner.CMAKE_NAMES or \
            basename.split('.')[-1] in MakefileScanner.CMAKE_NAMES

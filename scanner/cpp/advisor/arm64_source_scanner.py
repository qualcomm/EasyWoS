"""
SPDX-License-Identifier: Apache-2.0

Copyright (c) 2026 Qualcomm Technologies, Inc.
All Rights Reserved.
"""
from .clang_source_scanner import ClangSourceScanner


class Arm64SourceScanner(ClangSourceScanner):

    """
    Scanner that scans C, C++ and Fortran source files for ARM64 potential
    porting issues.
    """

    def __init__(self, output_format, arch, march, compiler, warning_level, locale):

        super().__init__(output_format=output_format,
                         arch=arch,
                         march=march,
                         compiler=compiler,
                         warning_level=warning_level,
                         locale=locale)

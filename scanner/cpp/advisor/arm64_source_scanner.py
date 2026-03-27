"""
Copyright (c) 2026 Qualcomm Technologies, Inc.
All Rights Reserved.
Qualcomm Technologies, Inc. Confidential and Proprietary.
Not a Contribution. Notifications and licenses are retained for attribution purposes only.
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

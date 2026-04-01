"""
SPDX-License-Identifier: Apache-2.0

Copyright (c) 2026 Qualcomm Technologies, Inc.
All Rights Reserved.
"""
from .issue import Issue
from .localization import _
from .report_item import ReportItem


class ArchConfigMissIssue(Issue):

    def __init__(self, filename, lineno, arch=None, locale=None):

        if locale and locale.startswith('zh'):
            description = _("缺少%s的配置") % arch
        else:
            description = _("missing configuration for %s") % arch

        super().__init__(description=description,
                         filename=filename,
                         lineno=lineno,
                         issue_type=ReportItem.ARCH_CONFIG_MISS)

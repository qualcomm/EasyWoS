"""
SPDX-License-Identifier: Apache-2.0

Copyright (c) 2026 Qualcomm Technologies, Inc.
All Rights Reserved.
"""
from .issue import Issue
from .localization import _
from .report_item import ReportItem


class IncompatibleHeaderFileIssue(Issue):

    def __init__(self,
                 filename,
                 lineno,
                 arch=None,
                 intrinsic=None,
                 item_type=ReportItem.INTRINSIC,
                 checkpoint=None,
                 description=None):
        if not description:
            description = _("incompatible header file check")

        super().__init__(description=description,
                         filename=filename,
                         lineno=lineno,
                         issue_type=ReportItem.INCOMPATIBLE_HEADER_FILE,
                         checkpoint=checkpoint)

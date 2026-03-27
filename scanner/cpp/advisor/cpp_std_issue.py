"""
Copyright (c) 2026 Qualcomm Technologies, Inc.
All Rights Reserved.
Qualcomm Technologies, Inc. Confidential and Proprietary.
Not a Contribution. Notifications and licenses are retained for attribution purposes only.
"""
from .issue import Issue
from .localization import _
from .report_item import ReportItem


class CPPStdCodesIssue(Issue):

    def __init__(self, filename, lineno, arch=None, intrinsic=None, item_type=ReportItem.INTRINSIC, checkpoint=None, description=None):

        if not description:
            description = _("cpp standard language check")

        super().__init__(description=description,
                         filename=filename,
                         lineno=lineno,
                         issue_type=ReportItem.CPP_STD_CODES,
                         checkpoint=checkpoint)

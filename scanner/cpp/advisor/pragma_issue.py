"""
Copyright (c) 2026 Qualcomm Technologies, Inc.
All Rights Reserved.
Qualcomm Technologies, Inc. Confidential and Proprietary.
Not a Contribution. Notifications and licenses are retained for attribution purposes only.
"""
from .issue import Issue
from .localization import _
from .report_item import ReportItem


class PragmaIssue(Issue):

    def __init__(self, filename, lineno, pragma, checkpoint=None):

        description = _("Possible incompatible pragma: %s") % pragma

        super().__init__(description=description,
                         filename=filename,
                         lineno=lineno,
                         issue_type=ReportItem.PRAGMA,
                         checkpoint=checkpoint)

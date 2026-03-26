from .issue import Issue
from .localization import _
from .report_item import ReportItem


class CPPLibVersionIssue(Issue):

    def __init__(self, filename, lineno, description):

        super().__init__(description=description,
                         filename=filename,
                         lineno=lineno,
                         issue_type=ReportItem.CPP_LIB_VERSION,
                         checkpoint=None)

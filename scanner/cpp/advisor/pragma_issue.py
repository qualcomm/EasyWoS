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

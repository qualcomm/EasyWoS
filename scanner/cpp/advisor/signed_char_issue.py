from .localization import _
from .cross_compile_issue import CrossCompileIssue
from .report_item import ReportItem


class SignedCharIssue(CrossCompileIssue):

    def __init__(self, filename, lineno, description=None):

        if not description:
            description = _("It's recommended that you use the compiler command option \'-fsigned-char\' changes the default behaviour of plain char to be a signed char.")

        super().__init__(description=description,
                         filename=filename,
                         lineno=lineno,
                         issue_type=ReportItem.SIGNED_CHAR)

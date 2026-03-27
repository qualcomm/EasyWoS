"""
Copyright (c) 2026 Qualcomm Technologies, Inc.
All Rights Reserved.
Qualcomm Technologies, Inc. Confidential and Proprietary.
Not a Contribution. Notifications and licenses are retained for attribution purposes only.
"""
from .issue import Issue

class ARM64ECIncompatibleGrammarIssue(Issue):
    """
    Issue found in ARM64EC source files that contains incompatible grammar.
    """

    def __init__(self, filename, lineno, checkpoint=None, description=None):
        if not description:
            description = "ARM64EC incompatible grammar"

        super().__init__(description=description,
                         filename=filename,
                         lineno=lineno,
                         issue_type=Issue.ARM64EC_INCOMPATIBLE_GRAMMAR,
                         checkpoint=checkpoint)
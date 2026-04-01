"""
SPDX-License-Identifier: Apache-2.0

Copyright (c) 2026 Qualcomm Technologies, Inc.
All Rights Reserved.
"""
"""
Copyright 2017 Arm Ltd.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

SPDX-License-Identifier: Apache-2.0
"""

from .report_item import ReportItem
import re


class Issue(ReportItem):

    """
    Base class for issues.
    """

    def __init__(self, description, filename=None, lineno=None, issue_type=ReportItem.OTHER, checkpoint=None):

        super().__init__(description,
                         filename=filename,
                         lineno=lineno,
                         issue_type=issue_type,
                         checkpoint=checkpoint)

    @classmethod
    def display_name(cls):
        """
        Return the display name for the given issue class.
        """
        return re.sub('Issue$', '', cls.__name__)

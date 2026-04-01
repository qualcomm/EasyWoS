"""
SPDX-License-Identifier: Apache-2.0

Copyright (c) 2026 Qualcomm Technologies, Inc.
All Rights Reserved.
"""
# NOTE
# ---
# This file defines OS specific information including supported OS and not
# supported OS.

_SUPPORTED_OS = {
    'Windows': {
        'Windows 11':
        {
            'supported': True,
            'kernel': ''
        }
    },
}
DEFAULT_OS = 'Windows 11'
SUPPORTED_OS = [_ for _ in list(_SUPPORTED_OS['Windows'].keys()) if _SUPPORTED_OS['Windows'][_]['supported']]

"""
SPDX-License-Identifier: Apache-2.0

Copyright (c) 2026 Qualcomm Technologies, Inc.
All Rights Reserved.
"""
from sanic.response import json as sanic_json


def rsp(code=200, message='success', data=None):
    response = dict(
        code=code,
        message=message,
        data=data
    )
    return sanic_json(response, ensure_ascii=False)

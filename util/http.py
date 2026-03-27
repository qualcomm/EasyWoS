"""
Copyright (c) 2026 Qualcomm Technologies, Inc.
All Rights Reserved.
Qualcomm Technologies, Inc. Confidential and Proprietary.
Not a Contribution. Notifications and licenses are retained for attribution purposes only.
"""
from sanic.response import json as sanic_json


def rsp(code=200, message='success', data=None):
    response = dict(
        code=code,
        message=message,
        data=data
    )
    return sanic_json(response, ensure_ascii=False)

"""
Copyright (c) 2026 Qualcomm Technologies, Inc.
All Rights Reserved.
Qualcomm Technologies, Inc. Confidential and Proprietary.
Not a Contribution. Notifications and licenses are retained for attribution purposes only.
"""
class TaskProfile:
    name: str
    userid: int
    language: str
    file_path: str
    repeat_type: str
    locale: str
    build_tool: str


class UpdateTaskProfile:
    language: str
    repeat_type: str
    locale: str
    build_tool: str

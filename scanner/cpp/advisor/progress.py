"""
Copyright (c) 2026 Qualcomm Technologies, Inc.
All Rights Reserved.
Qualcomm Technologies, Inc. Confidential and Proprietary.
Not a Contribution. Notifications and licenses are retained for attribution purposes only.
"""
import datetime


def create_progress_for_scanner(scanner_name: str):
    def progress_callback(filename):
        t = datetime.datetime.now().astimezone()
        format_time = t.strftime('[%Y-%m-%d %H:%M:%S %z]')
        msg = f'[{format_time}] [{scanner_name}] {filename}'
        print(msg, flush=True)

    return progress_callback

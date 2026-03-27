"""
Copyright (c) 2026 Qualcomm Technologies, Inc.
All Rights Reserved.
Qualcomm Technologies, Inc. Confidential and Proprietary.
Not a Contribution. Notifications and licenses are retained for attribution purposes only.
"""
import datetime


def string_toDatetime(st):
    return datetime.datetime.strptime(st, "%Y-%m-%d %H:%M:%S")


def datetime_toString(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def datetime_toString_without_space(dt):
    return dt.strftime("%Y_%m_%d_%H:%M:%S")

"""
SPDX-License-Identifier: Apache-2.0

Copyright (c) 2026 Qualcomm Technologies, Inc.
All Rights Reserved.
"""
import datetime


def string_toDatetime(st):
    return datetime.datetime.strptime(st, "%Y-%m-%d %H:%M:%S")


def datetime_toString(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def datetime_toString_without_space(dt):
    return dt.strftime("%Y_%m_%d_%H:%M:%S")
